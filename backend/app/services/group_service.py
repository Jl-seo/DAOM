"""
Group Service - Enhanced with Entra group members and model permissions
"""
import logging
from datetime import datetime
from uuid import uuid4
from typing import Optional
from dataclasses import dataclass, asdict, field
from app.db.cosmos import get_container

logger = logging.getLogger(__name__)

GROUPS_CONTAINER = "groups"


@dataclass
class GroupMember:
    """Member of a group - can be a user or an Entra group"""
    type: str           # "user" or "entra_group"
    id: str             # user_id or entra_group_id
    displayName: str    # Display name for UI

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "GroupMember":
        return cls(
            type=data.get("type", "user"),
            id=data.get("id", ""),
            displayName=data.get("displayName", "")
        )


@dataclass
class ModelPermission:
    """Permission for a specific model"""
    modelId: str
    modelName: str      # For display
    role: str           # "Admin" or "User"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ModelPermission":
        return cls(
            modelId=data.get("modelId", ""),
            modelName=data.get("modelName", ""),
            role=data.get("role", "User")
        )


@dataclass
class GroupPermissions:
    """Permissions config for a group"""
    superAdmin: bool = False           # Access to ALL models and menus
    models: list = field(default_factory=list)  # ModelPermission list
    menus: list = field(default_factory=list)   # Menu ID list

    def to_dict(self) -> dict:
        return {
            "superAdmin": self.superAdmin,
            "models": [m.to_dict() if isinstance(m, ModelPermission) else m for m in self.models],
            "menus": self.menus
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GroupPermissions":
        return cls(
            superAdmin=data.get("superAdmin", False),
            models=[ModelPermission.from_dict(m) for m in data.get("models", [])],
            menus=data.get("menus", [])
        )


@dataclass
class Group:
    """Group with Entra members and model permissions"""
    id: str
    name: str
    description: str
    tenant_id: str
    members: list           # GroupMember list
    permissions: dict       # GroupPermissions
    created_by: str = ""
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "tenant_id": self.tenant_id,
            "members": [m.to_dict() if isinstance(m, GroupMember) else m for m in self.members],
            "permissions": self.permissions.to_dict() if isinstance(self.permissions, GroupPermissions) else self.permissions,
            "created_by": self.created_by,
            "created_at": self.created_at
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Group":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            tenant_id=data.get("tenant_id", ""),
            members=[GroupMember.from_dict(m) for m in data.get("members", [])],
            permissions=GroupPermissions.from_dict(data.get("permissions", {})),
            created_by=data.get("created_by", ""),
            created_at=data.get("created_at", "")
        )


async def create_group(
    name: str,
    description: str,
    tenant_id: str,
    created_by: str,
    super_admin: bool = False
) -> Optional[Group]:
    """Create a new group"""
    container = get_container(GROUPS_CONTAINER, "/tenant_id")
    if not container:
        return None

    try:
        group = Group(
            id=str(uuid4()),
            name=name,
            description=description,
            tenant_id=tenant_id,
            members=[],
            permissions=GroupPermissions(superAdmin=super_admin, models=[]),
            created_by=created_by,
            created_at=datetime.utcnow().isoformat()
        )
        await container.create_item(body=group.to_dict())
        logger.info(f"Created group: {name}")
        return group
    except Exception as e:
        logger.error(f"Error creating group: {e}")
        return None


async def update_group(
    group_id: str,
    name: str = None,
    description: str = None,
    tenant_id: str = None
) -> Optional[Group]:
    """Update group details"""
    container = get_container(GROUPS_CONTAINER, "/tenant_id")
    if not container:
        return None

    try:
        items = [item async for item in container.query_items(
            query="SELECT * FROM c WHERE c.id = @id AND c.tenant_id = @tenant_id",
            parameters=[
                {"name": "@id", "value": group_id},
                {"name": "@tenant_id", "value": tenant_id}
            ],
            enable_cross_partition_query=True
        )]

        if not items:
            return None

        group_data = items[0]
        if name is not None:
            group_data["name"] = name
        if description is not None:
            group_data["description"] = description

        await container.upsert_item(body=group_data)
        logger.info(f"Updated group: {group_data['name']}")
        return Group.from_dict(group_data)

    except Exception as e:
        logger.error(f"Error updating group: {e}")
        return None


async def get_group_by_id(group_id: str) -> Optional[Group]:
    """Get group by ID"""
    container = get_container(GROUPS_CONTAINER, "/tenant_id")
    if not container:
        return None

    try:
        items = [item async for item in container.query_items(
            query="SELECT * FROM c WHERE c.id = @id",
            parameters=[{"name": "@id", "value": group_id}],
            enable_cross_partition_query=True
        )]
        return Group.from_dict(items[0]) if items else None
    except Exception as e:
        logger.error(f"Error getting group: {e}")
        return None


