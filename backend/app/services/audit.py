"""
Audit logging service - Records all user actions to Cosmos DB
"""
import logging
from datetime import datetime
from uuid import uuid4
from typing import Optional, Any
from dataclasses import dataclass, asdict
from fastapi import Request
from app.db.cosmos import get_audit_container
from app.core.auth import CurrentUser
from app.core.config import settings

logger = logging.getLogger(__name__)

# Container name for audit logs
AUDIT_CONTAINER = "audit_logs"


@dataclass
class AuditLogEntry:
    """Audit log entry structure"""
    id: str
    timestamp: str
    user_id: str
    user_email: str
    tenant_id: str
    action: str          # CREATE, READ, UPDATE, DELETE, START_EXTRACTION, etc.
    resource_type: str   # model, document, extraction, template
    resource_id: str
    status: str = "SUCCESS"  # SUCCESS, FAILURE
    user_name: Optional[str] = None  # Display name of the user
    changes: Optional[dict] = None  # {field: {old, new}}
    metadata: Optional[dict] = None # Browser, OS, etc
    details: Optional[dict] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

    def to_dict(self) -> dict:
        data = asdict(self)
        if data["details"] is None:
            data["details"] = {}
        return data


class AuditAction:
    """Standard audit action types"""
    CREATE = "CREATE"
    READ = "READ"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    EXPORT = "EXPORT"
    EXTRACT = "EXTRACT"
    # Extraction lifecycle
    START_EXTRACTION = "START_EXTRACTION"
    ERROR = "ERROR"
    # Model lifecycle
    CREATE_MODEL = "CREATE_MODEL"
    UPDATE_MODEL = "UPDATE_MODEL"
    DELETE_MODEL = "DELETE_MODEL"


class AuditResource:
    """Standard resource types"""
    MODEL = "model"
    DOCUMENT = "document"
    EXTRACTION = "extraction"
    TEMPLATE = "template"
    USER = "user"
    SETTINGS = "settings"


async def log_action(
    user: CurrentUser,
    action: str,
    resource_type: str,
    resource_id: str,
    status: str = "SUCCESS",
    changes: Optional[dict] = None,
    details: Optional[dict] = None,
    request: Optional[Request] = None
) -> Optional[str]:
    """
    Log an action to the audit log
    
    Args:
        user: Current authenticated user
        action: Action type (CREATE, READ, UPDATE, DELETE, etc.)
        resource_type: Type of resource being accessed
        resource_id: ID of the resource
        details: Additional details about the action
        request: Optional FastAPI request for IP/user-agent
    
    Returns:
        Audit log entry ID if successful, None otherwise
    """
    try:
        container = get_audit_container()
        if container is None:
            logger.warning("Audit log container not available")
            return None

        # Extract request info
        ip_address = None
        user_agent = None
        if request:
            ip_address = request.client.host if request.client else None
            user_agent = request.headers.get("user-agent")

        # Create log entry
        entry = AuditLogEntry(
            id=str(uuid4()),
            timestamp=datetime.utcnow().isoformat() + "Z",
            user_id=user.id,
            user_email=user.email,
            tenant_id=user.tenant_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            status=status,
            changes=changes,
            details=details,
            metadata={
                "path": request.url.path if request else None,
                "method": request.method if request else None
            } if request else {},
            ip_address=ip_address,
            user_agent=user_agent
        )

        # Insert into Cosmos DB
        await container.create_item(body=entry.to_dict())
        logger.info(f"Audit: {user.email} {action} {resource_type}/{resource_id}")

        return entry.id

    except Exception as e:
        logger.error(f"Failed to create audit log: {e}")
        return None


async def get_audit_logs(
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    action: Optional[str] = None,
    target_model_ids: Optional[list[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
) -> list[dict]:
    """
    Query audit logs with filters
    
    Returns:
        List of audit log entries
    """
    try:
        container = get_audit_container()
        if container is None:
            return []

        # Build query
        conditions = ["1=1"]  # Always true base
        parameters = []

        if user_id:
            conditions.append("c.user_id = @user_id")
            parameters.append({"name": "@user_id", "value": user_id})

        if tenant_id:
            conditions.append("(c.tenant_id = @tenant_id OR c.tenant_id = 'default' OR NOT IS_DEFINED(c.tenant_id))")
            parameters.append({"name": "@tenant_id", "value": tenant_id})

        if resource_type:
            conditions.append("c.resource_type = @resource_type")
            parameters.append({"name": "@resource_type", "value": resource_type})

        if action:
            conditions.append("c.action = @action")
            parameters.append({"name": "@action", "value": action})

        if target_model_ids:
            # Filter by model IDs
            # 1. Resource is the model itself
            # 2. Resource is an extraction using the model (check details.model_id)
            ids_str = ", ".join([f"'{mid}'" for mid in target_model_ids])
            conditions.append(f"""(
                (c.resource_type = 'model' AND ARRAY_CONTAINS([{ids_str}], c.resource_id)) OR
                (c.resource_type = 'extraction' AND ARRAY_CONTAINS([{ids_str}], c.details.model_id))
            )""")

        if start_date:
            conditions.append("c.timestamp >= @start_date")
            parameters.append({"name": "@start_date", "value": start_date})

        if end_date:
            conditions.append("c.timestamp <= @end_date")
            parameters.append({"name": "@end_date", "value": end_date})

        query = f"""
            SELECT * FROM c 
            WHERE {' AND '.join(conditions)}
            ORDER BY c.timestamp DESC
            OFFSET {offset} LIMIT {limit}
        """

        items = [item async for item in container.query_items(
            query=query,
            parameters=parameters,
        )]

        return items

    except Exception as e:
        logger.error(f"Failed to query audit logs: {e}")
        return []


async def log_extraction_action(
    job: Any,  # ExtractionJob
    action: str,
    status: str = "SUCCESS",
    changes: Optional[dict] = None,
    details: Optional[dict] = None,
    token_usage: Optional[dict] = None  # NEW: Token usage tracking
) -> Optional[str]:
    """
    Log an extraction-related action (background task friendly)
    Includes token usage for cost tracking and audit.
    """
    try:
        container = get_audit_container()
        if container is None:
            return None

        # Build details with token usage
        audit_details = {
            "model_id": job.model_id,
            "filename": job.filename,
            **(details or {})
        }

        # Add token usage if available
        if token_usage:
            audit_details["token_usage"] = token_usage

        entry = AuditLogEntry(
            id=str(uuid4()),
            timestamp=datetime.utcnow().isoformat() + "Z",
            user_id=job.user_id or "system",
            user_name=job.user_name or "System",
            user_email=job.user_email or settings.SYSTEM_USER_EMAIL,
            tenant_id=getattr(job, "tenant_id", None) or "default",
            action=action,
            resource_type=AuditResource.EXTRACTION,
            resource_id=job.id,
            status=status,
            changes=changes,
            details=audit_details,
            ip_address="system",  # System action
            user_agent="DaomBackend/ExtractionService"
        )

        await container.create_item(body=entry.to_dict())

        # Log token usage if present
        if token_usage:
            logger.info(f"Audit [Extraction]: {entry.user_email} {action} {entry.resource_id} | Tokens: {token_usage.get('total_tokens', 'N/A')}")
        else:
            logger.info(f"Audit [Extraction]: {entry.user_email} {action} {entry.resource_id}")

        return entry.id
    except Exception as e:
        logger.error(f"Failed to log extraction action: {e}")
        return None
