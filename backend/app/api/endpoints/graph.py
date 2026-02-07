"""
Graph API endpoints - Search Entra ID users and groups
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from app.core.auth import get_current_user, CurrentUser
from app.core.config import settings

# For now, we'll do client-side Graph API calls using MSAL
# This endpoint is a placeholder that explains the client-side approach

router = APIRouter()


class EntraSearchResult(BaseModel):
    type: str  # "user" or "group"
    id: str
    displayName: str
    email: Optional[str] = None
    description: Optional[str] = None


@router.get("/info")
async def get_graph_info(current_user: CurrentUser = Depends(get_current_user)):
    """
    Returns information about Graph API integration.
    
    Actual Graph API calls should be made from the frontend using MSAL,
    as the frontend already has the user's access token.
    
    Required Graph permissions (add to Azure App Registration):
    - User.Read.All (for searching users)
    - Group.Read.All (for searching groups)
    - GroupMember.Read.All (for checking memberships)
    """
    return {
        "message": "Graph API calls should be made from frontend using MSAL",
        "required_scopes": [
            f"{settings.GRAPH_API_BASE_URL}/User.Read.All",
            f"{settings.GRAPH_API_BASE_URL}/Group.Read.All"
        ],
        "endpoints": {
            "search_users": f"GET {settings.GRAPH_API_BASE_URL}/users?$search=\"displayName:{{query}}\"",
            "search_groups": f"GET {settings.GRAPH_API_BASE_URL}/groups?$search=\"displayName:{{query}}\"&$filter=securityEnabled eq true"
        }
    }
