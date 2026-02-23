"""
Power Automate Custom Connector API Endpoints
Provides clean, well-documented endpoints for Power Automate integration
"""
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from app.core.auth import get_current_user, CurrentUser
from app.core.enums import ExtractionStatus
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
        await update_job(job_id, status=ExtractionStatus.ANALYZING.value)

        # 2. Download Primary File
        primary_url = file_urls[0]
        try:
            file_content = await download_blob_to_bytes(primary_url)
            if not file_content:
                raise ValueError("Downloaded file content is empty or None")
        except Exception as e:
             logger.error(f"[Connector] Failed to download {primary_url}: {e}")
             await update_job(job_id, status=ExtractionStatus.ERROR.value, error=f"Download failed: {e}")
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
        if result.get("error"):
             await update_job(job_id, status=ExtractionStatus.ERROR.value, error=result["error"])
        else:
             # Success -> Update Job + Store extracted_data for connector result API
             extracted = result.get("guide_extracted", {})
             await update_job(
                job_id, 
                status=ExtractionStatus.SUCCESS.value, 
                preview_data=result,
                extracted_data=extracted
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
        await update_job(job_id, status=ExtractionStatus.ERROR.value, error=str(e))


# ============================================
# Endpoints
# ============================================

class PAFileItem(BaseModel):
    name: str
    contentBytes: str  # Base64 encoded content

class PAUploadRequest(BaseModel):
    model_id: str
    metadata: Optional[str] = None
    webhook_url: Optional[str] = None
    file: PAFileItem

@router.post("/upload", response_model=UploadResponse,
             summary="📄 문서 업로드 (JSON)",
             description="JSON/Base64를 통해 단건 파일을 업로드하고 추출을 시작합니다. (Multipart의 한글 파일명 깨짐 버그 완벽 방지)")
async def upload_document(
    background_tasks: BackgroundTasks,
    payload: PAUploadRequest,
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
        '.xlsx', '.xls', '.csv',  # Excel/CSV
        '.docx',  # Word
    }
    
    filename = payload.file.name if payload.file.name else "document"
    file_ext = os.path.splitext(filename)[1].lower()

    # Fallback if extension is somehow missing from JSON (very rare now)
    if not file_ext:
        file_ext = ".pdf" # Default fallback
        filename = f"{filename}{file_ext}"

    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 파일 확장자입니다: {file_ext}. 지원 형식: PDF, 이미지, Excel, Word"
        )

    # Parse metadata if provided
    parsed_metadata = None
    if payload.metadata:
        try:
            parsed_metadata = json.loads(payload.metadata)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="metadata must be valid JSON")

    # Decode base64 file content securely
    import base64
    import re
    
    # Power Automate sometimes passes dicts stringified like "{\"$content-type\":\"...\",\"$content\":\"base64str\"}"
    b64_str = payload.file.contentBytes.strip()
    
    # Extract just the base64 part if it's a JSON string from Power Automate
    if b64_str.startswith("{") and "$content" in b64_str:
        try:
            content_dict = json.loads(b64_str)
            b64_str = content_dict.get("$content", b64_str)
        except json.JSONDecodeError:
            pass

    # Clean data URL prefixes and whitespaces
    if "," in b64_str:
        b64_str = b64_str.split(",", 1)[1]
    b64_str = re.sub(r'[^a-zA-Z0-9+/=]', '', b64_str)
    
    # Pad if necessary
    padding_needed = len(b64_str) % 4
    if padding_needed:
        b64_str += '=' * (4 - padding_needed)

    try:
        file_content = base64.b64decode(b64_str, validate=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail="유효하지 않은 Base64 파일 내용입니다.")
    job_id = str(uuid.uuid4())

    try:
        file_url = upload_file_to_blob(file_content, filename, f"connector/{job_id}")
    except Exception as e:
        logger.error(f"[Connector] File upload failed: {e}")
        raise HTTPException(status_code=500, detail="File upload failed")

    # Create initial log entry with metadata
    extraction_logs.save_extraction_log(
        model_id=payload.model_id,
        user_id=current_user.id,
        filename=filename,
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
        model_id=payload.model_id,
        file_urls=[file_url],
        filenames=[filename],
        metadata=parsed_metadata
    )

    # Send webhook if provided
    if payload.webhook_url:
        from app.services.webhook import send_webhook_background
        send_webhook_background(payload.webhook_url, {
            "event": "extraction_started",
            "job_id": job_id,
            "model_id": payload.model_id,
            "filename": filename
        })

    # Return JSONResponse specifically to inject the Location and Retry-After headers
    return JSONResponse(
        status_code=202,
        content={
            "job_id": job_id,
            "status": "pending",
            "message": "추출 작업이 시작되었습니다",
            "poll_url": f"/api/v1/connectors/result/{job_id}"
        },
        headers={
            "Location": f"/api/v1/connectors/result/{job_id}",
            "Retry-After": "5"
        }
    )


class BatchUploadItemResponse(BaseModel):
    filename: str
    job_id: Optional[str] = None
    status: str
    message: str
    poll_url: Optional[str] = None
    error: Optional[str] = None

