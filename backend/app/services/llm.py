import json
import logging
from typing import Optional, List
from openai import AsyncAzureOpenAI
import httpx
from app.core.config import settings
from app.core.enums import DEFAULT_COMPARISON_CATEGORIES
from app.schemas.model import ExtractionModel
from app.services.refiner import RefinerEngine
# DEPRECATED: LayoutParser moved to lazy import inside call_llm_for_extraction()
# from app.services.layout_parser import LayoutParser
from app.db.cosmos import get_config_container

logger = logging.getLogger(__name__)

# 동적 모델 설정 (어드민에서 변경 가능)
_current_model = settings.AZURE_OPENAI_DEPLOYMENT_NAME
LLM_CONFIG_ID = "llm_config"

# Safety clamp: deployed model's actual max completion tokens.
# GPT-4o = 16384, GPT-4o-2024-08-06+ = 16384, GPT-4.1 = 32768
# Bumping default to 32768 to fully support GPT-4.1 output length for complex large extractions.
MODEL_MAX_COMPLETION_TOKENS = 32768

# Singleton client — reuse across all calls
_openai_client: Optional[AsyncAzureOpenAI] = None

async def initialize_llm_settings():
    """서버 시작 시 DB에서 설정 로드"""
    global _current_model
    try:
        container = get_config_container()
        if container:
            try:
                item = await container.read_item(item=LLM_CONFIG_ID, partition_key=LLM_CONFIG_ID)
                saved_model = item.get("model_name")
                if saved_model:
                    _current_model = saved_model
                    logger.info(f"[LLM] Loaded configuration from DB: {_current_model}")
            except Exception:
                # 설정이 없으면 기본값 사용 (조용히 넘어감)
                logger.info(f"[LLM] No saved configuration found, using default: {_current_model}")
    except Exception as e:
        logger.warning(f"[LLM] Failed to initialize settings: {e}")

async def set_llm_model(model_name: str):
    """어드민에서 LLM 모델 변경 (DB 저장)"""
    global _current_model
    global _openai_client
    
    _current_model = model_name
    _openai_client = None # 클라이언트 캐시 초기화 (Stale connection 방지 / 새 API 연결 강제)
    
    # Reset inference client too (for non-OpenAI model switches)
    try:
        from app.services.llm_service import reset_inference_client
        reset_inference_client()
    except Exception:
        pass
    
    logger.info(f"[LLM] Model changed to: {_current_model} & All client caches cleared")

    # DB 저장
    try:
        container = get_config_container()
        if container:
            await container.upsert_item({
                "id": LLM_CONFIG_ID,
                "model_name": model_name,
                "updated_at": "now"
            })
            logger.info("[LLM] Configuration saved to DB")
    except Exception as e:
        logger.warning(f"[LLM] Failed to save configuration to DB: {e}")

def get_current_model() -> str:
    return _current_model

