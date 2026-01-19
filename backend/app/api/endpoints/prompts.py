"""
Prompts API - Manage system prompts
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.services.prompt_service import (
    get_prompt,
    get_all_prompts,
    save_prompt,
    reset_prompt
)

router = APIRouter(prefix="/settings/prompts", tags=["prompts"])


class PromptResponse(BaseModel):
    id: str
    content: str
    description: str
    variables: list
    is_default: bool
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None


class PromptUpdateRequest(BaseModel):
    content: str
    description: Optional[str] = ""


@router.get("")
async def list_prompts():
    """Get all system prompts"""
    prompts = await get_all_prompts()
    return {"prompts": prompts}


@router.get("/{key}")
async def get_prompt_by_key(key: str):
    """Get a specific prompt by key"""
    prompt = await get_prompt(key)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return prompt


@router.put("/{key}")
async def update_prompt(key: str, request: PromptUpdateRequest):
    """Update a prompt"""
    success = await save_prompt(
        key=key,
        content=request.content,
        description=request.description or ""
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save prompt")
    
    prompt = await get_prompt(key)
    return {"success": True, "prompt": prompt}


@router.post("/{key}/reset")
async def reset_prompt_to_default(key: str):
    """Reset a prompt to its default value"""
    success = await reset_prompt(key)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to reset prompt")
    
    prompt = await get_prompt(key)
    return {"success": True, "prompt": prompt}
