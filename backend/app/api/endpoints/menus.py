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
    # For now, return all menus (will be filtered by frontend based on user's groups)
    # In production, aggregate user's group permissions server-side
    menus = await menu_service.get_all_menus(current_user.tenant_id)
    return [MenuResponse(
        id=m.id,
        name=m.name,
        icon=m.icon,
        order=m.order,
        parent=m.parent
    ) for m in menus]


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