async def fetch_available_models() -> List[str]:
    """Azure AI Foundry에서 실제 배포(Deployment)된 모델 목록만 가져오기.
    
    3-layer fallback:
    1. AZURE_DEPLOYMENT_NAMES 환경 변수 (가장 빠르고 안정적)
    2. Management Plane API + DefaultAzureCredential
    3. Data Plane /openai/deployments (classic Azure OpenAI only)
    """
    models = []
    
    # ── Strategy 1: Explicit env var (most reliable for deployed environments) ──
    explicit_models = settings.AZURE_DEPLOYMENT_NAMES
    if explicit_models:
        models = [m.strip() for m in explicit_models.split(",") if m.strip()]
        if models:
            logger.info(f"[LLM] Using explicit AZURE_DEPLOYMENT_NAMES: {models}")
            return models
    
    # ── Strategy 2: Management Plane API (auto-discovery) ──
    resource_id = settings.AZURE_RESOURCE_ID
    if resource_id:
        try:
            from azure.identity import DefaultAzureCredential
            
            credential = DefaultAzureCredential()
            token = credential.get_token("https://management.azure.com/.default")
            
            mgmt_url = f"https://management.azure.com{resource_id}/deployments?api-version=2024-10-01"
            logger.info(f"[LLM] Fetching deployments from Management API...")
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    mgmt_url,
                    headers={"Authorization": f"Bearer {token.token}"},
                    timeout=15.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    for dep in data.get("value", []):
                        dep_name = dep.get("name")
                        props = dep.get("properties", {})
                        status = props.get("provisioningState", "")
                        
                        if dep_name and status == "Succeeded":
                            models.append(dep_name)
                    
                    if models:
                        logger.info(f"[LLM] Found {len(models)} deployments via Management API: {models}")
                        return models
                    else:
                        logger.warning("[LLM] Management API returned 200 but 0 succeeded deployments")
                else:
                    logger.warning(f"[LLM] Management API returned {response.status_code}: {response.text[:200]}")
        except ImportError:
            logger.warning("[LLM] azure-identity not installed, cannot use Management API")
        except Exception as e:
            logger.error(f"[LLM] Management API failed: {e}")
            logger.info("[LLM] TIP: Set AZURE_DEPLOYMENT_NAMES env var (comma-separated) to bypass Management API auth.")
    else:
        logger.debug("[LLM] AZURE_RESOURCE_ID not set, skipping Management API")
    
    # ── Strategy 3: Data Plane fallback (classic Azure OpenAI endpoints only) ──
    try:
        endpoint = settings.AZURE_OPENAI_ENDPOINT or settings.AZURE_AIPROJECT_ENDPOINT
        endpoint = endpoint.rstrip('/')
        api_key = settings.AZURE_OPENAI_API_KEY
        api_version = settings.AZURE_OPENAI_API_VERSION

        async with httpx.AsyncClient() as client:
            deployments_url = f"{endpoint}/openai/deployments?api-version={api_version}"
            logger.info(f"[LLM] Fallback: trying Data Plane {deployments_url}")
            response = await client.get(
                deployments_url,
                headers={"api-key": api_key},
                timeout=10.0
            )

            if response.status_code == 200:
                data = response.json()
                for dep in data.get("data", []):
                    dep_id = dep.get("id") or dep.get("deployment_id") or dep.get("name")
                    if dep_id:
                        models.append(dep_id)

                if models:
                    logger.info(f"[LLM] Found {len(models)} deployments via Data Plane: {models}")
                    return models
            else:
                logger.debug(f"[LLM] Data Plane /openai/deployments returned {response.status_code}")
    except Exception as e:
        logger.error(f"[LLM] Data Plane fallback failed: {e}")

    if not models:
        logger.warning("[LLM] No deployments found. Set AZURE_DEPLOYMENT_NAMES=model1,model2,... to configure explicitly.")
    return models

def get_openai_client() -> AsyncAzureOpenAI:
    """싱글톤 Azure OpenAI 클라이언트 — 연결 재사용"""
    global _openai_client
    if _openai_client is not None:
        return _openai_client

    endpoint = settings.AZURE_OPENAI_ENDPOINT or settings.AZURE_AIPROJECT_ENDPOINT
    endpoint = endpoint.rstrip('/')
    api_key = settings.AZURE_OPENAI_API_KEY
    api_version = settings.AZURE_OPENAI_API_VERSION

    if not endpoint or not api_key:
        raise ValueError("Azure AI endpoint and API key must be configured")

    logger.info(f"[LLM] Creating singleton client — Endpoint: {endpoint}")
    logger.info(f"[LLM] Model: {_current_model}")

    _openai_client = AsyncAzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=api_version,
        timeout=180.0
    )
    return _openai_client

