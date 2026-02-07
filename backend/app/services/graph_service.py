"""
Microsoft Graph API Service - Search Entra ID users and groups
Requires: pip install httpx
"""
import logging
from dataclasses import dataclass
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)

GRAPH_API_BASE = settings.GRAPH_API_BASE_URL


@dataclass
class EntraUser:
    id: str
    displayName: str
    mail: str
    userPrincipalName: str

    @classmethod
    def from_dict(cls, data: dict) -> "EntraUser":
        return cls(
            id=data.get("id", ""),
            displayName=data.get("displayName", ""),
            mail=data.get("mail", ""),
            userPrincipalName=data.get("userPrincipalName", "")
        )


@dataclass
class EntraGroup:
    id: str
    displayName: str
    description: str

    @classmethod
    def from_dict(cls, data: dict) -> "EntraGroup":
        return cls(
            id=data.get("id", ""),
            displayName=data.get("displayName", ""),
            description=data.get("description", "") or ""
        )


async def search_entra_users(access_token: str, query: str, limit: int = 10) -> list[EntraUser]:
    """
    Search Entra ID users by name or email
    
    Requires: User.Read.All or Directory.Read.All permission
    """
    if not query or len(query) < 2:
        return []

    headers = {
        "Authorization": f"Bearer {access_token}",
        "ConsistencyLevel": "eventual"
    }

    # Search by displayName or mail
    params = {
        "$search": f'"displayName:{query}" OR "mail:{query}"',
        "$top": str(limit),
        "$select": "id,displayName,mail,userPrincipalName"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{GRAPH_API_BASE}/users",
                headers=headers,
                params=params
            )

            if response.status_code != 200:
                logger.error(f"Graph API error: {response.status_code} - {response.text}")
                return []

            data = response.json()
            users = [EntraUser.from_dict(u) for u in data.get("value", [])]
            return users

    except Exception as e:
        logger.error(f"Error searching Entra users: {e}")
        return []


async def search_entra_groups(access_token: str, query: str, limit: int = 10) -> list[EntraGroup]:
    """
    Search Entra ID security groups by name
    
    Requires: Group.Read.All or Directory.Read.All permission
    """
    if not query or len(query) < 2:
        return []

    headers = {
        "Authorization": f"Bearer {access_token}",
        "ConsistencyLevel": "eventual"
    }

    params = {
        "$search": f'"displayName:{query}"',
        "$filter": "securityEnabled eq true",
        "$top": str(limit),
        "$select": "id,displayName,description"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{GRAPH_API_BASE}/groups",
                headers=headers,
                params=params
            )

            if response.status_code != 200:
                logger.error(f"Graph API error: {response.status_code} - {response.text}")
                return []

            data = response.json()
            groups = [EntraGroup.from_dict(g) for g in data.get("value", [])]
            return groups

    except Exception as e:
        logger.error(f"Error searching Entra groups: {e}")
        return []


async def get_user_group_memberships(access_token: str, user_id: str) -> list[str]:
    """
    Get all group IDs that a user is a member of
    
    Used to check permissions at login time
    """
    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{GRAPH_API_BASE}/users/{user_id}/getMemberObjects",
                headers=headers,
                json={"securityEnabledOnly": True}
            )

            if response.status_code != 200:
                logger.error(f"Graph API error: {response.status_code}")
                return []

            data = response.json()
            return data.get("value", [])

    except Exception as e:
        logger.error(f"Error getting user groups: {e}")
        return []


async def check_user_in_entra_group(access_token: str, user_id: str, group_id: str) -> bool:
    """
    Check if a user is a member of a specific Entra group
    """
    memberships = await get_user_group_memberships(access_token, user_id)
    return group_id in memberships
