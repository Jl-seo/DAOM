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