async def analyze_document_content(
    ocr_result: dict,
    language: str = "en",
    model_info: Optional[ExtractionModel] = None
) -> dict:
    """Azure AI Foundry를 통해 문서 내용 분석"""
    client = get_openai_client()

    # Check beta feature flag (safe access pattern)
    use_optimized_prompt = False
    ref_map = None
    if model_info:
        beta_features = getattr(model_info, 'beta_features', None) or {}
        use_optimized_prompt = beta_features.get("use_optimized_prompt", False)

    # Use LayoutParser for optimized content if beta enabled
    if use_optimized_prompt:
        logger.info("[LLM-Beta] Using LayoutParser for optimized prompt")
        try:
            from app.services.layout_parser import LayoutParser  # Lazy import (Beta only)
            parser = LayoutParser(ocr_result)
            content_text, ref_map = parser.parse()
            logger.info(f"[LLM-Beta] Parsed content length: {len(content_text)}, ref_map entries: {len(ref_map)}")
        except Exception as e:
            logger.warning(f"[LLM-Beta] LayoutParser failed, falling back to raw content: {e}")
            content_text = ocr_result.get("content", "")
            ref_map = None
    else:
        content_text = ocr_result.get("content", "")

    if model_info:
        system_prompt = RefinerEngine.construct_prompt(model_info, language)
    else:
        system_prompt = f"""
        You are an AI assistant. Extract key info in JSON format.
        Language: {language}.
        Return only valid JSON, no markdown or explanation.
        """

    # Prepare Table Context (CRITICAL for Beta: Provide structural hints)
    tables_context = ""
    raw_tables = ocr_result.get("tables", [])
    if raw_tables and len(raw_tables) > 0:
        tables_context = "\n\n=== DETECTED TABLES (Structure Reference) ===\n"
        for idx, table in enumerate(raw_tables):
            # Limit to first 20 rows to avoid token explosion
            cells = table.get("cells", [])
            row_count = table.get("rowCount", 0)
            col_count = table.get("columnCount", 0)

            tables_context += f"\nTable {idx+1} ({row_count}x{col_count}):\n"

            # Simple Grid Reconstruction for Prompt
            # Dynamic budget: short cells → more rows, long cells → fewer rows
            MAX_TABLE_CONTEXT_CHARS = 50_000
            table_chars_used = 0
            grid = {}
            for cell in cells:
                r = cell.get("rowIndex", 0)
                c = cell.get("columnIndex", 0)
                content = cell.get("content", "").replace("\n", " ")
                if table_chars_used < MAX_TABLE_CONTEXT_CHARS:
                    if r not in grid: grid[r] = {}
                    grid[r][c] = content
                    table_chars_used += len(content) + 3

            # Render rows
            for r in sorted(grid.keys()):
                row_cells = grid[r]
                row_str = " | ".join([row_cells.get(c, "") for c in range(col_count)])
                tables_context += f"| {row_str} |\n"

            rows_shown = len(grid)
            if row_count > rows_shown:
                tables_context += f"... ({row_count - rows_shown} more rows) ...\n"

    user_prompt = f"Document Text:\n{content_text}\n{tables_context}"

    # Token overflow protection: estimate and truncate if needed
    # GPT-4o context: ~128K tokens. Leave room for system prompt + response.
    # Rough estimate: 1 token ≈ 4 chars for mixed content
    MAX_USER_PROMPT_CHARS = settings.LLM_MAX_USER_PROMPT_CHARS
    original_prompt_len = len(user_prompt)
    if original_prompt_len > MAX_USER_PROMPT_CHARS:
        logger.warning(f"[LLM-Beta] User prompt too large ({original_prompt_len} chars), truncating to {MAX_USER_PROMPT_CHARS}")
        # Truncate content_text first, preserve tables_context (more structured)
        max_content_len = MAX_USER_PROMPT_CHARS - len(tables_context) - 50  # 50 for prefix
        if max_content_len > 1000:
            truncated_content = content_text[:max_content_len] + "\n\n[... CONTENT TRUNCATED DUE TO SIZE ...]"
            user_prompt = f"Document Text:\n{truncated_content}\n{tables_context}"
        else:
            user_prompt = user_prompt[:MAX_USER_PROMPT_CHARS]
        logger.info(f"[LLM-Beta] Truncated prompt: {original_prompt_len} → {len(user_prompt)} chars")

    max_retries = 2  # 1 initial + 1 retry with more aggressive truncation
    last_error = None

    for attempt in range(max_retries):
        try:
            logger.info(f"[LLM] Calling: {_current_model} (attempt {attempt+1}, prompt: {len(user_prompt)} chars)")

            temp = model_info.temperature if model_info and hasattr(model_info, 'temperature') else getattr(settings, 'LLM_DEFAULT_TEMPERATURE', 0.0)
            
            response = await client.chat.completions.create(
                model=_current_model,
                messages=[
                    {"role": "system", "content": system_prompt + "\n\nIMPORTANT: Respond with valid JSON only."},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=temp,
            )

            result_content = response.choices[0].message.content
            logger.info(f"[LLM] Response received. Length: {len(result_content)}")
            llm_json = json.loads(result_content)

            if model_info:
                logger.info("[LLM] Post-processing with RefinerEngine")
                processed_result = RefinerEngine.post_process_result(llm_json, ocr_result)

                # Track token usage for cost monitoring
                if response.usage:
                    processed_result["_token_usage"] = {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens
                    }
                    logger.info(f"[LLM] Token usage: {processed_result['_token_usage']}")

                # CRITICAL FIX: Always attach beta content when Beta mode is enabled
                # This ensures the UI shows content even if LayoutParser fails
                if use_optimized_prompt:
                    processed_result["_beta_parsed_content"] = content_text
                    logger.info(f"[LLM-Beta] Attached parsed content for UI (length: {len(content_text)})")

                    if ref_map:
                        processed_result["_beta_ref_map"] = ref_map
                        logger.info(f"[LLM-Beta] Attached ref_map with {len(ref_map)} entries")

                return processed_result

            # For non-model extraction: also attach beta content if enabled
            if use_optimized_prompt:
                llm_json["_beta_parsed_content"] = content_text
                if ref_map:
                    llm_json["_beta_ref_map"] = ref_map
            return llm_json

        except Exception as e:
            import traceback
            traceback.print_exc()
            error_msg = str(e).lower()
            last_error = str(e)
            logger.error(f"[LLM] Error (attempt {attempt+1}): {last_error}")

            # Check if token limit exceeded — retry with truncated content
            is_token_error = "token" in error_msg or "context_length" in error_msg or "too long" in error_msg
            if is_token_error and attempt < max_retries - 1:
                # Aggressively truncate to half
                current_len = len(user_prompt)
                truncated_len = current_len // 2
                user_prompt = user_prompt[:truncated_len] + "\n\n[... CONTENT TRUNCATED DUE TO TOKEN LIMIT ...]"
                logger.warning(f"[LLM-Beta] Token overflow, retrying with truncated prompt: {current_len} → {len(user_prompt)} chars")
                continue

            # Non-retryable error or final attempt — return error WITH beta data
            error_result = {"error": last_error}
            # CRITICAL: Attach beta data even on error so UI can still show parsed content
            if use_optimized_prompt:
                error_result["_beta_parsed_content"] = content_text
                if ref_map:
                    error_result["_beta_ref_map"] = ref_map
                logger.info(f"[LLM-Beta] Attached beta data to error result for UI visibility")
            return error_result

    # Should not reach here, but safety net
    error_result = {"error": last_error or "Unknown LLM error after retries"}
    if use_optimized_prompt:
        error_result["_beta_parsed_content"] = content_text
        if ref_map:
            error_result["_beta_ref_map"] = ref_map
    return error_result

    # Note: client.close() removed — AsyncAzureOpenAI manages its own connection pool.
    # Calling close() after every request was causing connection issues on retry.


def build_extraction_schema(model_info) -> dict:
    """
    Build a JSON Schema from model fields for Structured Outputs.
    
    Converts ExtractionModel.fields into a JSON Schema that enforces:
    - All field keys are present in the response
    - Each field has value, confidence, and source_text
    - No extra fields allowed (additionalProperties: false)
    
    Returns a schema dict suitable for response_format.json_schema.schema
    """
    # Build per-field schema
    field_properties = {}
    field_keys = []

    for field in model_info.fields:
        key = field.key
        field_keys.append(key)

        if getattr(field, "type", "") in ["table", "list", "array"] and getattr(field, "sub_fields", None):
            sub_props = {}
            sub_req = []
            for sf in field.sub_fields:
                sf_key = sf.get("key", "")
                if sf_key:
                    sub_props[sf_key] = {
                        "type": "object",
                        "properties": {
                            "value": {"type": ["string", "null", "number", "boolean"]},
                            "confidence": {"type": "number"},
                            "source_text": {"type": ["string", "null"]}
                        },
                        "required": ["value", "confidence", "source_text"],
                        "additionalProperties": False
                    }
                    sub_req.append(sf_key)
            
            value_type = {
                "type": ["array", "null"],
                "items": {
                    "type": "object",
                    "properties": sub_props,
                    "required": sub_req,
                    "additionalProperties": False
                }
            }
        else:
            value_type = _map_field_type(field.type)

        field_properties[key] = {
            "type": "object",
            "properties": {
                "value": value_type,
                "confidence": {"type": "number"},
                "source_text": {"type": ["string", "null"]},
            },
            "required": ["value", "confidence", "source_text"],
            "additionalProperties": False,
        }

    schema = {
        "type": "object",
        "properties": field_properties,
        "required": field_keys,
        "additionalProperties": False,
    }

    logger.info(f"[Schema] Built extraction schema with {len(field_keys)} fields: {field_keys}")
    return schema


def _map_field_type(field_type: str) -> dict:
    """Map FieldDefinition.type to JSON Schema value type."""
    type_map = {
        "string": {"type": ["string", "null"]},
        "number": {"type": ["number", "null"]},
        "integer": {"type": ["integer", "null"]},
        "boolean": {"type": ["boolean", "null"]},
        "date": {"type": ["string", "null"]},
        "array": {"type": ["array", "null"], "items": {"type": "string"}},
        "table": {"type": ["array", "null"], "items": {"type": "object"}},
    }
    return type_map.get(field_type, {"type": ["string", "null"]})


async def call_llm_single(
    system_prompt: str,
    user_prompt: str,
    model_info=None,
) -> dict:
    """
    Stateless single LLM call with optional Structured Outputs.
    Automatically routes to azure-ai-inference for non-OpenAI models (Claude, Llama, etc.).
    
    Args:
        system_prompt: System prompt (e.g. from RefinerEngine.construct_prompt)
        user_prompt: User prompt with document content
        model_info: Optional ExtractionModel. If provided, uses Structured Outputs
                     to enforce field schema at the API level.
    
    Returns:
        On success: {"result": <parsed_json>, "_token_usage": {...}}
        On error: {"error": "<message>"}
    """
    # ── Multi-Model Routing ──
    # Non-OpenAI models (Claude, Llama, Mistral, etc.) use azure-ai-inference SDK
    from app.services.llm_service import is_openai_model
    if not is_openai_model(_current_model):
        return await _call_llm_single_inference(system_prompt, user_prompt, model_info)

    # ── OpenAI Path ──
    client = get_openai_client()

    # Detect table-type models: strict Structured Outputs enforce exact schema.
    # We fall back to json_object ONLY if a table field lacks explicit sub_fields,
    # because we cannot build a strict schema for dynamic column names.
    is_table_model = False
    if model_info and hasattr(model_info, 'fields') and model_info.fields:
        for f in model_info.fields:
            if getattr(f, 'type', '') in ['table', 'list', 'array']:
                if not getattr(f, 'sub_fields', None):
                    is_table_model = True
                    break

    # Build response format
    if is_table_model:
        response_format = {"type": "json_object"}
        logger.info("[LLM-Single] Table model detected — using json_object (no strict schema)")
    elif model_info and hasattr(model_info, 'fields') and model_info.fields:
        try:
            schema = build_extraction_schema(model_info)
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "extraction_result",
                    "strict": True,
                    "schema": schema,
                }
            }
            logger.info(f"[LLM-Single] Using Structured Outputs with {len(model_info.fields)} field schema")
        except Exception as e:
            logger.warning(f"[LLM-Single] Schema build failed, falling back to json_object: {e}")
            response_format = {"type": "json_object"}
    else:
        response_format = {"type": "json_object"}

    # Pick table vs default, then clamp to model's actual limit
    raw_max = settings.LLM_TABLE_MAX_TOKENS if is_table_model else settings.LLM_DEFAULT_MAX_TOKENS
    max_tokens = min(raw_max, MODEL_MAX_COMPLETION_TOKENS)

    try:
        temp = model_info.temperature if model_info and hasattr(model_info, 'temperature') else getattr(settings, 'LLM_DEFAULT_TEMPERATURE', 0.0)
        
        response = await client.chat.completions.create(
            model=_current_model,
            messages=[
                {"role": "system", "content": system_prompt + "\n\nIMPORTANT: Respond with valid JSON only."},
                {"role": "user", "content": user_prompt}
            ],
            response_format=response_format,
            max_completion_tokens=max_tokens,
            temperature=temp,
        )

        result_content = response.choices[0].message.content
        logger.info(f"[LLM-Single] Response received. Length: {len(result_content)}")
        llm_json = json.loads(result_content)

        result = {"result": llm_json}

        if response.usage:
            result["_token_usage"] = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
            logger.info(f"[LLM-Single] Token usage: {result['_token_usage']}")

        return result

    except Exception as e:
        error_msg = str(e)
        logger.error(f"[LLM-Single] Error: {error_msg}")
        return {"error": error_msg}


