from fastapi import APIRouter
from pydantic import BaseModel
from typing import List
from app.services.llm import set_llm_model, get_current_model, fetch_available_models
from app.core.config import settings

router = APIRouter()

class LLMSettingsResponse(BaseModel):
    current_model: str
    available_models: List[str]
    endpoint: str

class UpdateLLMModelRequest(BaseModel):
    model_name: str

@router.get("/llm", response_model=LLMSettingsResponse)
async def get_llm_settings():
    """현재 LLM 설정 조회 및 사용 가능한 모델 목록"""
    available_models = await fetch_available_models()
    
    # 현재 모델이 목록에 없으면 추가
    current = get_current_model()
    if current and current not in available_models:
        available_models.insert(0, current)
    
    return LLMSettingsResponse(
        current_model=current,
        available_models=available_models,
        endpoint=settings.AZURE_OPENAI_ENDPOINT or settings.AZURE_AIPROJECT_ENDPOINT
    )

@router.put("/llm")
async def update_llm_model(request: UpdateLLMModelRequest):
    """LLM 모델 변경"""
    set_llm_model(request.model_name)
    return {
        "success": True,
        "message": f"Model changed to {request.model_name}",
        "current_model": get_current_model()
    }
