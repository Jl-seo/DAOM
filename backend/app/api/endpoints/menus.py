"""
Menus API endpoints - Menu configuration from database
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.core.auth import get_current_user, CurrentUser
from app.core.permissions import require_admin
from app.services import menu_service

router = APIRouter()


class MenuResponse(BaseModel):
    id: str
    name: str
    icon: str
    order: int
    parent: Optional[str] = None


class UpdateMenuRequest(BaseModel):
    name: Optional[str] = None
    icon: Optional[str] = None
    order: Optional[int] = None


@router.get("/", response_model=list[MenuResponse])
async def list_menus(current_user: CurrentUser = Depends(get_current_user)):
    """Get all menus for the tenant"""
    menus = await menu_service.get_all_menus(current_user.tenant_id)
    return [MenuResponse(
        id=m.id,
        name=m.name,
        icon=m.icon,
        order=m.order,
        parent=m.parent
    ) for m in menus]


@router.get("/accessible", response_model=list[MenuResponse])
async def get_accessible_menus(current_user: CurrentUser = Depends(get_current_user)):
    """Get menus accessible by the current user based on their group permissions"""
    from app.core.auth import is_super_admin
    from app.core.group_permission_utils import get_accessible_menu_ids

    # Super Admin sees all menus
    is_super = await is_super_admin(current_user)
    if is_super:
        menus = await menu_service.get_all_menus(current_user.tenant_id)
        return [MenuResponse(
            id=m.id, name=m.name, icon=m.icon, order=m.order, parent=m.parent
        ) for m in menus]

    # Get user's accessible menu IDs from group permissions
    accessible_menu_ids = await get_accessible_menu_ids(
        current_user.id,
        current_user.tenant_id,
        access_token=getattr(current_user, 'access_token', None)
    )

    # Get all menus and filter
    menus = await menu_service.get_all_menus(current_user.tenant_id)
    accessible_menus = [m for m in menus if m.id in accessible_menu_ids]

    # Also include parent menus if any child is accessible
    parent_ids = {m.parent for m in accessible_menus if m.parent}
    for m in menus:
        if m.id in parent_ids and m.id not in accessible_menu_ids:
            accessible_menus.append(m)

    # Sort by order
    accessible_menus.sort(key=lambda x: x.order)

    return [MenuResponse(
        id=m.id, name=m.name, icon=m.icon, order=m.order, parent=m.parent
    ) for m in accessible_menus]


@router.put("/{menu_id}")
async def update_menu(
    menu_id: str,
    request: UpdateMenuRequest,
    current_user: CurrentUser = Depends(require_admin)
):
    """Update menu properties (Admin only)"""
    success = await menu_service.update_menu(
        menu_id=menu_id,
        tenant_id=current_user.tenant_id,
        name=request.name,
        icon=request.icon,
        order=request.order
    )

    if not success:
        raise HTTPException(status_code=400, detail="Failed to update menu")

    return {"success": True, "message": "Menu updated"}