async def _call_llm_single_inference(
    system_prompt: str,
    user_prompt: str,
    model_info=None,
) -> dict:
    """
    Single LLM call routed through azure-ai-inference for non-OpenAI models.
    Used automatically when the current model is Claude, Llama, Mistral, etc.
    """
    from app.services.llm_service import call_llm_unified

    messages = [
        {"role": "system", "content": system_prompt + "\n\nIMPORTANT: Respond with valid JSON only."},
        {"role": "user", "content": user_prompt}
    ]

    is_table_model = False
    if model_info and hasattr(model_info, 'fields') and model_info.fields:
        for f in model_info.fields:
            if getattr(f, 'type', '') in ['table', 'list', 'array']:
                is_table_model = True
                break

    raw_max = settings.LLM_TABLE_MAX_TOKENS if is_table_model else settings.LLM_DEFAULT_MAX_TOKENS
    max_tokens = min(raw_max, MODEL_MAX_COMPLETION_TOKENS)
    temp = model_info.temperature if model_info and hasattr(model_info, 'temperature') else getattr(settings, 'LLM_DEFAULT_TEMPERATURE', 0.0)

    try:
        result = await call_llm_unified(
            messages=messages,
            model_name=_current_model,
            temperature=temp,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )

        content = result.get("content", "{}")
        logger.info(f"[LLM-Single-Inference] Response received. Length: {len(content)}")

        llm_json = json.loads(content)
        output = {"result": llm_json}

        usage = result.get("usage", {})
        if usage:
            output["_token_usage"] = {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            }
            logger.info(f"[LLM-Single-Inference] Token usage: {output['_token_usage']}")

        return output

    except Exception as e:
        error_msg = str(e)
        logger.error(f"[LLM-Single-Inference] Error: {error_msg}")
        return {"error": error_msg}

