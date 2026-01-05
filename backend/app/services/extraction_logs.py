"""
Extraction Logs Service - Stores extraction results in Azure Cosmos DB
"""
import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, field_validator
from app.db.cosmos import get_extractions_container
from app.core.enums import ExtractionType, ExtractionStatus
import logging
from app.services import audit
from app.services.audit import AuditAction, AuditResource

logger = logging.getLogger(__name__)


class ExtractionLog(BaseModel):
    """Extraction result log entry"""
    id: str
    model_id: str
    user_id: Optional[str] = "unknown"  # User who performed the extraction
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    filename: str
    file_url: Optional[str] = None
    status: str  # 'success' | 'error'
    extracted_data: Optional[dict] = None
    preview_data: Optional[dict] = None  # Full extraction structure with other_data
    error: Optional[str] = None
    job_id: Optional[str] = None  # Reference to active job for processing logs
    created_at: str
    updated_at: Optional[str] = None
    tenant_id: Optional[str] = "default"
    llm_model: Optional[str] = None  # Model name used for extraction (e.g. gpt-4.1)

    @field_validator('user_id', mode='before')
    @classmethod
    def set_user_id(cls, v):
        return v or "unknown"


def save_extraction_log(
    model_id: str,
    user_id: str,
    filename: str,
    status: str,
    file_url: Optional[str] = None,
    extracted_data: Optional[dict] = None,
    preview_data: Optional[dict] = None,
    error: Optional[str] = None,
    user_name: Optional[str] = None,
    user_email: Optional[str] = None,
    log_id: Optional[str] = None,
    job_id: Optional[str] = None,
    tenant_id: Optional[str] = "default",
    llm_model: Optional[str] = None,
) -> Optional[ExtractionLog]:
    """Save a new extraction log entry"""
    container = get_extractions_container()
    
    if not container:
        logger.warning("[ExtractionLogs] Cosmos not available, skipping log")
        return None
    
    # If log_id is provided, we're updating an existing log - preserve created_at
    existing_created_at = None
    if log_id:
        try:
            existing = get_log(log_id)
            if existing:
                existing_created_at = existing.created_at
        except Exception:
            pass
    
    now = datetime.utcnow().isoformat()
    log = ExtractionLog(
        id=log_id if log_id else str(uuid.uuid4()),
        model_id=model_id,
        user_id=user_id,
        user_name=user_name,
        user_email=user_email,
        filename=filename,
        file_url=file_url,
        status=status,
        extracted_data=extracted_data,
        preview_data=preview_data,
        error=error,
        job_id=job_id,
        created_at=existing_created_at if existing_created_at else now,
        updated_at=now,
        tenant_id=tenant_id,
        llm_model=llm_model
    )
    
    try:
        log_dict = log.model_dump()
        log_dict["type"] = ExtractionType.LOG.value
        container.upsert_item(log_dict)
        logger.info(f"[ExtractionLogs] Saved log {log.id} (Overwrite: {bool(log_id)}) for user {user_id}, model {model_id}, llm={llm_model}")
        
        # Log to Audit System
        # We only log significant state changes or new creations to avoid noise?
        # For now, log everything to ensure visibility as requested.
        try:
             # Create a mock user object for audit.log_action since we might not have request context here
            from app.core.auth import CurrentUser
            mock_user = CurrentUser(
                id=user_id,
                email=user_email or "unknown@example.com",
                name=user_name or "Unknown",
                tenant_id=tenant_id or "default",
                roles=[]
            )
            
            audit_action = AuditAction.CREATE if not log_id else AuditAction.UPDATE
            if status == ExtractionStatus.ERROR.value:
                audit_action = "ERROR"
            elif status == "P100":
                audit_action = "START_EXTRACTION"
            elif status == ExtractionStatus.SUCCESS.value:
                audit_action = AuditAction.EXTRACT

            # Avoid circular import or complex dependency - just call log_action synchronously?
            # log_action is async. We are in a sync function here.
            # We can use a background task approach if we were in FastAPI context, 
            # but here we might just fire-and-forget or use the async loop if available.
            # Wait, log_action is likely async. `async def log_action`.
            # We can't await it here easily in a sync function.
            
            # Alternative: Use `audit.log_extraction_action` which takes a job, but we have a log.
            # Or make a sync wrapper for audit logging?
            # Or just use the container directly like audit.py does?
            
            # Let's write directly to audit container to avoid async issues in sync wrapper
            # Re-using the logic from audit.log_extraction_action essentially
            from app.db.cosmos import get_audit_container
            audit_container = get_audit_container()
            if audit_container:
                 audit_entry = {
                    "id": str(uuid.uuid4()),
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "user_id": user_id,
                    "user_email": user_email or "system@daom.ai",
                    "tenant_id": tenant_id or "default",
                    "action": audit_action,
                    "resource_type": AuditResource.EXTRACTION,
                    "resource_id": log.id,
                    "status": "SUCCESS" if status != "error" else "FAILURE",
                    "details": {
                        "model_id": model_id,
                        "filename": filename,
                        "job_id": job_id,
                        "error": error,
                        "llm_model": llm_model
                    },
                    "ip_address": "system",
                    "user_agent": "DaomBackend/ExtractionLogs"
                 }
                 audit_container.create_item(body=audit_entry)
        except Exception as audit_e:
            logger.error(f"[ExtractionLogs] Audit log failed: {audit_e}")

        return log
    except Exception as e:
        logger.error(f"[ExtractionLogs] Save failed: {e}")
        return None


