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

    access_token = getattr(user, 'access_token', None)
    user_groups = getattr(user, 'groups', None)

    # 1. Super Admin / Initial Admin is always allowed
    if check_initial_admin(user.email):
        return True
    if await is_super_admin_by_group(user.id, user.tenant_id, access_token=access_token, user_groups=user_groups):
        return True

    # 2. Check granular model permission
    role = await get_model_role_by_group(user.id, user.tenant_id, model_id, access_token=access_token, user_groups=user_groups)
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


async def require_admin_or_model_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """
    Dependency: Require admin OR any model-level Admin role.
    Used for endpoints that need admin-like access but should also work for Model Admins
    (e.g., fetching available Azure DI models, LLM options for model configuration).
    """
    # 1. SuperAdmin / Initial Admin → always pass
    if await is_admin(user):
        return user

    # 2. Check if user has Admin role on ANY model via group permissions
    from app.core.group_permission_utils import get_accessible_model_ids, get_model_role_by_group
    accessible_ids = await get_accessible_model_ids(
        user.id,
        user.tenant_id,
        access_token=getattr(user, 'access_token', None),
        user_groups=getattr(user, 'groups', None)
    )
    if accessible_ids:
        # User has at least one model → Model Admin should be able to configure models
        return user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin or Model Admin access required"
    )