async def generate_schema_from_content(content_text: str, tables: List[dict] = None) -> List[dict]:
    """
    Generate a JSON schema (list of fields) based on document content using LLM.
    """
    client = get_openai_client()

    # summarized context
    table_context = ""
    if tables and len(tables) > 0:
        table_context = f"\nDetected {len(tables)} tables. First table headers: {[c['content'] for c in tables[0]['cells'] if c['row_index'] == 0]}"

    system_prompt = """
    You are an expert Data Engineer. Analyze the provided document text and structure.
    Your goal is to suggest a list of data fields that should be extracted from this type of document.
    
    Return a valid JSON object with a single key "fields", which is a list of objects.
    Each object must have:
    - "key": snake_case identifier (e.g., "invoice_number")
    - "label": Human readable name (e.g., "Invoice Number")
    - "type": One of ["string", "number", "date", "currency", "array", "table", "object"]
    - "description": specific description of what this field contains and where it might be found.
    - "sub_fields": ONLY if the type is "array", "list", or "table". This MUST be an array of objects follow the exact same structure `{"key": "...", "label": "...", "type": "...", "description": "..."}`. NEVER use a simple list of strings.
    
    Example:
    {
      "fields": [
        {"key": "total_amount", "label": "Total Amount", "type": "currency", "description": "The final total including tax, usually at the bottom"},
        {
          "key": "items", 
          "label": "Line Items", 
          "type": "table",
          "sub_fields": [
            {"key": "quantity", "label": "Quantity", "type": "number", "description": "Item qty"},
            {"key": "description", "label": "Description", "type": "string", "description": "Item name"}
          ]
        }
      ]
    }
    """

    user_prompt = f"Document Content:\n{content_text[:settings.SCHEMA_GENERATION_MAX_CHARS]}... (truncated)\n{table_context}\n\nSuggest extraction schema."

    try:
        response = await client.chat.completions.create(
            model=_current_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )

        result = json.loads(response.choices[0].message.content)
        return result.get("fields", [])

    except Exception as e:
        logger.warning(f"[LLM] Schema generation failed: {e}")
        return []


