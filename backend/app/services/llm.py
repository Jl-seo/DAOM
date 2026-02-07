import json
import logging
from typing import Optional, List
from openai import AsyncAzureOpenAI
import httpx
from app.core.config import settings
from app.core.enums import DEFAULT_COMPARISON_CATEGORIES
from app.schemas.model import ExtractionModel
from app.services.refiner import RefinerEngine
from app.services.layout_parser import LayoutParser
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
            grid = {}
            for cell in cells:
                r = cell.get("rowIndex", 0)
                c = cell.get("columnIndex", 0)
                content = cell.get("content", "").replace("\n", " ")
                if r < 20: # Limit rows
                    if r not in grid: grid[r] = {}
                    grid[r][c] = content
            
            # Render rows
            for r in sorted(grid.keys()):
                row_cells = grid[r]
                row_str = " | ".join([row_cells.get(c, "") for c in range(col_count)])
                tables_context += f"| {row_str} |\n"
            
            if row_count > 20:
                tables_context += f"... ({row_count - 20} more rows) ...\n"

    user_prompt = f"Document Text:\n{content_text}\n{tables_context}"

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
    Compare two images using the 3-Layer Component-Based Architecture:
    1. Physical Layer: SSIM (Structural Similarity)
    2. Visual Layer: Azure AI Vision (Color, Objects)
    3. Structural/Semantic Layer: GPT-4o Synthesis
    """
    client = get_openai_client()
    model = _current_model
    
    # 설정값 기본값 (UI에서 전달되지 않으면 사용)
    conf_threshold = 0.85
    ignore_position = True
    ignore_color = False
    ignore_font = True
    ignore_compression_noise = True
    output_language = "Korean"
    use_ssim = True
    use_vision = True
    align_images = True
    custom_ignore_rules = None  # 추가 무시 규칙 (자연어)
    
    # comparison_settings에서 설정값 읽기 (UI에서 전달된 값 우선)
    if comparison_settings:
        conf_threshold = comparison_settings.get("confidence_threshold", 0.85)
        ignore_position = comparison_settings.get("ignore_position_changes", True)
        ignore_color = comparison_settings.get("ignore_color_changes", False)
        ignore_font = comparison_settings.get("ignore_font_changes", True)
        ignore_compression_noise = comparison_settings.get("ignore_compression_noise", True)
        output_language = comparison_settings.get("output_language", "Korean")
        use_ssim = comparison_settings.get("use_ssim_analysis", True)
        use_vision = comparison_settings.get("use_vision_analysis", True)
        align_images = comparison_settings.get("align_images", True)
        custom_ignore_rules = comparison_settings.get("custom_ignore_rules")
    
    # custom_instructions (global_rules)와 custom_ignore_rules 합치기
    combined_instructions = []
    if custom_instructions:
        combined_instructions.append(f"GLOBAL RULES: {custom_instructions}")
    if custom_ignore_rules:
        combined_instructions.append(f"CUSTOM IGNORE RULES (자연어): {custom_ignore_rules}")
    
    final_custom_instructions = "\n".join(combined_instructions) if combined_instructions else None
    
    logger.info(f"[LLM] Comparison {model} | SSIM={use_ssim} | Vision={use_vision}")
    logger.info(f"[LLM] Settings: ignore_position={ignore_position}, ignore_color={ignore_color}, ignore_font={ignore_font}, ignore_noise={ignore_compression_noise}")
    if final_custom_instructions:
        logger.info(f"[LLM] Custom instructions: {final_custom_instructions[:100]}...")

    # 1. Parallel Data Collection (SSIM + Vision)
    from app.services import pixel_diff
    from app.services.vision_service import VisionService
    import asyncio

    tasks = []
    
    # Task A: SSIM Analysis (Physical)
    if use_ssim:
        tasks.append(pixel_diff.calculate_ssim(image_url_1, image_url_2, align=align_images))
    else:
        # Dummy task returning []
        async def no_op(): return []
        tasks.append(no_op())

    # Task B: Vision Analysis (Visual Semantics)
    # Wrap sync call in thread or async wrapper
    async def analyze_vision(url):
        if not use_vision: return "Vision Analysis Disabled"
        return await asyncio.to_thread(VisionService.analyze_image, url)

    tasks.append(analyze_vision(image_url_1))
    tasks.append(analyze_vision(image_url_2))

    # Execute Parallel
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    ssim_diffs = results[0] if isinstance(results[0], list) else []
    vision_1 = results[1] if isinstance(results[1], str) else "Error"
    vision_2 = results[2] if isinstance(results[2], str) else "Error"
    
    # Fast path: SSIM이 동일하면 LLM 호출 없이 즉시 빈 결과 반환 (hallucination 방지)
    # 설정에서 skip_llm_if_identical 옵션으로 제어 가능 (기본: True)
    skip_llm_if_identical = comparison_settings.get("skip_llm_if_identical", True) if comparison_settings else True
    
    if not ssim_diffs and use_ssim and skip_llm_if_identical:
        logger.info("[LLM] SSIM confirms images are IDENTICAL. Skipping LLM call to prevent hallucination.")
        return {
            "differences": [],
            "metadata": {
                "model": model,
                "method": "ssim_fast_path",
                "ssim_count": 0,
                "vision_enabled": use_vision,
                "skipped_llm": True,
                "reason": "Images are identical (SSIM)"
            }
        }
    
    # 2. Construct Synthesis Context
    ssim_context = ""
    ssim_identical = False
    if ssim_diffs:
        ssim_context = f"**PHYSICAL LAYER (SSIM)**: Detected {len(ssim_diffs)} areas with low structural similarity. These indicate POTENTIAL changes.\n"
        for i, d in enumerate(ssim_diffs[:5]):
            ssim_context += f"- Diff #{i}: score={d.get('diff_score',0)}, bbox={d['bbox']}\n"
    else:
        ssim_identical = True
        ssim_context = """**PHYSICAL LAYER (SSIM)**: Images are structurally IDENTICAL (High Similarity).
        
