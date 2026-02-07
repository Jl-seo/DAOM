"""
Role-Based Access Control (RBAC) for DAOM
Uses Cosmos DB group permissions instead of Azure AD App Roles
"""
from fastapi import HTTPException, status, Depends
from app.core.auth import get_current_user, is_admin, CurrentUser


async def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Dependency: Require admin privileges (superAdmin group membership or INITIAL_ADMIN_EMAILS)"""
    if not await is_admin(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return user


# Alias for backward compatibility
require_editor = require_admin
require_viewer = require_admin


# ... imports

async def check_model_permission(user: CurrentUser, model_id: str, required_role: str = "User") -> bool:
    """
    Check if user has required permissions for a model.
    Super Admins are always allowed.
    required_role: "Admin" (for write/team view) or "User" (for read)
    """
    from app.core.group_permission_utils import check_initial_admin, is_super_admin_by_group, get_model_role_by_group

    # 1. Super Admin / Initial Admin is always allowed
    if check_initial_admin(user.email):
        return True
    if await is_super_admin_by_group(user.id, user.tenant_id):
        return True

    # 2. Check granular model permission
    role = await get_model_role_by_group(user.id, user.tenant_id, model_id)
    if not role:
        return False

    if required_role == "Admin":
        return role == "Admin"
    elif required_role == "User":
        return role in ["Admin", "User"]

    return False


async def verify_model_admin(model_id: str, user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Dependency: Require Model Admin privileges"""
    if await check_model_permission(user, model_id, "Admin"):
        return user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Admin access required for model {model_id}"
    )


async def verify_model_access(model_id: str, user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Dependency: Require at least User privileges (Read Access)"""
    if await check_model_permission(user, model_id, "User"):
        return user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Access denied for model {model_id}"
    )