async def get_groups_by_tenant(tenant_id: str) -> list[Group]:
    """Get all groups in a tenant"""
    container = get_container(GROUPS_CONTAINER, "/tenant_id")
    if not container:
        return []

    try:
        items = [item async for item in container.query_items(
            query="SELECT * FROM c WHERE c.tenant_id = @tenant_id",
            parameters=[{"name": "@tenant_id", "value": tenant_id}],
            enable_cross_partition_query=True
        )]
        return [Group.from_dict(item) for item in items]
    except Exception as e:
        logger.error(f"Error getting groups: {e}")
        return []


async def get_user_groups(user_id: str, tenant_id: str) -> list[Group]:
    """Get all groups that a user belongs to (as a member)"""
    all_groups = await get_groups_by_tenant(tenant_id)
    return [
        g for g in all_groups
        if any(m.id == user_id for m in g.members if isinstance(m, GroupMember))
    ]


async def add_member_to_group(
    group_id: str,
    member_type: str,  # "user" or "entra_group"
    member_id: str,
    display_name: str,
    tenant_id: str
) -> bool:
    """Add a member (user or Entra group) to a group"""
    container = get_container(GROUPS_CONTAINER, "/tenant_id")
    if not container:
        return False

    try:
        items = [item async for item in container.query_items(
            query="SELECT * FROM c WHERE c.id = @id AND c.tenant_id = @tenant_id",
            parameters=[
                {"name": "@id", "value": group_id},
                {"name": "@tenant_id", "value": tenant_id}
            ],
            enable_cross_partition_query=True
        )]

        if not items:
            return False

        group_data = items[0]
        members = group_data.get("members", [])

        # Check if already a member
        if not any(m.get("id") == member_id for m in members):
            members.append({
                "type": member_type,
                "id": member_id,
                "displayName": display_name
            })
            group_data["members"] = members
            await container.upsert_item(body=group_data)
            logger.info(f"Added {member_type} {member_id} to group {group_id}")

        return True

    except Exception as e:
        logger.error(f"Error adding member to group: {e}")
        return False


async def remove_member_from_group(group_id: str, member_id: str, tenant_id: str) -> bool:
    """Remove a member from a group"""
    container = get_container(GROUPS_CONTAINER, "/tenant_id")
    if not container:
        return False

    try:
        items = [item async for item in container.query_items(
            query="SELECT * FROM c WHERE c.id = @id AND c.tenant_id = @tenant_id",
            parameters=[
                {"name": "@id", "value": group_id},
                {"name": "@tenant_id", "value": tenant_id}
            ],
            enable_cross_partition_query=True
        )]

        if not items:
            return False

        group_data = items[0]
        members = group_data.get("members", [])
        group_data["members"] = [m for m in members if m.get("id") != member_id]
        await container.upsert_item(body=group_data)
        logger.info(f"Removed member {member_id} from group {group_id}")
        return True

    except Exception as e:
        logger.error(f"Error removing member from group: {e}")
        return False


async def set_group_permissions(
    group_id: str,
    tenant_id: str,
    super_admin: bool = False,
    model_permissions: list = None,
    menu_permissions: list = None
) -> bool:
    """Set group permissions (superAdmin, per-model, and menus)"""
    container = get_container(GROUPS_CONTAINER, "/tenant_id")
    if not container:
        return False

    try:
        items = [item async for item in container.query_items(
            query="SELECT * FROM c WHERE c.id = @id AND c.tenant_id = @tenant_id",
            parameters=[
                {"name": "@id", "value": group_id},
                {"name": "@tenant_id", "value": tenant_id}
            ],
            enable_cross_partition_query=True
        )]

        if not items:
            return False

        group_data = items[0]
        group_data["permissions"] = {
            "superAdmin": super_admin,
            "models": model_permissions or [],
            "menus": menu_permissions or []
        }
        await container.upsert_item(body=group_data)
        logger.info(f"Updated permissions for group {group_id}")
        return True

    except Exception as e:
        logger.error(f"Error setting group permissions: {e}")
        return False


async def delete_group(group_id: str, tenant_id: str) -> bool:
    """Delete a group"""
    container = get_container(GROUPS_CONTAINER, "/tenant_id")
    if not container:
        return False

    try:
        await container.delete_item(item=group_id, partition_key=tenant_id)
        logger.info(f"Deleted group {group_id}")
        return True
    except Exception as e:
        logger.error(f"Error deleting group: {e}")
        return False
