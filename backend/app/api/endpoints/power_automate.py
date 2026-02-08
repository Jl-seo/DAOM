"""
Power Automate Custom Connector API Endpoints
Provides clean, well-documented endpoints for Power Automate integration
"""
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from app.core.auth import get_current_user, CurrentUser
from app.services import extraction_logs
from app.services.models import load_models
from app.services.storage import upload_file_to_blob
from app.core.group_permission_utils import get_accessible_model_ids
from app.core.auth import is_super_admin
import logging
import uuid

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================
# Request/Response Models
# ============================================

class UploadResponse(BaseModel):
    """Response for document upload"""
    job_id: str
    status: str
    message: str
    poll_url: str


class ExtractionResultResponse(BaseModel):
    """Response for extraction result"""
    job_id: str
    status: str  # pending | processing | completed | failed
    model_id: Optional[str] = None
    model_name: Optional[str] = None
    filename: Optional[str] = None
    extracted_data: Optional[Dict[str, Any]] = None
    confidence: Optional[float] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None  # Passthrough user data
    created_at: Optional[str] = None


class ModelInfo(BaseModel):
    """Model information for listing"""
    id: str
    name: str
    description: Optional[str] = None


class ModelsListResponse(BaseModel):
    """Response for models list"""
    models: List[ModelInfo]
    total: int


# ============================================
# Background Task for Extraction
# ============================================

async def run_extraction_with_metadata(
    job_id: str,
    model_id: str,
    file_urls: List[str],
    filenames: List[str],
    metadata: Optional[Dict[str, Any]] = None
):

    """Run extraction and store metadata alongside results"""
    from app.services.extraction_service import extraction_service
    from app.services.extraction_jobs import update_job
    from app.services.storage import download_blob_to_bytes
    import mimetypes

    try:
        # 1. Update Status
        update_job(job_id, status="analyzing")

        # 2. Download Primary File
        primary_url = file_urls[0]
        try:
            file_content = await download_blob_to_bytes(primary_url)
            if not file_content:
                raise ValueError("Downloaded file content is empty or None")
        except Exception as e:
             logger.error(f"[Connector] Failed to download {primary_url}: {e}")
             update_job(job_id, status="error", error=f"Download failed: {e}")
             return

        # 3. Detect MIME
        filename = filenames[0] if filenames else "unknown"
        mime_type, _ = mimetypes.guess_type(filename)

        # 4. Call Pure Extraction
        result = await extraction_service.run_extraction_pipeline(
            file_content=file_content,
            model_id=model_id,
            filename=filename,
            mime_type=mime_type or ""
        )
        
        # 5. Handle Result
        if "error" in result:
             update_job(job_id, status="error", error=result["error"])
        else:
             # Success -> Update Job
             update_job(
                job_id, 
                status="preview_ready", 
                preview_data=result
            )

        # 6. Update log with metadata if provided
        if metadata:
            log = extraction_logs.get_log(job_id)
            if log:
                extraction_logs.save_extraction_log(
                    model_id=log.model_id,
                    user_id=log.user_id,
                    filename=log.filename,
                    status=log.status,
                    file_url=log.file_url,
                    extracted_data=log.extracted_data,
                    log_id=job_id,
                    tenant_id=log.tenant_id,
                    metadata=metadata
                )
    except Exception as e:
        logger.error(f"[Connector] Extraction failed for job {job_id}: {e}")
        update_job(job_id, status="error", error=str(e))


# ============================================
# Endpoints
# ============================================