def get_logs_by_model(model_id: str, limit: int = 50) -> List[ExtractionLog]:
    """Get extraction logs for a specific model"""
    container = get_extractions_container()
    
    if not container:
        return []
    
    try:
        # Only return extraction_logs (Jobs are temp processing records)
        query = f"""
            SELECT TOP {limit} * FROM c 
            WHERE c.model_id = @model_id 
            AND (NOT IS_DEFINED(c.type) OR c.type = '{ExtractionType.LOG.value}')
            ORDER BY c.created_at DESC
        """
        items = list(container.query_items(
            query=query,
            parameters=[{"name": "@model_id", "value": model_id}],
            enable_cross_partition_query=False
        ))
        return [ExtractionLog(**item) for item in items]
    except Exception as e:
        logger.error(f"[ExtractionLogs] Query failed: {e}")
        return []


def get_all_logs(limit: int = 100) -> List[ExtractionLog]:
    """Get all recent extraction logs"""
    container = get_extractions_container()
    
    if not container:
        return []
    
    try:
        # Only return extraction_logs (Jobs are temp processing records)
        query = f"""
            SELECT TOP {limit} * FROM c 
            WHERE (NOT IS_DEFINED(c.type) OR c.type = '{ExtractionType.LOG.value}')
            ORDER BY c.created_at DESC
        """
        items = list(container.query_items(
            query=query,
            enable_cross_partition_query=True
        ))
        return [ExtractionLog(**item) for item in items]
    except Exception as e:
        logger.error(f"[ExtractionLogs] Query failed: {e}")
        return []


def get_logs_by_user(user_id: str, limit: int = 100) -> List[ExtractionLog]:
    """Get extraction logs for a specific user"""
    container = get_extractions_container()
    
    if not container:
        return []
    
    try:
        # Only return extraction_logs (Jobs are temp processing records)
        query = f"""
            SELECT TOP {limit} * FROM c 
            WHERE c.user_id = @user_id 
            AND (NOT IS_DEFINED(c.type) OR c.type = '{ExtractionType.LOG.value}')
            ORDER BY c.created_at DESC
        """
        items = list(container.query_items(
            query=query,
            parameters=[{"name": "@user_id", "value": user_id}],
            enable_cross_partition_query=True
        ))
        return [ExtractionLog(**item) for item in items]
    except Exception as e:
        logger.error(f"[ExtractionLogs] Query failed: {e}")
        return []


def get_log_by_id(log_id: str, model_id: str) -> Optional[ExtractionLog]:
    """Get a single log by ID"""
    container = get_extractions_container()
    
    if not container:
        return None
    
    try:
        item = container.read_item(item=log_id, partition_key=model_id)
        return ExtractionLog(**item)
    except Exception:
        return None


def get_log(log_id: str) -> Optional[ExtractionLog]:
    """Get log by ID via query (useful when partition key is unknown)"""
    container = get_extractions_container()
    
    if not container:
        return None
    
    try:
        query = "SELECT * FROM c WHERE c.id = @id"
        items = list(container.query_items(
            query=query,
            parameters=[{"name": "@id", "value": log_id}],
            enable_cross_partition_query=True
        ))
        if items:
            return ExtractionLog(**items[0])
        return None
    except Exception as e:
        logger.error(f"[ExtractionLogs] Get log failed: {e}")
        return None


def update_log_status(log_id: str, status: str, preview_data: Optional[dict] = None) -> bool:
    """Update just the status (and optionally preview_data) of an existing log"""
    container = get_extractions_container()
    
    if not container:
        return False
    
    try:
        # Get existing log
        log = get_log(log_id)
        if not log:
            logger.warning(f"[ExtractionLogs] Log {log_id} not found for status update")
            return False
        
        # Update fields
        log_dict = log.model_dump()
        log_dict["status"] = status
        log_dict["updated_at"] = datetime.utcnow().isoformat()
        log_dict["type"] = ExtractionType.LOG.value
        
        if preview_data:
            log_dict["preview_data"] = preview_data
        
        container.upsert_item(log_dict)
        logger.info(f"[ExtractionLogs] Updated log {log_id} status to {status}")
        return True
    except Exception as e:
        logger.error(f"[ExtractionLogs] Update status failed: {e}")
        return False


def delete_logs(log_ids: List[str]) -> int:
    """Delete multiple extraction logs by IDs"""
    container = get_extractions_container()
    
    if not container:
        return 0
    
    deleted_count = 0
    for log_id in log_ids:
        try:
            # Get the log first to get the partition key (model_id)
            log = get_log(log_id)
            if log:
                container.delete_item(item=log_id, partition_key=log.model_id)
                deleted_count += 1
                logger.info(f"[ExtractionLogs] Deleted log {log_id}")
        except Exception as e:
            logger.error(f"[ExtractionLogs] Failed to delete log {log_id}: {e}")
    
    return deleted_count
