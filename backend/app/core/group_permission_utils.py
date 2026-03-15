"""
Group Permission Utilities
그룹 기반 권한 조회를 위한 유틸리티 함수들
Now with Entra Group inheritance support!
"""
import logging
from typing import Optional
from datetime import datetime, timedelta
from app.core.config import settings

logger = logging.getLogger(__name__)

# Simple in-memory cache for Entra group membership checks
# Key: (user_id, entra_group_id), Value: (is_member, timestamp)
_entra_membership_cache: dict[tuple[str, str], tuple[bool, datetime]] = {}
CACHE_TTL_MINUTES = 5


def check_initial_admin(email: str) -> bool:
    """Bootstrap: INITIAL_ADMIN_EMAILS에 등록된 관리자인지 확인"""
    if not email or not settings.INITIAL_ADMIN_EMAILS:
        return False
    initial_admins = [e.strip().lower() for e in settings.INITIAL_ADMIN_EMAILS.split(',')]
    return email.lower() in initial_admins


async def _check_entra_membership_cached(access_token: str, user_id: str, entra_group_id: str) -> bool:
    """
    Check Entra group membership with caching (5min TTL)
    """
    cache_key = (user_id, entra_group_id)
    now = datetime.utcnow()

    # Check cache
    if cache_key in _entra_membership_cache:
        is_member, cached_at = _entra_membership_cache[cache_key]
        if now - cached_at < timedelta(minutes=CACHE_TTL_MINUTES):
            logger.debug(f"[Permission] Cache hit for Entra group check: {user_id} in {entra_group_id}")
            return is_member

    # Cache miss - call Graph API
    try:
        from app.services import graph_service
        is_member = await graph_service.check_user_in_entra_group(access_token, user_id, entra_group_id)
        _entra_membership_cache[cache_key] = (is_member, now)
        logger.debug(f"[Permission] Entra group check: {user_id} in {entra_group_id} = {is_member}")
        return is_member
    except Exception as e:
        logger.warning(f"[Permission] Failed to check Entra group membership: {e}")
        return False


async def is_member_of_daom_group(user_id: str, group, access_token: Optional[str] = None, user_groups: Optional[list[str]] = None) -> bool:
    """
    Check if user is a member of a DAOM group.
    Supports both direct user members and Entra group inheritance.
    
    Args:
        user_id: The user's object ID
        group: DAOM Group object with members list
        access_token: Optional access token for Graph API fallback
        user_groups: Optional list of Entra group IDs from JWT 'groups' claim (preferred)
    
    Returns:
        True if user is a member (directly or via Entra group)
    """
    for member in group.members:
        member_type = member.type if hasattr(member, 'type') else member.get('type', 'user')
        member_id = member.id if hasattr(member, 'id') else member.get('id', '')

        if member_type == "user" and member_id == user_id:
            return True
        elif member_type == "entra_group":
            # Priority 1: Check JWT groups claim (no API call needed, always available)
            if user_groups and member_id in user_groups:
                logger.debug(f"[Permission] JWT groups claim match: user in Entra group {member_id}")
                return True
            # Priority 2: Fallback to Graph API (requires Graph-scoped token)
            if access_token:
                is_in_entra = await _check_entra_membership_cached(access_token, user_id, member_id)
                if is_in_entra:
                    return True

    return False


async def is_super_admin_by_group(user_id: str, tenant_id: str, access_token: Optional[str] = None, user_groups: Optional[list[str]] = None) -> bool:
    """
    사용자가 superAdmin=true 그룹의 멤버인지 확인
    Now supports Entra group inheritance!
    """
    from app.services import group_service

    groups = await group_service.get_groups_by_tenant(tenant_id)
    for group in groups:
        # Enhanced: Check membership including Entra groups
        is_member = await is_member_of_daom_group(user_id, group, access_token, user_groups=user_groups)
        if is_member:
            # permissions가 객체인 경우와 dict인 경우 모두 처리
            if hasattr(group.permissions, 'superAdmin'):
                if group.permissions.superAdmin:
                    return True
            elif isinstance(group.permissions, dict):
                if group.permissions.get('superAdmin', False):
                    return True
    return False


async def get_model_role_by_group(user_id: str, tenant_id: str, model_id: str, access_token: Optional[str] = None, user_groups: Optional[list[str]] = None) -> Optional[str]:
    """
    사용자의 특정 모델에 대한 role 반환 ("Admin" | "User" | None)
    Now supports Entra group inheritance!
    """
    from app.services import group_service

    groups = await group_service.get_groups_by_tenant(tenant_id)
    for group in groups:
        is_member = await is_member_of_daom_group(user_id, group, access_token, user_groups=user_groups)
        if is_member:
            # permissions.models 접근
            models_list = []
            if hasattr(group.permissions, 'models'):
                models_list = group.permissions.models
            elif isinstance(group.permissions, dict):
                models_list = group.permissions.get('models', [])

            for model_perm in models_list:
                perm_model_id = model_perm.modelId if hasattr(model_perm, 'modelId') else model_perm.get('modelId')
                if perm_model_id == model_id:
                    return model_perm.role if hasattr(model_perm, 'role') else model_perm.get('role')
    return None


async def get_accessible_model_ids(user_id: str, tenant_id: str, access_token: Optional[str] = None, user_groups: Optional[list[str]] = None) -> set[str]:
    """
    사용자가 속한 그룹들의 권한을 확인하여 접근 가능한 모든 모델 ID 집합 반환
    Now supports Entra group inheritance!
    """
    from app.services import group_service

    accessible_models = set()
    groups = await group_service.get_groups_by_tenant(tenant_id)

    for group in groups:
        is_member = await is_member_of_daom_group(user_id, group, access_token, user_groups=user_groups)
        if is_member:
            models_list = []
            if hasattr(group.permissions, 'models'):
                models_list = group.permissions.models
            elif isinstance(group.permissions, dict):
                models_list = group.permissions.get('models', [])

            for model_perm in models_list:
                perm_model_id = model_perm.modelId if hasattr(model_perm, 'modelId') else model_perm.get('modelId')
                if perm_model_id:
                    accessible_models.add(perm_model_id)

    return accessible_models


async def get_accessible_menu_ids(user_id: str, tenant_id: str, access_token: Optional[str] = None, user_groups: Optional[list[str]] = None) -> set[str]:
    """
    사용자가 속한 그룹들의 메뉴 권한을 확인하여 접근 가능한 모든 메뉴 ID 집합 반환
    """
    from app.services import group_service

    accessible_menus = set()
    groups = await group_service.get_groups_by_tenant(tenant_id)

    for group in groups:
        is_member = await is_member_of_daom_group(user_id, group, access_token, user_groups=user_groups)
        if is_member:
            # Check if superAdmin - gets all menus
            is_super = False
            if hasattr(group.permissions, 'superAdmin'):
                is_super = group.permissions.superAdmin
            elif isinstance(group.permissions, dict):
                is_super = group.permissions.get('superAdmin', False)

            if is_super:
                return set()  # Empty set = all access (handled by caller)

            # Get menu list
            menus_list = []
            if hasattr(group.permissions, 'menus'):
                menus_list = group.permissions.menus
            elif isinstance(group.permissions, dict):
                menus_list = group.permissions.get('menus', [])

            accessible_menus.update(menus_list)

    return accessible_menus

