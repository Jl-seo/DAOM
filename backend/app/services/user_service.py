"""
User Service - Manages users in Cosmos DB
Automatically registers users on first login from Entra ID
"""
import logging
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, asdict
from app.db.cosmos import get_container
from app.core.auth import CurrentUser

logger = logging.getLogger(__name__)

USERS_CONTAINER = "users"


@dataclass
class User:
    """User stored in database"""
    id: str              # oid from Entra ID
    email: str
    name: str
    role: str            # Admin, Editor, Viewer
    tenant_id: str
    created_at: str
    last_login: str
    groups: list[str]    # List of group IDs
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "User":
        return cls(
            id=data.get("id", ""),
            email=data.get("email", ""),
            name=data.get("name", "Unknown"),
            role=data.get("role", "Viewer"),
            tenant_id=data.get("tenant_id", ""),
            created_at=data.get("created_at", ""),
            last_login=data.get("last_login", ""),
            groups=data.get("groups", [])
        )


async def get_or_create_user(current_user: CurrentUser) -> User:
    """
    Get user from DB or create if not exists (first login)
    Called automatically when user accesses any authenticated endpoint
    """
    container = get_container(USERS_CONTAINER, "/tenant_id")
    if not container:
        logger.warning("Users container not available")
        # Return temporary user object
        return User(
            id=current_user.id,
            email=current_user.email,
            name=current_user.name,
            role="Viewer",
            tenant_id=current_user.tenant_id,
            created_at=datetime.utcnow().isoformat(),
            last_login=datetime.utcnow().isoformat(),
            groups=[]
        )
    
    try:
        # Try to get existing user
        items = list(container.query_items(
            query="SELECT * FROM c WHERE c.id = @id",
            parameters=[{"name": "@id", "value": current_user.id}],
            enable_cross_partition_query=True
        ))
        
        if items:
            # Update last login
            user_data = items[0]
            user_data["last_login"] = datetime.utcnow().isoformat()
            container.upsert_item(body=user_data)
            logger.info(f"User login: {current_user.email}")
            return User.from_dict(user_data)
        
        # Create new user (first login)
        new_user = User(
            id=current_user.id,
            email=current_user.email,
            name=current_user.name,
            role="Viewer",  # Default role
            tenant_id=current_user.tenant_id,
            created_at=datetime.utcnow().isoformat(),
            last_login=datetime.utcnow().isoformat(),
            groups=[]
        )
        container.create_item(body=new_user.to_dict())
        logger.info(f"New user registered: {current_user.email}")
        return new_user
        
    except Exception as e:
        logger.error(f"Error in get_or_create_user: {e}")
        raise


async def get_user_by_id(user_id: str) -> Optional[User]:
    """Get user by ID"""
    container = get_container(USERS_CONTAINER, "/tenant_id")
    if not container:
        return None
    
    try:
        items = list(container.query_items(
            query="SELECT * FROM c WHERE c.id = @id",
            parameters=[{"name": "@id", "value": user_id}],
            enable_cross_partition_query=True
        ))
        return User.from_dict(items[0]) if items else None
    except Exception as e:
        logger.error(f"Error getting user: {e}")
        return None


async def get_users_by_tenant(tenant_id: str) -> list[User]:
    """Get all users in a tenant"""
    container = get_container(USERS_CONTAINER, "/tenant_id")
    if not container:
        return []
    
    try:
        items = list(container.query_items(
            query="SELECT * FROM c WHERE c.tenant_id = @tenant_id",
            parameters=[{"name": "@tenant_id", "value": tenant_id}],
            enable_cross_partition_query=True
        ))
        return [User.from_dict(item) for item in items]
    except Exception as e:
        logger.error(f"Error getting users: {e}")
        return []


async def update_user_role(user_id: str, new_role: str, tenant_id: str) -> bool:
    """Update user's role (Admin only)"""
    if new_role not in ["Admin", "Editor", "Viewer"]:
        return False
    
    container = get_container(USERS_CONTAINER, "/tenant_id")
    if not container:
        return False
    
    try:
        items = list(container.query_items(
            query="SELECT * FROM c WHERE c.id = @id AND c.tenant_id = @tenant_id",
            parameters=[
                {"name": "@id", "value": user_id},
                {"name": "@tenant_id", "value": tenant_id}
            ],
            enable_cross_partition_query=True
        ))
        
        if not items:
            return False
        
        user_data = items[0]
        user_data["role"] = new_role
        container.upsert_item(body=user_data)
        logger.info(f"Updated role for {user_id} to {new_role}")
        return True
        
    except Exception as e:
        logger.error(f"Error updating user role: {e}")
        return False


async def add_user_to_group(user_id: str, group_id: str, tenant_id: str) -> bool:
    """Add user to a group"""
    container = get_container(USERS_CONTAINER, "/tenant_id")
    if not container:
        return False
    
    try:
        items = list(container.query_items(
            query="SELECT * FROM c WHERE c.id = @id AND c.tenant_id = @tenant_id",
            parameters=[
                {"name": "@id", "value": user_id},
                {"name": "@tenant_id", "value": tenant_id}
            ],
            enable_cross_partition_query=True
        ))
        
        if not items:
            return False
        
        user_data = items[0]
        if group_id not in user_data.get("groups", []):
            user_data.setdefault("groups", []).append(group_id)
            container.upsert_item(body=user_data)
        return True
        
    except Exception as e:
        logger.error(f"Error adding user to group: {e}")
        return False
