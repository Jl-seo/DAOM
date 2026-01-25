"""
Group Permission Utilities
그룹 기반 권한 조회를 위한 유틸리티 함수들
"""
from typing import Optional
from app.core.config import settings


def check_initial_admin(email: str) -> bool:
    """Bootstrap: INITIAL_ADMIN_EMAILS에 등록된 관리자인지 확인"""
    if not email or not settings.INITIAL_ADMIN_EMAILS:
        return False
    initial_admins = [e.strip().lower() for e in settings.INITIAL_ADMIN_EMAILS.split(',')]
    return email.lower() in initial_admins


async def is_super_admin_by_group(user_id: str, tenant_id: str) -> bool:
    """
    사용자가 superAdmin=true 그룹의 멤버인지 확인
    """
    # Lazy import to avoid circular dependency
    from app.services import group_service
    
    groups = await group_service.get_groups_by_tenant(tenant_id)
    for group in groups:
        # 사용자가 이 그룹의 멤버인지 확인
        is_member = any(m.id == user_id for m in group.members)
        if is_member:
            # permissions가 객체인 경우와 dict인 경우 모두 처리
            if hasattr(group.permissions, 'superAdmin'):
                if group.permissions.superAdmin:
                    return True
            elif isinstance(group.permissions, dict):
                if group.permissions.get('superAdmin', False):
                    return True
    return False


async def get_model_role_by_group(user_id: str, tenant_id: str, model_id: str) -> Optional[str]:
    """
    사용자의 특정 모델에 대한 role 반환 ("Admin" | "User" | None)
    """
    from app.services import group_service
    
    groups = await group_service.get_groups_by_tenant(tenant_id)
    for group in groups:
        is_member = any(m.id == user_id for m in group.members)
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

async def get_accessible_model_ids(user_id: str, tenant_id: str) -> set[str]:
    """
    사용자가 속한 그룹들의 권한을 확인하여 접근 가능한 모든 모델 ID 집합 반환
    """
    from app.services import group_service
    
    accessible_models = set()
    groups = await group_service.get_groups_by_tenant(tenant_id)
    
    for group in groups:
        is_member = any(m.id == user_id for m in group.members)
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
