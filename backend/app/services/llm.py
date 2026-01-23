import json
import logging
from typing import Optional, List
from openai import AsyncAzureOpenAI
import httpx
from app.core.config import settings
from app.schemas.model import ExtractionModel
from app.services.refiner import RefinerEngine
from app.db.cosmos import get_config_container

logger = logging.getLogger(__name__)

# 동적 모델 설정 (어드민에서 변경 가능)
_current_model = settings.AZURE_OPENAI_DEPLOYMENT_NAME
LLM_CONFIG_ID = "llm_config"

def initialize_llm_settings():
    """서버 시작 시 DB에서 설정 로드"""
    global _current_model
    try:
        container = get_config_container()
        if container:
            try:
                item = container.read_item(item=LLM_CONFIG_ID, partition_key=LLM_CONFIG_ID)
                saved_model = item.get("model_name")
                if saved_model:
                    _current_model = saved_model
                    logger.info(f"[LLM] Loaded configuration from DB: {_current_model}")
            except Exception:
                # 설정이 없으면 기본값 사용 (조용히 넘어감)
                logger.info(f"[LLM] No saved configuration found, using default: {_current_model}")
    except Exception as e:
        logger.info(f"[LLM] Failed to initialize settings: {e}")

def set_llm_model(model_name: str):
    """어드민에서 LLM 모델 변경 (DB 저장)"""
    global _current_model
    _current_model = model_name
    logger.info(f"[LLM] Model changed to: {_current_model}")
    
    # DB 저장
    try:
        container = get_config_container()
        if container:
            container.upsert_item({
                "id": LLM_CONFIG_ID,
                "model_name": model_name,
                "updated_at": "now"
            })
            logger.info("[LLM] Configuration saved to DB")
    except Exception as e:
        logger.info(f"[LLM] Failed to save configuration to DB: {e}")

def get_current_model() -> str:
    return _current_model

