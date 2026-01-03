import json
from typing import Optional, List
from openai import AsyncAzureOpenAI
import httpx
from app.core.config import settings
from app.schemas.model import ExtractionModel
from app.services.refiner import RefinerEngine

# 동적 모델 설정 (어드민에서 변경 가능)
_current_model = settings.AZURE_OPENAI_DEPLOYMENT_NAME

def set_llm_model(model_name: str):
    """어드민에서 LLM 모델 변경"""
    global _current_model
    _current_model = model_name
    print(f"[LLM] Model changed to: {_current_model}")

def get_current_model() -> str:
    return _current_model

async def fetch_available_models() -> List[str]:
    """Azure AI Foundry에서 사용 가능한 채팅 모델 목록 가져오기"""
    try:
        endpoint = settings.AZURE_OPENAI_ENDPOINT or settings.AZURE_AIPROJECT_ENDPOINT
        endpoint = endpoint.rstrip('/')
        api_key = settings.AZURE_OPENAI_API_KEY
        
        url = f"{endpoint}/openai/models?api-version={settings.AZURE_OPENAI_API_VERSION}"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers={"api-key": api_key},
                timeout=10.0
            )
            
            if response.status_code == 200:
                data = response.json()
                # chat_completion 가능한 모델만 필터링
                models = [
                    m["id"] for m in data.get("data", [])
                    if m.get("capabilities", {}).get("chat_completion", False)
                ]
                print(f"[LLM] Found {len(models)} chat models: {models[:5]}...")
                return models
    except Exception as e:
        print(f"[LLM] Error fetching models: {e}")
    
    # Fallback
    return ["gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini"]

def get_openai_client() -> AsyncAzureOpenAI:
    """Azure AI Foundry 클라이언트 생성"""
    endpoint = settings.AZURE_OPENAI_ENDPOINT or settings.AZURE_AIPROJECT_ENDPOINT
    endpoint = endpoint.rstrip('/')
    api_key = settings.AZURE_OPENAI_API_KEY
    api_version = settings.AZURE_OPENAI_API_VERSION
    
    if not endpoint or not api_key:
        raise ValueError("Azure AI endpoint and API key must be configured")
    
    print(f"[LLM] Endpoint: {endpoint}")
    print(f"[LLM] Model: {_current_model}")
    
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
        print(f"[LLM] Calling: {_current_model}")
        
        response = await client.chat.completions.create(
            model=_current_model,
            messages=[
                {"role": "system", "content": system_prompt + "\n\nIMPORTANT: Respond with valid JSON only."},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"}
        )
        
        result_content = response.choices[0].message.content
        print(f"[LLM] Response received. Length: {len(result_content)}")
        llm_json = json.loads(result_content)
        
        if model_info:
            print("[LLM] Post-processing with RefinerEngine")
            return RefinerEngine.post_process_result(llm_json, ocr_result)
        
        return llm_json
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        error_msg = str(e)
        print(f"[LLM] Error: {error_msg}")
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
        print(f"[LLM] Schema generation failed: {e}")
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
        print(f"[LLM] Schema refinement failed: {e}")
        return current_fields
    finally:
        await client.close()
