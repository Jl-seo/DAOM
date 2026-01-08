"""
Permission Service - Checks access to models based on user/group permissions
"""
import logging
from typing import Optional
from dataclasses import dataclass
from app.db.cosmos import get_container
from app.services.user_service import User, get_user_by_id
from app.services.group_service import get_user_groups

logger = logging.getLogger(__name__)

MODELS_CONTAINER = "DocumentModels"


@dataclass
class ModelPermissions:
    """Permission settings for a model"""
    owner: str               # User ID of owner
    users: list[str]         # User IDs with access
    groups: list[str]        # Group IDs with access
    public: bool             # Available to all in tenant
    
    @classmethod
    def from_dict(cls, data: dict) -> "ModelPermissions":
        return cls(
            owner=data.get("owner", ""),
            users=data.get("users", []),
            groups=data.get("groups", []),
            public=data.get("public", False)
        )
    
    def to_dict(self) -> dict:
        return {
            "owner": self.owner,
            "users": self.users,
            "groups": self.groups,
            "public": self.public
        }


async def can_access_model(user: User, model_id: str) -> bool:
    """
    Check if user can access a model
    
    Access is granted if:
    1. User is Bootstrap Admin (INITIAL_ADMIN_EMAILS)
    2. User is superAdmin via group membership
    3. User has model permission via group
    4. User is model owner
    5. User is in model's users list
    6. User is member of a group in model's groups list
    7. Model is public
    """
    from app.core.group_permission_utils import (
        check_initial_admin, 
        is_super_admin_by_group,
        get_model_role_by_group
    )
    
    # 1. Bootstrap admin
    if check_initial_admin(user.email):
        return True
    
    # 2. Group superAdmin -> access all models
    if await is_super_admin_by_group(user.id, user.tenant_id):
        return True
    
    # 3. Group-based model permission
    role = await get_model_role_by_group(user.id, user.tenant_id, model_id)
    if role:  # "Admin" or "User" both grant access
        return True
    
    container = get_container(MODELS_CONTAINER, "/id")
    if not container:
        return False
    
    try:
        items = list(container.query_items(
            query="SELECT * FROM c WHERE c.id = @id",
            parameters=[{"name": "@id", "value": model_id}],
            enable_cross_partition_query=True
        ))
        
        if not items:
            return False
        
        model = items[0]
        permissions = model.get("permissions", {})
        
        # Check if public
        if permissions.get("public", False):
            return True
        
        # Check if owner
        if permissions.get("owner") == user.id:
            return True
        
        # Check if in users list
        if user.id in permissions.get("users", []):
            return True
        
        # Check if in any allowed group
        user_groups = await get_user_groups(user.id, user.tenant_id)
        user_group_ids = [g.id for g in user_groups]
        allowed_groups = permissions.get("groups", [])
        
        if any(gid in allowed_groups for gid in user_group_ids):
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"Error checking model access: {e}")
        return False


async def set_model_permissions(
    model_id: str,
    owner: str,
    users: list[str] = None,
    groups: list[str] = None,
    public: bool = False
) -> bool:
    """Set permissions for a model"""
    container = get_container(MODELS_CONTAINER, "/id")
    if not container:
        return False
    
    try:
        items = list(container.query_items(
            query="SELECT * FROM c WHERE c.id = @id",
            parameters=[{"name": "@id", "value": model_id}],
            enable_cross_partition_query=True
        ))
        
        if not items:
            return False
        
        model = items[0]
        model["permissions"] = {
            "owner": owner,
            "users": users or [],
            "groups": groups or [],
            "public": public
        }
        container.upsert_item(body=model)
        logger.info(f"Updated permissions for model {model_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error setting model permissions: {e}")
        return False


async def get_model_permissions(model_id: str) -> Optional[ModelPermissions]:
    """Get permissions for a model"""
    container = get_container(MODELS_CONTAINER, "/id")
    if not container:
        return None
    
    try:
        items = list(container.query_items(
            query="SELECT c.permissions FROM c WHERE c.id = @id",
            parameters=[{"name": "@id", "value": model_id}],
            enable_cross_partition_query=True
        ))
        
        if not items:
            return None
        
        return ModelPermissions.from_dict(items[0].get("permissions", {}))
        
    except Exception as e:
        logger.error(f"Error getting model permissions: {e}")
        return None


async def get_accessible_models(user: User) -> list[str]:
    """Get list of model IDs user can access"""
    from app.core.group_permission_utils import check_initial_admin, is_super_admin_by_group
    
    container = get_container(MODELS_CONTAINER, "/id")
    if not container:
        return []
    
    try:
        # Bootstrap admin or superAdmin can access all models
        is_admin = check_initial_admin(user.email) or await is_super_admin_by_group(user.id, user.tenant_id)
        if is_admin:
            items = list(container.query_items(
                query="SELECT c.id FROM c",
                enable_cross_partition_query=True
            ))
            return [item["id"] for item in items]
        
        # Get user's groups
        user_groups = await get_user_groups(user.id, user.tenant_id)
        user_group_ids = [g.id for g in user_groups]
        
        # Query models user can access
        items = list(container.query_items(
            query="""
                SELECT c.id FROM c 
                WHERE c.permissions.public = true
                   OR c.permissions.owner = @user_id
                   OR ARRAY_CONTAINS(c.permissions.users, @user_id)
            """,
            parameters=[{"name": "@user_id", "value": user.id}],
            enable_cross_partition_query=True
        ))
        
        accessible = [item["id"] for item in items]
        
        # Also check group access (separate query for simplicity)
        if user_group_ids:
            for group_id in user_group_ids:
                group_items = list(container.query_items(
                    query="SELECT c.id FROM c WHERE ARRAY_CONTAINS(c.permissions.groups, @group_id)",
                    parameters=[{"name": "@group_id", "value": group_id}],
                    enable_cross_partition_query=True
                ))
                accessible.extend([item["id"] for item in group_items])
        
        return list(set(accessible))  # Remove duplicates
        
    except Exception as e:
        logger.error(f"Error getting accessible models: {e}")
        return []