⚠️ CRITICAL: Since SSIM analysis confirms the images are IDENTICAL, you should NOT report any differences.
If you cannot find clear, obvious, and verifiable differences, return an EMPTY differences array."""

    vision_context = f"""
    **VISUAL LAYER (Azure Vision)**:
    - Baseline Image Details:
    {vision_1}
    
    - Candidate Image Details:
    {vision_2}
    """

    # 3. GPT-4o Synthesis Prompt
    # Build dynamic category list based on user settings
    default_categories = DEFAULT_COMPARISON_CATEGORIES
    allowed_categories = comparison_settings.get("allowed_categories") if comparison_settings else None
    excluded_categories = comparison_settings.get("excluded_categories") if comparison_settings else None
    
    if allowed_categories:
        # Only use specified categories
        category_list = [c for c in allowed_categories if c in default_categories]
    elif excluded_categories:
        # Remove excluded categories
        category_list = [c for c in default_categories if c not in excluded_categories]
    else:
        # Use all defaults
        category_list = default_categories
    
    categories_str = json.dumps(category_list)
    
    # Build category instruction (강화된 지시)
    if allowed_categories:
        category_instruction = f"""**ABSOLUTE REQUIREMENT**: You MUST ONLY report differences in these categories: {categories_str}. 
        ANY difference not in this list MUST be completely ignored - do NOT include them in your response under any circumstances."""
    elif excluded_categories:
        category_instruction = f"""**ABSOLUTE REQUIREMENT**: You MUST COMPLETELY IGNORE and NEVER report differences in these categories: {json.dumps(excluded_categories)}. 
        Even if you detect changes in {json.dumps(excluded_categories)}, you MUST NOT include them in your response. 
        ONLY report differences in: {categories_str}."""
    else:
        category_instruction = f"You may report differences in any of these categories: {categories_str}."
    
    # 추가: SSIM이 동일하면 hallucination 방지 강화
    anti_hallucination_instruction = ""
    if ssim_identical:
        anti_hallucination_instruction = """
    
    ⚠️ ANTI-HALLUCINATION WARNING ⚠️
    The SSIM analysis has CONFIRMED these images are IDENTICAL at the pixel level.
    
    DO NOT invent or imagine differences that don't exist.
    DO NOT report minor variations that are likely compression artifacts.
    DO NOT report differences you are not 100% certain about.
    
    If you cannot find CLEAR, OBVIOUS, and VERIFIABLE differences, you MUST return:
    {"differences": []}
    
    Only report a difference if you can see an UNMISTAKABLE change with your own visual inspection.
    When in doubt, do NOT report it."""
    
    # IGNORE RULES를 설정값에 따라 동적으로 생성
    ignore_rules_list = []
    if ignore_position:
        ignore_rules_list.append("- IGNORE position shifts if text content is identical")
    if ignore_color:
        ignore_rules_list.append("- IGNORE color changes (배경 색, 글자 색 차이 무시)")
    if ignore_font:
        ignore_rules_list.append("- IGNORE font style changes (폰트 크기, 굵기 차이 무시)")
    if ignore_compression_noise:
        ignore_rules_list.append("- IGNORE compression artifacts and minor pixel noise")
    ignore_rules_list.append("- IGNORE anything you are not certain about")
    
    ignore_rules_text = "\n    ".join(ignore_rules_list)
    
    system_prompt = f"""
    You are an expert Visual QA Auditor utilizing a 3-Layer Analysis Pipeline.
    
    **INPUT DATA**:
    1. {ssim_context}
    2. {vision_context}
    3. **VISUAL INSPECTION**: You will see the two images directly.

    **GOAL**: Synthesize these signals to find verifiable differences. Do NOT hallucinate or invent differences.
    
    {category_instruction}
    {anti_hallucination_instruction}
    
    **TEXT/NUMBER ACCURACY**:
    - Read text and numbers carefully. Do not skip digits (e.g., "140" ≠ "40").
    - If both images show the same text, do NOT report it as a difference.
    
    **LOGIC CHAIN**:
    1. **Check SSIM**: If SSIM says "IDENTICAL", you should almost certainly return an empty differences array.
    2. **Check Vision**: Compare Tags/Captions. Only report if there's a CLEAR mismatch.
    3. **Visual Audit**: Look at the images yourself.
       - If SSIM highlights a region, zoom in on that region.
       - If you're not 100% sure about a difference, DO NOT REPORT IT.
    
    **IGNORE RULES** (MUST FOLLOW):
    {ignore_rules_text}
    
    {final_custom_instructions or ""}

    Return JSON:
    {{
        "differences": [
            {{
                "id": "1",
                "description": "Description in {output_language}",
                "category": "One of {categories_str} (ALWAYS English)",
                "confidence": 0.95,
                "location_1": [y1, x1, y2, x2] (0-1000 scale)
            }}
        ]
    }}
    
    IMPORTANT: 
    - "category" MUST be one of the English keys in {categories_str}. DO NOT translate the category.
    - "description" MUST be in {output_language}.
    - If images are identical, return {{"differences": []}}
    - DO NOT report text differences unless you are 100% certain you read both texts correctly.
    """

    user_message = [
        {"type": "text", "text": "Compare these images using the 3-Layer Pipeline."},
        {"type": "image_url", "image_url": {"url": image_url_1}},
        {"type": "image_url", "image_url": {"url": image_url_2}}
    ]

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            response_format={"type": "json_object"},
            max_tokens=2000
        )
        
        result_content = response.choices[0].message.content
        data = json.loads(result_content)
        
        # Post-process 1: Filter by confidence threshold (낮은 확신도 차이점 제거)
        if "differences" in data and isinstance(data["differences"], list):
            before_conf_count = len(data["differences"])
            data["differences"] = [
                d for d in data["differences"] 
                if d.get("confidence", 0) >= conf_threshold
            ]
            after_conf_count = len(data["differences"])
            if before_conf_count != after_conf_count:
                logger.info(f"[LLM] Confidence filter: {before_conf_count} -> {after_conf_count} (threshold: {conf_threshold})")
        
        # Post-process 2: Filter out excluded categories (LLM 지시 무시 대비 안전장치)
        if "differences" in data and isinstance(data["differences"], list):
            original_count = len(data["differences"])
            
            if allowed_categories:
                # Only keep differences in allowed categories
                data["differences"] = [
                    d for d in data["differences"] 
                    if d.get("category", "").lower() in [c.lower() for c in category_list]
                ]
            elif excluded_categories:
                # Remove differences in excluded categories
                excluded_lower = [c.lower() for c in excluded_categories]
                data["differences"] = [
                    d for d in data["differences"] 
                    if d.get("category", "").lower() not in excluded_lower
                ]
            
            filtered_count = len(data["differences"])
            if original_count != filtered_count:
                logger.info(f"[LLM] Category filter: {original_count} -> {filtered_count} differences")
        
        # Inject metadata
        data["metadata"] = {
            "model": model,
            "method": "3_layer_component_arch",
            "ssim_count": len(ssim_diffs),
            "vision_enabled": use_vision,
            "category_filter_applied": bool(allowed_categories or excluded_categories),
            "confidence_threshold": conf_threshold
        }
        return data

    except Exception as e:
        logger.error(f"[LLM] Comparison synthesis failed: {e}")
        return {"differences": [], "error": str(e)}
    finally:
        await client.close()