async def fetch_available_models() -> List[str]:
    """Azure AI Foundry/OpenAI에서 사용 가능한 모델 목록 가져오기"""
    try:
        endpoint = settings.AZURE_OPENAI_ENDPOINT or settings.AZURE_AIPROJECT_ENDPOINT
        endpoint = endpoint.rstrip('/')
        api_key = settings.AZURE_OPENAI_API_KEY
        api_version = settings.AZURE_OPENAI_API_VERSION
        
        models = []
        
        async with httpx.AsyncClient() as client:
            # Try deployments endpoint first (Azure OpenAI standard)
            try:
                deployments_url = f"{endpoint}/openai/deployments?api-version={api_version}"
                response = await client.get(
                    deployments_url,
                    headers={"api-key": api_key},
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    # Get deployment names
                    for dep in data.get("data", []):
                        dep_id = dep.get("id") or dep.get("deployment_id") or dep.get("name")
                        if dep_id:
                            models.append(dep_id)
                    
                    if models:
                        logger.info(f"[LLM] Found {len(models)} deployments: {models}")
                        return models
            except Exception as e:
                logger.debug(f"[LLM] Deployments endpoint failed: {e}")
            
            # Fallback to models endpoint
            try:
                models_url = f"{endpoint}/openai/models?api-version={api_version}"
                response = await client.get(
                    models_url,
                    headers={"api-key": api_key},
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    logger.debug(f"[LLM] Models API raw response: {data}")
                    
                    for m in data.get("data", []):
                        model_id = m.get("id")
                        caps = m.get("capabilities", {})
                        
                        # Include if it has chat_completion OR if no capabilities info (be permissive)
                        if caps.get("chat_completion", False) or not caps:
                            if model_id:
                                models.append(model_id)
                    
                    if models:
                        logger.info(f"[LLM] Found {len(models)} models: {models}")
                        return models
            except Exception as e:
                logger.debug(f"[LLM] Models endpoint failed: {e}")
        
    except Exception as e:
        logger.error(f"[LLM] Error fetching models: {e}")
    
    # Fallback - return empty list
    logger.warning("[LLM] Could not fetch models from Azure API, returning empty list")
    return []

def get_openai_client() -> AsyncAzureOpenAI:
    """Azure AI Foundry 클라이언트 생성"""
    endpoint = settings.AZURE_OPENAI_ENDPOINT or settings.AZURE_AIPROJECT_ENDPOINT
    endpoint = endpoint.rstrip('/')
    api_key = settings.AZURE_OPENAI_API_KEY
    api_version = settings.AZURE_OPENAI_API_VERSION
    
    if not endpoint or not api_key:
        raise ValueError("Azure AI endpoint and API key must be configured")
    
    logger.info(f"[LLM] Endpoint: {endpoint}")
    logger.info(f"[LLM] Model: {_current_model}")
    
    return AsyncAzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=api_version
    )

async def analyze_document_content(
    ocr_result: dict, 
    language: str = "en", 
    model_info: Optional[ExtractionModel] = None
) -> dict:
    """Azure AI Foundry를 통해 문서 내용 분석"""
    client = get_openai_client()
    
    content_text = ocr_result.get("content", "")

    if model_info:
        system_prompt = RefinerEngine.construct_prompt(model_info, language)
    else:
        system_prompt = f"""
        You are an AI assistant. Extract key info in JSON format.
        Language: {language}.
        Return only valid JSON, no markdown or explanation.
        """

    user_prompt = f"Document Text:\n{content_text}"

    try:
        logger.info(f"[LLM] Calling: {_current_model}")
        
        response = await client.chat.completions.create(
            model=_current_model,
            messages=[
                {"role": "system", "content": system_prompt + "\n\nIMPORTANT: Respond with valid JSON only."},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"}
        )
        
        result_content = response.choices[0].message.content
        logger.info(f"[LLM] Response received. Length: {len(result_content)}")
        llm_json = json.loads(result_content)
        
        if model_info:
            logger.info("[LLM] Post-processing with RefinerEngine")
            return RefinerEngine.post_process_result(llm_json, ocr_result)
        
        return llm_json
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        error_msg = str(e)
        logger.info(f"[LLM] Error: {error_msg}")
        return {"error": error_msg}
    
    finally:
        await client.close()

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
    - "type": One of ["string", "number", "date", "currency", "array", "object"]
    - "description": specific description of what this field contains and where it might be found.
    
    Example:
    {
      "fields": [
        {"key": "total_amount", "label": "Total Amount", "type": "currency", "description": "The final total including tax, usually at the bottom"}
      ]
    }
    """
    
    user_prompt = f"Document Content:\n{content_text[:4000]}... (truncated)\n{table_context}\n\nSuggest extraction schema."

    try:
        response = await client.chat.completions.create(
            model=_current_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        return result.get("fields", [])
        
    except Exception as e:
        logger.info(f"[LLM] Schema generation failed: {e}")
        return []
    finally:
        await client.close()


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
    
    Return a valid JSON object with a single key "fields", containing the updated list.
    
    Example:
    Input Fields: [{"key": "inv_id", "label": "ID", "type": "string"}]
    Instruction: "Change inv_id to invoice_number and add total_amount"
    Output: {
      "fields": [
        {"key": "invoice_number", "label": "Invoice Number", "type": "string", "description": "ID"},
        {"key": "total_amount", "label": "Total Amount", "type": "currency", "description": "Total amount usually found at bottom"}
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
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        return result.get("fields", current_fields)
        
    except Exception as e:
        logger.info(f"[LLM] Schema refinement failed: {e}")
        return current_fields
    finally:
        await client.close()

async def compare_images(image_url_1: str, image_url_2: str, custom_instructions: Optional[str] = None, comparison_settings: Optional[dict] = None) -> dict:
    """
    Compare two images using the globally configured LLM (e.g. GPT-4.1).
    Expects data uris or public urls.
    
    Args:
        custom_instructions: Optional specific rules for comparison (e.g. "Ignore font size changes", "Focus on red text")
        comparison_settings: Optional structured settings dict with keys:
            - confidence_threshold: float (0.0-1.0)
            - ignore_position_changes: bool
            - ignore_color_changes: bool
            - ignore_font_changes: bool
            - custom_ignore_rules: Optional[str]
    """
    client = get_openai_client()
    
    # Use configured global model (Admin controlled)
    model = _current_model
    
    # Extract settings with defaults
    conf_threshold = 0.85
    ignore_position = True
    ignore_color = False
    ignore_font = True
    ignore_compression = True  # New: default to ignoring compression noise
    custom_ignore = None
    allowed_cats = None
    excluded_cats = None
    
    if comparison_settings:
        conf_threshold = comparison_settings.get("confidence_threshold", 0.85)
        ignore_position = comparison_settings.get("ignore_position_changes", True)
        ignore_color = comparison_settings.get("ignore_color_changes", False)
        ignore_font = comparison_settings.get("ignore_font_changes", True)
        ignore_compression = comparison_settings.get("ignore_compression_noise", True)
        custom_ignore = comparison_settings.get("custom_ignore_rules")
        allowed_cats = comparison_settings.get("allowed_categories")
        excluded_cats = comparison_settings.get("excluded_categories")
        logger.info(f"[LLM] Using model comparison settings: threshold={conf_threshold}, ignore_position={ignore_position}, categories={allowed_cats or 'default'}")
    
    # Inject Custom Rules if provided
    custom_rules_text = ""
    if custom_instructions:
        custom_rules_text = f"\n\n**USER DEFINED COMPARISON RULES (MUST FOLLOW):**\n{custom_instructions}\n"
    if custom_ignore:
        custom_rules_text += f"\n**ADDITIONAL IGNORE RULES:**\n{custom_ignore}\n"
    
    # Try to load custom system prompt from site settings
    custom_system_prompt = None
    try:
        from app.api.endpoints.site_settings import load_config
        site_config = load_config()
        custom_system_prompt = site_config.get("comparisonSystemPrompt")
        if custom_system_prompt:
            logger.info("[LLM] Using custom comparison system prompt from site settings")
    except Exception as e:
        logger.debug(f"[LLM] Could not load site settings: {e}")
    
    # Build dynamic ignore rules based on settings
    dynamic_ignore_rules = []
    if ignore_position:
        dynamic_ignore_rules.append("- **POSITION/LAYOUT SHIFTS**: If the SAME element exists in BOTH images but at slightly different positions, THIS IS NOT A DIFFERENCE.")
    if ignore_color:
        dynamic_ignore_rules.append("- **COLOR CHANGES**: Ignore color differences unless they significantly change meaning.")
    if ignore_font:
        dynamic_ignore_rules.append("- **FONT CHANGES**: Ignore minor font weight, size, or style differences.")
    if ignore_compression:
        dynamic_ignore_rules.append("""- **IMAGE COMPRESSION ARTIFACTS**: IGNORE any visual differences that could be explained by:
      - JPEG compression artifacts (blocky edges, color banding)
      - Slight RGB value shifts (within ~10 values difference)
      - Anti-aliasing differences on text/element edges
      - Subtle brightness/contrast variations
      - Image re-encoding noise
      - **RULE**: If the difference looks like the SAME color with slight variation, IGNORE IT. Only report if the color is OBVIOUSLY INTENTIONALLY DIFFERENT (e.g., blue→red, yellow→green).""")
    
    dynamic_ignore_text = "\n".join(dynamic_ignore_rules) if dynamic_ignore_rules else ""
    
    # Build category list dynamically
    default_categories = ["content", "layout", "style", "missing_element", "added_element"]
    if allowed_cats:
        active_categories = allowed_cats
    elif excluded_cats:
        active_categories = [c for c in default_categories if c not in excluded_cats]
    else:
        active_categories = default_categories
    
    categories_str = json.dumps(active_categories)
    
    # If custom system prompt exists in site settings, use it; otherwise use default
    if custom_system_prompt:
        system_prompt = custom_system_prompt + custom_rules_text
    else:
        system_prompt = f"""
    You are an expert QA and Visual Inspection AI.
    Compare the two provided images (Baseline vs Candidate) and identify semantic and visual differences.

    **Chain-of-Thought Process (Internal Monologue):**
    1.  **Analyze Layout**: First, look at the overall structure (header, body, footer) of both images. note any shifts or resizing.
    2.  **Scan for Content**: Read the text in both images. Identify changed numbers, typo fixes, or modified sentences.
    3.  **Check Elements**: Look for missing or added UI elements (buttons, icons, lines).
    4.  **Filter Noise**: Ignore minor pixel-level anti-aliasing differences, JPEG compression artifacts, or slight font rendering weight changes unless they affect legibility.
    5.  **Apply Custom Rules**: Strictly apply the user-defined comparison rules if provided below.
    6.  **Validation**: If a difference is too subtle or ambiguous, discard it. Do NOT hallucinate differences.
    7.  **Formulate Output**: Create the JSON output for each valid difference.

    {custom_rules_text}

    Return a JSON object with a key "differences" containing a list of objects.
    Each difference object must have:
    - "id": unique integer (1, 2, 3...)
    - "description": concise text describing the change in **KOREAN** (한국어로 설명). Example: "헤더의 'Invoice' 텍스트가 'Tax Invoice'로 변경됨" or "우측 상단에 '결재' 버튼이 추가됨".
    - "category": one of {categories_str}
    - "confidence": float between 0.0 and 1.0.
      - **0.9 - 1.0**: Absolutely certain (text clearly changed, element clearly added/removed).
      - **0.85 - 0.89**: Very likely a real difference.
      - **< 0.85**: DO NOT REPORT. Discard these entirely.
    - "location_1": bounding box in Baseline image as [y_min, x_min, y_max, x_max] (0-1000 scale). Null if added_element.
    - "location_2": bounding box in Candidate image as [y_min, x_min, y_max, x_max] (0-1000 scale). Null if missing_element.
    - "page_number": integer (1-based), default to 1.
    
    **CRITICAL BOUNDING BOX FORMAT:**
    - Coordinates are normalized to 0-1000 scale (0=top-left origin, 1000=bottom-right).
    - Format: [y_min, x_min, y_max, x_max] where:
      - y_min: distance from TOP edge (0 = very top)
      - x_min: distance from LEFT edge (0 = very left)
      - y_max: distance from TOP edge (must be > y_min)
      - x_max: distance from LEFT edge (must be > x_min)
    
    **CRITICAL RULES - READ CAREFULLY:**
    1. **ABSOLUTELY NO HALLUCINATION**: If the images look identical or nearly identical, return EMPTY "differences" list. Do NOT invent differences.
    2. **IDENTICAL = EMPTY LIST**: If after careful analysis you find NO meaningful differences, respond with: {{"differences": []}}
    3. **HIGH CONFIDENCE ONLY**: Only report differences with confidence >= 0.85. Anything below is NOISE.
    4. **IGNORE NOISE**: Do not report:
       - Slight color variations due to image compression
       - Anti-aliasing differences on text edges
       - Minor font weight/rendering differences
       - Subtle shadow or gradient differences
       - **POSITION/LAYOUT SHIFTS**: If the SAME element exists in BOTH images but at slightly different positions, THIS IS NOT A DIFFERENCE. Do NOT report it.
       - **Alignment variations**: Same content with minor alignment or spacing differences is NOT a difference.
    5. **REAL DIFFERENCES ONLY**: Only report if you can clearly describe WHAT text changed, WHAT element was added/removed. Position shifts of identical content are NOT real differences.
    6. **VALIDATE BEFORE REPORTING**: Ask yourself "Can a human clearly see this difference?" and "Is the CONTENT actually different, not just the position?" If no to either, DO NOT REPORT.
    7. **POSITION IS NOT CONTENT**: Moving an element from left to right, or top to bottom, is NOT a content difference. Only report if the TEXT, IMAGE, or MEANING has changed.
    """
    
    user_message_content = [
        {"type": "text", "text": "Compare these two images. Image 1 is Baseline. Image 2 is Candidate."},
        {
            "type": "image_url",
            "image_url": {"url": image_url_1}
        },
        {
            "type": "image_url",
            "image_url": {"url": image_url_2}
        }
    ]

    try:
        logger.info(f"[LLM] Comparing images using {model}...")
        
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message_content}
            ],
            response_format={"type": "json_object"},
            max_tokens=2000
        )
        
        result_content = response.choices[0].message.content
        return json.loads(result_content)
        
    except Exception as e:
        logger.info(f"[LLM] Comparison failed: {e}")
        return {"differences": [], "error": str(e)}
    finally:
        await client.close()
