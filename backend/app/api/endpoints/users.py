"""
Users API endpoints - User management and role assignment
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.core.auth import get_current_user, CurrentUser
from app.core.permissions import require_admin
from app.services import user_service, startup_service

import logging

router = APIRouter()
logger = logging.getLogger(__name__)


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    role: str
    tenant_id: str
    created_at: str
    last_login: str
    groups: list[str]


class UpdateRoleRequest(BaseModel):
    role: str  # Admin, Editor, Viewer


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: CurrentUser = Depends(get_current_user)):
    """
    Get current user info (auto-registers on first login)
    Also seeds System Admins group for the tenant if not exists
    """
    # Seed System Admins group for this tenant and auto-add if in INITIAL_ADMIN_EMAILS
    try:
        await startup_service.run_startup_tasks(
            tenant_id=current_user.tenant_id,
            current_user_email=current_user.email,
            current_user_id=current_user.id,
            current_user_name=current_user.name
        )
    except Exception as e:
        # Don't block login if startup tasks fail
        logger.error(f"Failed to run startup tasks: {e}")
    
    user = await user_service.get_or_create_user(current_user)
    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        tenant_id=user.tenant_id,
        created_at=user.created_at,
        last_login=user.last_login,
        groups=user.groups
    )


@router.get("/", response_model=list[UserResponse])
async def list_users(
    search: Optional[str] = None,
    current_user: CurrentUser = Depends(require_admin)
):
    """
    List all users in tenant (Admin only)
    """
    users = await user_service.get_users_by_tenant(current_user.tenant_id, search_term=search)
    return [
        UserResponse(
            id=u.id,
            email=u.email,
            name=u.name,
            role=u.role,
            tenant_id=u.tenant_id,
            created_at=u.created_at,
            last_login=u.last_login,
            groups=u.groups
        )
        for u in users
    ]


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    current_user: CurrentUser = Depends(require_admin)
):
    """
    Get specific user info (Admin only)
    """
    user = await user_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        tenant_id=user.tenant_id,
        created_at=user.created_at,
        last_login=user.last_login,
        groups=user.groups
    )


@router.put("/{user_id}/role")
async def update_user_role(
    user_id: str,
    request: UpdateRoleRequest,
    current_user: CurrentUser = Depends(require_admin)
):
    """
    Update user's role (Admin only)
    """
    success = await user_service.update_user_role(
        user_id, 
        request.role, 
        current_user.tenant_id
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="Failed to update role")
    
    return {"success": True, "message": f"Role updated to {request.role}"}
