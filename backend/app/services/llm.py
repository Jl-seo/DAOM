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
    Compare two images using the 3-Layer Component-Based Architecture:
    1. Physical Layer: SSIM (Structural Similarity)
    2. Visual Layer: Azure AI Vision (Color, Objects)
    3. Structural/Semantic Layer: GPT-4o Synthesis
    """
    client = get_openai_client()
    model = _current_model
    
    # Defaults
    conf_threshold = 0.85
    ignore_position = True
    output_language = "Korean"
    use_ssim = True
    use_vision = True
    
    if comparison_settings:
        conf_threshold = comparison_settings.get("confidence_threshold", 0.85)
        ignore_position = comparison_settings.get("ignore_position_changes", True)
        output_language = comparison_settings.get("output_language", "Korean")
        use_ssim = comparison_settings.get("use_ssim_analysis", True)
        use_vision = comparison_settings.get("use_vision_analysis", True)

    logger.info(f"[LLM] Comparison {model} | SSIM={use_ssim} | Vision={use_vision}")

    # 1. Parallel Data Collection (SSIM + Vision)
    from app.services import pixel_diff
    from app.services.vision_service import VisionService
    import asyncio

    tasks = []
    
    # Task A: SSIM Analysis (Physical)
    if use_ssim:
        tasks.append(pixel_diff.calculate_ssim(image_url_1, image_url_2))
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
    
    # 2. Construct Synthesis Context
    ssim_context = ""
    if ssim_diffs:
        ssim_context = f"**PHYSICAL LAYER (SSIM)**: Detected {len(ssim_diffs)} areas with low structural similarity. These indicate POTENTIAL changes.\n"
        for i, d in enumerate(ssim_diffs[:5]):
            ssim_context += f"- Diff #{i}: score={d.get('diff_score',0)}, bbox={d['bbox']}\n"
    else:
         ssim_context = "**PHYSICAL LAYER (SSIM)**: Images are structurally IDENTICAL (High Similarity).\n"

    vision_context = f"""
    **VISUAL LAYER (Azure Vision)**:
    - Baseline Image Details:
    {vision_1}
    
    - Candidate Image Details:
    {vision_2}
    """

    # 3. GPT-4o Synthesis Prompt
    category_list = ["content", "layout", "style", "missing_element", "added_element"]
    categories_str = json.dumps(category_list)
    
    system_prompt = f"""
    You are an expert Visual QA Auditor utilizing a 3-Layer Analysis Pipeline.
    
    **INPUT DATA**:
    1. {ssim_context}
    2. {vision_context}
    3. **VISUAL INSPECTION**: You will see the two images directly.

    **GOAL**: Synthesize these signals to find verifyable differences.
    
    **LOGIC CHAIN**:
    1. **Check SSIM**: If SSIM says "IDENTICAL", be very skeptical of any hallucinated differences.
    2. **Check Vision**: Compare Tags/Captions. If Baseline has "Red Logo" and Candidate has "Blue Logo", that is a CONFIRMED diff.
    3. **Visual Audit**: Look at the images yourself.
       - If SSIM highlights a region, zoom in on that region.
       - If Text matches but SSIM failed, check for **Color/Style** changes (which SSIM detects but OCR might ignore).
    
    **IGNORE RULES**:
    - Ignore position shifts if text is identical (unless `ignore_position_changes` is False).
    - Ignore compression noise.
    
    {custom_instructions or ""}

    Return JSON:
    {{
        "differences": [
            {{
                "id": "1",
                "description": "Description in {output_language}",
                "category": "category",
                "confidence": 0.95,
                "location_1": [y1, x1, y2, x2] (0-1000 scale)
            }}
        ]
    }}
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
        
        # Inject metadata
        data["metadata"] = {
            "model": model,
            "method": "3_layer_component_arch",
            "ssim_count": len(ssim_diffs),
            "vision_enabled": use_vision
        }
        return data

    except Exception as e:
        logger.error(f"[LLM] Comparison synthesis failed: {e}")
        return {"differences": [], "error": str(e)}
    finally:
        await client.close()

