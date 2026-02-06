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
    isSuperAdmin: bool = False  # Whether user has Super Admin privileges


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
    
    # Check if user is Super Admin
    from app.core.auth import is_super_admin
    is_super = await is_super_admin(current_user)
    
    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        tenant_id=user.tenant_id,
        created_at=user.created_at,
        last_login=user.last_login,
        groups=user.groups,
        isSuperAdmin=is_super
    )


@router.get("/", response_model=list[UserResponse])
async def list_users(
    search: Optional[str] = None,
    all_tenants: bool = False,
    current_user: CurrentUser = Depends(require_admin)
):
    """
    List users (Admin only)
    - all_tenants=False: 현재 테넌트의 사용자만 (기본)
    - all_tenants=True: 모든 테넌트의 사용자 (Super Admin 전용)
    """
    from app.core.auth import is_super_admin
    
    if all_tenants:
        # Super Admin 권한 체크
        if not await is_super_admin(current_user):
            raise HTTPException(status_code=403, detail="Super Admin 권한이 필요합니다")
        users = await user_service.get_all_users(search_term=search)
    else:
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


class BulkUserEntry(BaseModel):
    email: str
    name: str
    groups: list[str] = []  # Group names


class BulkImportRequest(BaseModel):
    users: list[BulkUserEntry]


class BulkImportResult(BaseModel):
    total: int
    created: int
    updated: int
    failed: int
    errors: list[str] = []


@router.post("/bulk-import", response_model=BulkImportResult)
async def bulk_import_users(
    request: BulkImportRequest,
    current_user: CurrentUser = Depends(require_admin)
):
    """
    Bulk import users (Admin only)
    
    Accepts a list of users with email, name, and optional group names.
    Creates new users or updates existing ones.
    Processes in batches of 100 for performance.
    """
    from app.services import group_service
    from datetime import datetime
    
    result = BulkImportResult(
        total=len(request.users),
        created=0,
        updated=0,
        failed=0,
        errors=[]
    )
    
    # Pre-load groups for name lookup
    all_groups = await group_service.get_groups_by_tenant(current_user.tenant_id)
    group_name_to_id = {g.name.lower(): g.id for g in all_groups}
    
    # Process in batches
    BATCH_SIZE = 100
    for i in range(0, len(request.users), BATCH_SIZE):
        batch = request.users[i:i + BATCH_SIZE]
        
        for user_entry in batch:
            try:
                # Map group names to IDs
                group_ids = []
                for gname in user_entry.groups:
                    gid = group_name_to_id.get(gname.lower())
                    if gid:
                        group_ids.append(gid)
                    else:
                        result.errors.append(f"Group '{gname}' not found for user {user_entry.email}")
                
                # Check if user exists
                existing = await user_service.get_user_by_email(user_entry.email, current_user.tenant_id)
                
                if existing:
                    # Update user groups
                    await user_service.update_user_groups(existing.id, group_ids, current_user.tenant_id)
                    result.updated += 1
                else:
                    # Create new user (pre-registered, will be activated on first login)
                    await user_service.pre_register_user(
                        email=user_entry.email,
                        name=user_entry.name,
                        tenant_id=current_user.tenant_id,
                        groups=group_ids
                    )
                    result.created += 1
                    
            except Exception as e:
                result.failed += 1
                result.errors.append(f"{user_entry.email}: {str(e)}")
                logger.error(f"Failed to import user {user_entry.email}: {e}")
    
    return result