async def refine_schema(current_fields: List[dict], instruction: str) -> List[dict]:
    """
    Refine existing schema based on user instruction (e.g. "Rename invoice_id to invoice_number")
    """
    client = get_openai_client()

    system_prompt = """
    You are an expert Data Engineer. You will be given a current JSON schema (list of fields) and a user instruction.
    Your goal is to MODIFY the schema according to the instruction.
    
    You can:
    - Rename keys/labels
    - Add new fields
    - Remove fields
    - Update descriptions or types
    - **Add or Modify Sub-Fields:** If the instruction implies an array of objects (like a Table, List, or Array of items), you MUST add a `sub_fields` array to that field. Every sub-field in `sub_fields` follows the same structure: `{"key": "...", "label": "...", "type": "...", "description": "..."}`.
    
    Return a valid JSON object with a single key "fields", containing the updated list.
    
    Example 1:
    Input Fields: [{"key": "inv_id", "label": "ID", "type": "string"}]
    Instruction: "Change inv_id to invoice_number and add total_amount"
    Output: {
      "fields": [
        {"key": "invoice_number", "label": "Invoice Number", "type": "string", "description": "ID"},
        {"key": "total_amount", "label": "Total Amount", "type": "currency", "description": "Total amount usually found at bottom"}
      ]
    }

    Example 2:
    Input Fields: [{"key": "items", "label": "Line Items", "type": "table"}]
    Instruction: "add line item breakdown with quantity, description, and unit price"
    Output: {
      "fields": [
        {
          "key": "items", 
          "label": "Line Items", 
          "type": "table",
          "sub_fields": [
            {"key": "quantity", "label": "Quantity", "type": "number", "description": "Item qty"},
            {"key": "description", "label": "Description", "type": "string", "description": "Item name"},
            {"key": "unit_price", "label": "Unit Price", "type": "currency", "description": "Price per unit"}
          ]
        }
      ]
    }
    """

    user_prompt = f"""
    Current Fields:
    {json.dumps(current_fields, indent=2)}
    
    Instruction:
    "{instruction}"
    
    Return updated JSON schema.
    """

    try:
        response = await client.chat.completions.create(
            model=_current_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )

        result = json.loads(response.choices[0].message.content)
        return result.get("fields", current_fields)

    except Exception as e:
        logger.warning(f"[LLM] Schema refinement failed: {e}")
        return current_fields