class BatchUploadResponse(BaseModel):
    batch_status: str
    message: str
    results: List[BatchUploadItemResponse]

class PABatchUploadRequest(BaseModel):
    model_id: str
    metadata: Optional[str] = None
    files: List[PAFileItem]

@router.post("/batch-upload", response_model=BatchUploadResponse,
             summary="📑 일괄 문서 업로드 (JSON/Base64)",
             description="Base64로 인코딩된 여러 파일을 순차적으로 업로드하고 각각의 추출 작업을 시작합니다.")
async def batch_upload_documents_json(
    background_tasks: BackgroundTasks,
    payload: PABatchUploadRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    import json
    import os
    import base64

    ALLOWED_EXTENSIONS = {
        '.pdf', '.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp',
        '.xlsx', '.xls', '.csv', '.docx'
    }

    if len(payload.files) > 20:
        raise HTTPException(status_code=400, detail="최대 20개까지만 동시에 업로드할 수 있습니다.")

    parsed_metadata = None
    if payload.metadata:
        try:
            parsed_metadata = json.loads(payload.metadata)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="metadata must be valid JSON")

    results = []
    
    for file_item in payload.files:
        filename = file_item.name if file_item.name else "document"
        file_ext = os.path.splitext(filename)[1].lower()
        
        if not file_ext:
            file_ext = ".pdf" # default for batch if totally blind
            filename = f"{filename}{file_ext}"
            
        if file_ext not in ALLOWED_EXTENSIONS:
            results.append(BatchUploadItemResponse(
                filename=file_item.name,
                status="error",
                message="지원하지 않는 파일 확장자입니다",
                error=f"Invalid extension {file_ext}"
            ))
            continue

        try:
            # Decode base64 securely for Batch
            import re
            b64_str = file_item.contentBytes.strip()
            
            if b64_str.startswith("{") and "$content" in b64_str:
                try:
                    content_dict = json.loads(b64_str)
                    b64_str = content_dict.get("$content", b64_str)
                except json.JSONDecodeError:
                    pass

            if "," in b64_str:
                b64_str = b64_str.split(",", 1)[1]
            b64_str = re.sub(r'[^a-zA-Z0-9+/=]', '', b64_str)
            
            padding_needed = len(b64_str) % 4
            if padding_needed:
                b64_str += '=' * (4 - padding_needed)
                
            file_content = base64.b64decode(b64_str, validate=True)
            job_id = str(uuid.uuid4())
            file_url = upload_file_to_blob(file_content, filename, f"connector/{job_id}")

            extraction_logs.save_extraction_log(
                model_id=payload.model_id,
                user_id=current_user.id,
                filename=filename,
                status="pending",
                file_url=file_url,
                log_id=job_id,
                job_id=job_id,
                tenant_id=current_user.tenant_id,
                user_name=current_user.name if hasattr(current_user, 'name') else None,
                user_email=current_user.email if hasattr(current_user, 'email') else None,
                metadata=parsed_metadata
            )

            background_tasks.add_task(
                run_extraction_with_metadata,
                job_id=job_id,
                model_id=payload.model_id,
                file_urls=[file_url],
                filenames=[filename],
                metadata=parsed_metadata
            )

            results.append(BatchUploadItemResponse(
                filename=filename,
                job_id=job_id,
                status="pending",
                message="추출 작업이 시작되었습니다",
                poll_url=f"/api/v1/connectors/result/{job_id}"
            ))
        except Exception as e:
            logger.error(f"[Connector Batch] Error uploading {filename}: {e}")
            results.append(BatchUploadItemResponse(
                filename=filename,
                status="error",
                message="업로드 처리 중 오류 발생",
                error=str(e)
            ))

    response_status = "success" if any(r.status == "pending" for r in results) else "error"
    
    # Critical for Power Automate 2026 async pattern: Include Location and Retry-After
    headers = {}
    if response_status == "success" and results:
        # Since this is a batch, we point the primary polling location to the first job
        # (Users can map over the 'results' array for individual status later)
        first_job = next((r.job_id for r in results if r.job_id), None)
        if first_job:
            headers["Location"] = f"/api/v1/connectors/result/{first_job}"
            headers["Retry-After"] = "10"

    return JSONResponse(
        status_code=202,
        content={
            "batch_status": response_status,
            "message": "일괄 업로드 처리가 완료되었습니다.",
            "results": [r.model_dump() for r in results]
        },
        headers=headers if headers else None
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

    # Support both legacy "success" and new enum status codes
    is_done = log.status in ["success", ExtractionStatus.SUCCESS.value, ExtractionStatus.PREVIEW_READY.value]
    is_err = log.status in ["error", ExtractionStatus.ERROR.value, ExtractionStatus.FAILED.value]

    response_data = {
        "job_id": job_id,
        "status": log.status,
        "model_id": log.model_id,
        "model_name": model_name,
        "filename": log.filename,
        "extracted_data": log.extracted_data if is_done else None,
        "is_table": isinstance(log.extracted_data, list) if log.extracted_data else False,
        "error": log.error if is_err else None,
        "metadata": log.metadata,
        "created_at": log.created_at
    }

    # Calculate confidence if available
    if log.extracted_data and isinstance(log.extracted_data, dict):
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