@router.post("/upload", response_model=UploadResponse,
             summary="📄 문서 업로드",
             description="파일을 업로드하고 추출 작업을 시작합니다. 비동기로 처리되며 job_id로 결과를 조회할 수 있습니다.")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="추출할 문서 파일 (PDF, 이미지 등)"),
    model_id: str = Form(..., description="사용할 추출 모델 ID"),
    metadata: Optional[str] = Form(None, description="사용자 정의 메타데이터 (JSON 문자열)"),
    webhook_url: Optional[str] = Form(None, description="완료 시 콜백 URL"),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Power Automate용 문서 업로드 엔드포인트.
    
    - 파일을 Azure Blob에 업로드
    - 비동기 추출 작업 시작
    - job_id 반환 (결과 조회용)
    """
    import json
    import os

    # ========== FILE TYPE VALIDATION ==========
    # Check 1: Extension validation
    ALLOWED_EXTENSIONS = {
        '.pdf', '.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp',
        '.xlsx', '.xls', '.csv',  # Excel/CSV — Azure DI Layout supports these
        '.docx',  # Word — Azure DI Layout supports this
    }
    file_ext = os.path.splitext(file.filename)[1].lower()

    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 파일 확장자입니다: {file_ext}. 지원 형식: PDF, 이미지, Excel, Word"
        )

    # Check 2: MIME type validation
    ALLOWED_MIME_TYPES = {
        'application/pdf',
        'image/jpeg',
        'image/png',
        'image/tiff',
        'image/bmp',
        'image/x-ms-bmp',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',  # .xlsx
        'application/vnd.ms-excel',  # .xls
        'text/csv',  # .csv
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',  # .docx
    }

    if file.content_type and file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 파일 타입입니다: {file.content_type}. 지원 형식: PDF, 이미지, Excel, Word"
        )

    # Parse metadata if provided
    # Parse metadata if provided
    parsed_metadata = None
    if metadata:
        try:
            parsed_metadata = json.loads(metadata)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="metadata must be valid JSON")

    # Upload file to blob
    file_content = await file.read()
    job_id = str(uuid.uuid4())

    try:
        file_url = upload_file_to_blob(file_content, file.filename, f"connector/{job_id}")
    except Exception as e:
        logger.error(f"[Connector] File upload failed: {e}")
        raise HTTPException(status_code=500, detail="File upload failed")

    # Create initial log entry with metadata
    extraction_logs.save_extraction_log(
        model_id=model_id,
        user_id=current_user.id,
        filename=file.filename,
        status="pending",
        file_url=file_url,
        log_id=job_id,
        job_id=job_id,
        tenant_id=current_user.tenant_id,
        user_name=current_user.name if hasattr(current_user, 'name') else None,
        user_email=current_user.email if hasattr(current_user, 'email') else None,
        metadata=parsed_metadata
    )

    # Start background extraction
    background_tasks.add_task(
        run_extraction_with_metadata,
        job_id=job_id,
        model_id=model_id,
        file_urls=[file_url],
        filenames=[file.filename],
        metadata=parsed_metadata
    )

    # Send webhook if provided
    if webhook_url:
        from app.services.webhook import send_webhook_background
        send_webhook_background(webhook_url, {
            "event": "extraction_started",
            "job_id": job_id,
            "model_id": model_id,
            "filename": file.filename
        })

    return UploadResponse(
        job_id=job_id,
        status="pending",
        message="추출 작업이 시작되었습니다",
        poll_url=f"/api/v1/connectors/result/{job_id}"
    )


@router.get("/result/{job_id}",
            summary="🔍 추출 결과 조회",
            description="Job ID로 추출 상태 및 결과를 조회합니다.")
async def get_extraction_result(
    job_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    추출 결과 조회. 
    
    - 완료 시: 200 + 추출 데이터
    - 처리 중: 202 + 현재 상태
    - 실패 시: 200 + error 필드
    """
    log = extraction_logs.get_log(job_id)

    if not log:
        raise HTTPException(status_code=404, detail="Job not found")

    # Get model name
    model_name = None
    try:
        from app.services.models import get_model_by_id
        model = get_model_by_id(log.model_id)
        if model:
            model_name = model.name
    except Exception:
        pass

    response_data = {
        "job_id": job_id,
        "status": log.status,
        "model_id": log.model_id,
        "model_name": model_name,
        "filename": log.filename,
        "extracted_data": log.extracted_data if log.status == "success" else None,
        "error": log.error if log.status == "error" else None,
        "metadata": log.metadata,
        "created_at": log.created_at
    }

    # Calculate confidence if available
    if log.extracted_data:
        confidences = []
        for field_data in log.extracted_data.values():
            if isinstance(field_data, dict) and "confidence" in field_data:
                confidences.append(field_data["confidence"])
        if confidences:
            response_data["confidence"] = sum(confidences) / len(confidences)

    # Return 202 if still processing (for async polling pattern)
    if log.status in ["pending", "processing"]:
        return JSONResponse(
            status_code=202,
            content=response_data,
            headers={
                "Retry-After": "5",
                "Location": f"/api/v1/connectors/result/{job_id}"
            }
        )

    return response_data


@router.get("/wait/{job_id}",
            summary="⏳ 추출 완료 대기",
            description="추출이 완료될 때까지 대기합니다 (Async Polling Pattern).")
async def wait_for_extraction(
    job_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    비동기 폴링 패턴 지원.
    Power Automate가 자동으로 폴링하며, 완료 시 결과를 반환합니다.
    """
    return await get_extraction_result(job_id, current_user)


@router.get("/models", response_model=ModelsListResponse,
            summary="📋 모델 목록 조회",
            description="사용 가능한 추출 모델 목록을 반환합니다 (권한 필터링 적용).")
async def list_available_models(
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    접근 가능한 모델 목록 반환.
    Super Admin은 모든 모델, 일반 사용자는 권한 있는 모델만 표시됩니다.
    """
    all_models = [m for m in load_models() if getattr(m, "is_active", True)]

    # Filter by permission
    if await is_super_admin(current_user):
        accessible = all_models
    else:
        accessible_ids = await get_accessible_model_ids(current_user.id, current_user.tenant_id)
        accessible = [m for m in all_models if m.id in accessible_ids]

    return ModelsListResponse(
        models=[
            ModelInfo(
                id=m.id,
                name=m.name,
                description=getattr(m, 'description', None)
            )
            for m in accessible
        ],
        total=len(accessible)
    )


@router.post("/cancel/{job_id}",
             summary="❌ 작업 취소",
             description="진행 중인 추출 작업을 취소합니다.")
async def cancel_extraction(
    job_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    진행 중인 작업 취소.
    이미 완료된 작업은 취소할 수 없습니다.
    """
    log = extraction_logs.get_log(job_id)

    if not log:
        raise HTTPException(status_code=404, detail="Job not found")

    if log.status in ["success", "error"]:
        raise HTTPException(status_code=400, detail="Cannot cancel completed job")

    # Update status to cancelled
    extraction_logs.save_extraction_log(
        model_id=log.model_id,
        user_id=log.user_id,
        filename=log.filename,
        status="cancelled",
        file_url=log.file_url,
        log_id=job_id,
        tenant_id=log.tenant_id,
        metadata=log.metadata,
        error="Cancelled by user"
    )

    return {"job_id": job_id, "status": "cancelled", "message": "작업이 취소되었습니다"}
