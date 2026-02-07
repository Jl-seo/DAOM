"""
Groups API endpoints - Group management with Entra members and model permissions
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.core.auth import get_current_user, CurrentUser
from app.core.permissions import require_admin
from app.services import group_service

router = APIRouter()


class MemberInfo(BaseModel):
    type: str  # "user" or "entra_group"
    id: str
    displayName: str


class ModelPermissionInfo(BaseModel):
    modelId: str
    modelName: str
    role: str  # "Admin" or "User"


class GroupPermissionsInfo(BaseModel):
    superAdmin: bool = False
    models: list[ModelPermissionInfo] = []
    menus: list[str] = []  # Menu IDs


class GroupResponse(BaseModel):
    id: str
    name: str
    description: str
    tenant_id: str
    members: list[MemberInfo]
    permissions: GroupPermissionsInfo
    created_by: str
    created_at: str


class CreateGroupRequest(BaseModel):
    name: str
    description: str = ""
    superAdmin: bool = False


class AddMemberRequest(BaseModel):
    type: str  # "user" or "entra_group"
    id: str
    displayName: str


class SetPermissionsRequest(BaseModel):
    superAdmin: bool = False
    models: list[ModelPermissionInfo] = []
    menus: list[str] = []  # Menu IDs


def _to_response(group) -> GroupResponse:
    return GroupResponse(
        id=group.id,
        name=group.name,
        description=group.description,
        tenant_id=group.tenant_id,
        members=[MemberInfo(type=m.type, id=m.id, displayName=m.displayName) for m in group.members],
        permissions=GroupPermissionsInfo(
            superAdmin=group.permissions.superAdmin if hasattr(group.permissions, 'superAdmin') else group.permissions.get('superAdmin', False),
            models=[ModelPermissionInfo(**m.to_dict() if hasattr(m, 'to_dict') else m) for m in (group.permissions.models if hasattr(group.permissions, 'models') else group.permissions.get('models', []))],
            menus=group.permissions.menus if hasattr(group.permissions, 'menus') else group.permissions.get('menus', [])
        ),
        created_by=group.created_by,
        created_at=group.created_at
    )


@router.get("/", response_model=list[GroupResponse])
async def list_groups(current_user: CurrentUser = Depends(get_current_user)):
    """List all groups in tenant. Filter out Super Admin groups for non-super admins."""
    from app.core.auth import is_super_admin
    is_super = await is_super_admin(current_user)

    groups = await group_service.get_groups_by_tenant(current_user.tenant_id)

    # Filter out Super Admin groups for non-super admins
    if not is_super:
        filtered_groups = []
        for g in groups:
            # Check superAdmin flag safely (similar to _to_response logic)
            perm_super = False
            if hasattr(g, 'permissions'):
                perms = g.permissions
                if hasattr(perms, 'superAdmin'):
                    perm_super = perms.superAdmin
                elif isinstance(perms, dict):
                    perm_super = perms.get('superAdmin', False)

            if not perm_super:
                filtered_groups.append(g)
        groups = filtered_groups

    return [_to_response(g) for g in groups]


@router.post("/", response_model=GroupResponse)
async def create_group(
    request: CreateGroupRequest,
    current_user: CurrentUser = Depends(require_admin)
):
    """Create a new group (Admin only)"""
    group = await group_service.create_group(
        name=request.name,
        description=request.description,
        tenant_id=current_user.tenant_id,
        created_by=current_user.id,
        super_admin=request.superAdmin
    )

    if not group:
        raise HTTPException(status_code=400, detail="Failed to create group")

    return _to_response(group)



@router.get("/{group_id}", response_model=GroupResponse)
async def get_group(
    group_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Get group info"""
    group = await group_service.get_group_by_id(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    return _to_response(group)


class UpdateGroupRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


@router.put("/{group_id}", response_model=GroupResponse)
async def update_group(
    group_id: str,
    request: UpdateGroupRequest,
    current_user: CurrentUser = Depends(require_admin)
):
    """Update group details (Admin only)"""
    group = await group_service.update_group(
        group_id=group_id,
        name=request.name,
        description=request.description,
        tenant_id=current_user.tenant_id
    )

    if not group:
        raise HTTPException(status_code=400, detail="Failed to update group")

    return _to_response(group)


@router.post("/{group_id}/members")
async def add_member(
    group_id: str,
    request: AddMemberRequest,
    current_user: CurrentUser = Depends(require_admin)
):
    """Add member (user or Entra group) to group"""
    if request.type not in ["user", "entra_group"]:
        raise HTTPException(status_code=400, detail="Invalid member type")

    success = await group_service.add_member_to_group(
        group_id=group_id,
        member_type=request.type,
        member_id=request.id,
        display_name=request.displayName,
        tenant_id=current_user.tenant_id
    )

    if not success:
        raise HTTPException(status_code=400, detail="Failed to add member")

    return {"success": True, "message": f"{request.type} added"}


@router.delete("/{group_id}/members/{member_id}")
async def remove_member(
    group_id: str,
    member_id: str,
    current_user: CurrentUser = Depends(require_admin)
):
    """Remove member from group"""
    success = await group_service.remove_member_from_group(
        group_id,
        member_id,
        current_user.tenant_id
    )

    if not success:
        raise HTTPException(status_code=400, detail="Failed to remove member")

    return {"success": True, "message": "Member removed"}


@router.put("/{group_id}/permissions")
async def set_permissions(
    group_id: str,
    request: SetPermissionsRequest,
    current_user: CurrentUser = Depends(require_admin)
):
    """Set group permissions (superAdmin, per-model, and menus)"""
    model_perms = [{"modelId": m.modelId, "modelName": m.modelName, "role": m.role} for m in request.models]

    success = await group_service.set_group_permissions(
        group_id=group_id,
        tenant_id=current_user.tenant_id,
        super_admin=request.superAdmin,
        model_permissions=model_perms,
        menu_permissions=request.menus
    )

    if not success:
        raise HTTPException(status_code=400, detail="Failed to set permissions")

    return {"success": True, "message": "Permissions updated"}


@router.delete("/{group_id}")
async def delete_group(
    group_id: str,
    current_user: CurrentUser = Depends(require_admin)
):
    """Delete group"""
    success = await group_service.delete_group(group_id, current_user.tenant_id)

    if not success:
        raise HTTPException(status_code=400, detail="Failed to delete group")

    return {"success": True, "message": "Group deleted"}
