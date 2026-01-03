"""
Role-Based Access Control (RBAC) for DAOM
"""
from enum import Enum
from functools import wraps
from fastapi import HTTPException, status, Depends
from app.core.auth import get_current_user, CurrentUser
from app.core.config import settings


class Role(str, Enum):
    """Application roles"""
    ADMIN = "Admin"
    EDITOR = "Editor"
    VIEWER = "Viewer"


def get_initial_admin_emails() -> list[str]:
    """Get list of initial admin emails from env"""
    if not settings.INITIAL_ADMIN_EMAILS:
        return []
    return [e.strip().lower() for e in settings.INITIAL_ADMIN_EMAILS.split(",") if e.strip()]


def is_initial_admin(user: CurrentUser) -> bool:
    """Check if user email is in INITIAL_ADMIN_EMAILS"""
    initial_admins = get_initial_admin_emails()
    return user.email.lower() in initial_admins


def has_role(user: CurrentUser, required_role: Role) -> bool:
    """Check if user has the required role or higher"""
    # Initial admins bypass role check
    if is_initial_admin(user):
        return True
    
    role_hierarchy = {
        Role.ADMIN: 3,
        Role.EDITOR: 2,
        Role.VIEWER: 1
    }
    
    user_level = 0
    for role in user.roles:
        if role in role_hierarchy:
            user_level = max(user_level, role_hierarchy[Role(role)])
    
    # If no roles, default to Viewer
    if user_level == 0:
        user_level = role_hierarchy[Role.VIEWER]
    
    required_level = role_hierarchy.get(required_role, 1)
    return user_level >= required_level


def require_role(required_role: Role):
    """Dependency factory: Require specific role"""
    async def role_dependency(user: CurrentUser = Depends(get_current_user)):
        if not has_role(user, required_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{required_role.value}' required"
            )
        return user
    return role_dependency


# Pre-defined dependencies for common roles
require_admin = require_role(Role.ADMIN)
require_editor = require_role(Role.EDITOR)
require_viewer = require_role(Role.VIEWER)
