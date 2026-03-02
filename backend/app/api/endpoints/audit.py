"""
Audit Log API endpoints - Admin only
"""
from fastapi import APIRouter, Depends, Query
from typing import Optional
from pydantic import BaseModel
from app.core.auth import CurrentUser, is_super_admin
from app.core.permissions import require_admin
from app.services.audit import get_audit_logs
from app.services import models, stats_service

router = APIRouter()


class AuditLogResponse(BaseModel):
    id: str
    timestamp: str
    user_id: str
    user_email: str
    tenant_id: str
    action: str
    resource_type: str
    resource_id: str
    status: str = "SUCCESS"
    changes: Optional[dict] = None
    metadata: Optional[dict] = None
    details: Optional[dict] = None
    ip_address: Optional[str] = None


class AuditLogsListResponse(BaseModel):
    items: list[AuditLogResponse]
    total: int


@router.get("/", response_model=AuditLogsListResponse)
async def list_audit_logs(
    user: CurrentUser = Depends(require_admin),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    action: Optional[str] = Query(None, description="Filter by action"),
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0)
):
    """
    List audit logs (Admin only)
    
    Filters:
    - user_id: Filter by specific user
    - resource_type: model, document, extraction, template
    - action: CREATE, READ, UPDATE, DELETE, etc.
    - start_date/end_date: Date range filter
    """


    # RBAC Filtering
    target_model_ids = None
    if not is_super_admin(user):
        # Model Admin: Filter logs by accessible groups
        all_models = await models.load_models()
        user_groups = set(user.groups or [])

        # Find models where allowedGroups intersects with user's groups
        accessible_models = [
            m for m in all_models
            if m.allowedGroups and set(m.allowedGroups) & user_groups
        ]

        target_model_ids = [m.id for m in accessible_models]

        # If no accessible models, return empty result (or handle as no permission)
        if not target_model_ids:
            return AuditLogsListResponse(items=[], total=0)

    # If super admin, allow viewing all logs (ignore tenant mismatch for system logs)
    # System logs often have tenant_id="default", but user has real Entra ID tenant
    search_tenant = user.tenant_id
    if is_super_admin(user):
        search_tenant = None

    logs = get_audit_logs(
        user_id=user_id,
        tenant_id=search_tenant,
        resource_type=resource_type,
        action=action,
        target_model_ids=target_model_ids,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset
    )

    return AuditLogsListResponse(
        items=[AuditLogResponse(**log) for log in logs],
        total=len(logs)  # Simplified - in production, use separate count query
    )


@router.get("/stats")
async def get_audit_stats(
    user: CurrentUser = Depends(require_admin)
):
    """
    Get audit log statistics (Admin only)
    """
    """
    Get audit log statistics (Admin only)
    """
    stats = stats_service.get_dashboard_stats()
    return stats
