"""
Template API endpoints
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Any
from app.services.template_chat import process_template_chat

router = APIRouter()


class TemplateChatRequest(BaseModel):
    message: str
    currentConfig: dict[str, Any] = {}
    modelFields: list[dict[str, Any]] = []


class TemplateChatResponse(BaseModel):
    message: str
    config: dict[str, Any]


@router.post("/chat", response_model=TemplateChatResponse)
async def chat_template(request: TemplateChatRequest):
    """
    Process natural language request and update template configuration
    """
    result = await process_template_chat(
        message=request.message,
        current_config=request.currentConfig,
        model_fields=request.modelFields
    )
    return TemplateChatResponse(**result)
