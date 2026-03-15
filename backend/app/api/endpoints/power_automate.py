"""
Power Automate Custom Connector API Endpoints
Provides clean, well-documented endpoints for Power Automate integration
"""
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, UploadFile, File, Form, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from app.core.auth import get_current_user, CurrentUser
from app.core.enums import ExtractionStatus
from app.services import extraction_logs
from app.services.models import load_models
from app.services.storage import upload_file_to_blob, upload_bytes_to_blob
from app.core.group_permission_utils import get_accessible_model_ids, get_model_role_by_group
from app.core.auth import is_super_admin
import logging
import uuid

logger = logging.getLogger(__name__)

router = APIRouter()

def is_valid_binary_magic(data: bytes) -> bool:
    """
    Check if the byte array starts with a known valid file signature (Magic Bytes).
    This guarantees we never accidentally corrupt a valid file by treating its content as Base64.
    """
    if len(data) < 4:
        return False
    # PDF
    if data.startswith(b'%PDF'): return True
    # JPEG
    if data.startswith(b'\xff\xd8\xff'): return True
    # PNG
    if data.startswith(b'\x89PNG\r\n\x1a\n'): return True
    # ZIP / Office OpenXML (XLSX, DOCX)
    if data.startswith(b'PK\x03\x04'): return True
    # Legacy Office (XLS, DOC)
    if data.startswith(b'\xd0\xcf\x11\xe0'): return True
    # TIFF
    if data.startswith(b'II*\x00') or data.startswith(b'MM\x00*'): return True
    return False

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
        from app.services.extraction_jobs import get_job
        job = await get_job(job_id)
        original_log_id = job.original_log_id if job else None
        
        log = None
        if original_log_id:
            log = await extraction_logs.get_log(original_log_id)
        
        if result.get("error"):
             await update_job(job_id, status=ExtractionStatus.ERROR.value, error=result["error"])
             if log:
                 await extraction_logs.save_extraction_log(
                     model_id=log.model_id, user_id=log.user_id, filename=log.filename,
                     status=ExtractionStatus.ERROR.value, file_url=log.file_url,
                     error=result["error"], log_id=log.id, tenant_id=log.tenant_id,
                     metadata=metadata or log.metadata, user_name=log.user_name, user_email=log.user_email
                 )
        else:
             # Success -> Update Job + Store extracted_data for connector result API
             extracted = result.get("guide_extracted", {})
             await update_job(
                job_id, 
                status=ExtractionStatus.SUCCESS.value, 
                preview_data=result,
                extracted_data=extracted
            )
             if log:
                 await extraction_logs.save_extraction_log(
                     model_id=log.model_id, user_id=log.user_id, filename=log.filename,
                     status=ExtractionStatus.SUCCESS.value, file_url=log.file_url,
                     extracted_data=extracted, preview_data=result,
                     log_id=log.id, tenant_id=log.tenant_id,
                     metadata=metadata or log.metadata, user_name=log.user_name, user_email=log.user_email,
                     token_usage=result.get("_token_usage")
                 )

    except Exception as e:
        logger.error(f"[Connector] Extraction failed for job {job_id}: {e}")
        from app.services.extraction_jobs import update_job, get_job
        await update_job(job_id, status=ExtractionStatus.ERROR.value, error=str(e))
        
        job = await get_job(job_id)
        if job and job.original_log_id:
            log = await extraction_logs.get_log(job.original_log_id)
            if log:
                await extraction_logs.save_extraction_log(
                    model_id=log.model_id, user_id=log.user_id, filename=log.filename,
                    status=ExtractionStatus.ERROR.value, file_url=log.file_url,
                    error=str(e), log_id=log.id, tenant_id=log.tenant_id,
                    metadata=metadata or log.metadata, user_name=log.user_name, user_email=log.user_email
                )


# ============================================
# Endpoints
# ============================================

class QueryResultItem(BaseModel):
    job_id: str
    status: str
    model_id: str
    filename: Optional[str] = None
    file_url: Optional[str] = None
    extracted_data: Optional[Dict[str, Any]] = None
    is_table: bool = False
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: str

class QueryResultList(BaseModel):
    total: int
    limit: int
    next_link: Optional[str] = Field(None, alias="@odata.nextLink")
    results: List[QueryResultItem]

class PAFileItem(BaseModel):
    model_config = ConfigDict(extra="ignore")  # Ignore metadata injected by Power Automate Array Variables
    name: str
    contentBytes: Optional[Any] = None  # Base64 string or Power Automate structured dict {"$content": "..."}

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

    # ========== PERMISSION CHECK ==========
    is_super = await is_super_admin(current_user)
    if not is_super:
        model_role = await get_model_role_by_group(
            current_user.id,
            current_user.tenant_id,
            payload.model_id,
            access_token=getattr(current_user, 'access_token', None)
        )
        if model_role is None:
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to use this model"
            )

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
    
    # Power Automate array variables may pass the raw JSON File object natively.
    raw_content = payload.file.contentBytes
    
    if raw_content is None:
        raise HTTPException(status_code=400, detail="Missing file content. Please provide 'contentBytes'.")

    b64_str = ""
    
    if isinstance(raw_content, dict):
        b64_str = raw_content.get("$content", "")
    elif isinstance(raw_content, str):
        b64_str = raw_content.strip()
        # Fallback for stringified json
        if b64_str.startswith("{") and "$content" in b64_str:
            try:
                content_dict = json.loads(b64_str)
                b64_str = content_dict.get("$content", b64_str)
            except json.JSONDecodeError:
                pass
    else:
        raise HTTPException(status_code=400, detail="contentBytes must be a string or object.")
    
    # DoS Prevention: Limit base64 length (approx 15MB)
    if len(b64_str) > 20_000_000:
        raise HTTPException(status_code=413, detail="File too large. Maximum supported size via JSON connector is 15MB.")

    # Clean data URL prefixes and whitespaces
    if "," in b64_str:
        b64_str = b64_str.split(",", 1)[1]
        
        # Convert URL-safe base64 to standard base64 before stripping
    b64_str = b64_str.replace('-', '+').replace('_', '/')
    b64_str = re.sub(r'[^a-zA-Z0-9+/=]', '', b64_str)
    
    # Pad if necessary
    padding_needed = len(b64_str) % 4
    if padding_needed:
        b64_str += '=' * (4 - padding_needed)

    try:
        file_content = base64.b64decode(b64_str, validate=True)
        
        # THE ULTIMATE ROOT CAUSE FIX: Power Automate Double-Encoding.
        # Fallback: if the first decode did NOT yield a valid binary signature (like %PDF),
        # but IT IS a base64 string that, when decoded AGAIN, yields a valid binary, accept it.
        # This guarantees we NEVER accidentally corrupt standard valid binaries.
        import binascii
        if not is_valid_binary_magic(file_content):
            current_decode = file_content
            for _ in range(2):
                try:
                    next_layer = base64.b64decode(current_decode, validate=True)
                    if is_valid_binary_magic(next_layer):
                        file_content = next_layer
                        break
                    current_decode = next_layer
                except binascii.Error:
                    break
                    
    except Exception as e:
        raise HTTPException(status_code=400, detail="유효하지 않은 Base64 파일 내용입니다.")
    job_id = str(uuid.uuid4())

    try:
        file_url = await upload_bytes_to_blob(file_content, filename, f"connector/{job_id}")
    except Exception as e:
        logger.error(f"[Connector] File upload failed: {e}")
        raise HTTPException(status_code=500, detail="File upload failed")

    # Create initial log entry with metadata
    log = await extraction_logs.save_extraction_log(
        model_id=payload.model_id,
        user_id=current_user.id,
        filename=filename,
        status="pending",
        file_url=file_url,
        tenant_id=current_user.tenant_id,
        user_name=current_user.name if hasattr(current_user, 'name') else None,
        user_email=current_user.email if hasattr(current_user, 'email') else None,
        metadata=parsed_metadata
    )

    # Create extraction job so frontend doesn't throw 404
    from app.services import extraction_jobs
    job = await extraction_jobs.create_job(
        model_id=payload.model_id,
        user_id=current_user.id,
        user_name=current_user.name if hasattr(current_user, 'name') else None,
        user_email=current_user.email if hasattr(current_user, 'email') else None,
        filename=filename,
        file_url=file_url,
        file_urls=[file_url],
        filenames=[filename],
        original_log_id=log.id if log else None,
        tenant_id=current_user.tenant_id
    )

    # Update log with proper job_id
    if log:
        await extraction_logs.save_extraction_log(
            model_id=payload.model_id,
            user_id=current_user.id,
            filename=filename,
            status="pending",
            file_url=file_url,
            log_id=log.id,
            job_id=job.id,
            tenant_id=current_user.tenant_id,
            metadata=parsed_metadata,
            user_name=current_user.name if hasattr(current_user, 'name') else None,
            user_email=current_user.email if hasattr(current_user, 'email') else None
        )

    # Start background extraction using job.id (for updates) but PA polls using log.id
    background_tasks.add_task(
        run_extraction_with_metadata,
        job_id=job.id,
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
            "job_id": job.id,
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

from pydantic import model_validator
import json

class PABatchUploadRequest(BaseModel):
    model_id: str
    metadata: Optional[str] = None
    files: List[PAFileItem]

    @model_validator(mode='before')
    @classmethod
    def parse_stringified_files(cls, data: Any) -> Any:
        # Power Automate sometimes passes array variables as stringified JSON
        if isinstance(data, dict):
            files_val = data.get("files")
            if isinstance(files_val, str):
                try:
                    data["files"] = json.loads(files_val)
                except json.JSONDecodeError:
                    pass
        return data

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
            
            raw_content = file_item.contentBytes
            
            if raw_content is None:
                results.append(BatchUploadItemResponse(
                    filename=filename,
                    status="error",
                    message="Missing file content",
                    error="Please provide 'contentBytes'."
                ))
                continue

            b64_str = ""
            
            if isinstance(raw_content, dict):
                b64_str = raw_content.get("$content", "")
            elif isinstance(raw_content, str):
                b64_str = raw_content.strip()
                if b64_str.startswith("{") and "$content" in b64_str:
                    try:
                        content_dict = json.loads(b64_str)
                        b64_str = content_dict.get("$content", b64_str)
                    except json.JSONDecodeError:
                        # CRITICAL FIX: If Power Automate stringified the content object with broken escaping,
                        # json.loads() fails. We MUST extract the base64 using regex to prevent the
                        # "$content-type":"application/pdf" characters from being blindly parsed as base64 bytes!
                        import re
                        match = re.search(r'"\$content"\s*:\s*"([^"]+)"', b64_str)
                        if match:
                            b64_str = match.group(1)
                        else:
                            import logging
                            logging.getLogger("uvicorn.error").error(f"[PA-DEBUG] Failed to regex extract $content from PA JSON string.")
                            # Cannot recover safely
                            pass
            else:
                raise ValueError("contentBytes must be a string or object.")
                
            # FIX: If Power Automate fallback expression intentionally injected an empty string (''), skip it
            if not b64_str:
                continue
            
            # DoS Prevention: Limit base64 length (approx 15MB) per file
            if len(b64_str) > 20_000_000:
                results.append(BatchUploadItemResponse(
                    filename=filename,
                    status="error",
                    message="파일 업로드 스킵됨",
                    error="File too large. Maximum supported size via JSON connector is 15MB."
                ))
                continue

            if "," in b64_str:
                import logging
                logging.getLogger("uvicorn.error").error(f"[PA-DEBUG] Data URI removed. Snippet: {b64_str[:50]}")
                b64_str = b64_str.split(",", 1)[1]
            
            import logging
            pa_logger = logging.getLogger("uvicorn.error")
            pa_logger.error(f"[PA-DEBUG] Before Replace: len={len(b64_str)} snippet={b64_str[:50]} end={b64_str[-20:]}")
            
            # Convert URL-safe base64 to standard base64 before stripping
            b64_str = b64_str.replace('-', '+').replace('_', '/')
            pa_logger.error(f"[PA-DEBUG] After Replace: len={len(b64_str)} snippet={b64_str[:50]}")
            
            b64_str = re.sub(r'[^a-zA-Z0-9+/=]', '', b64_str)
            pa_logger.error(f"[PA-DEBUG] After Strip: len={len(b64_str)} snippet={b64_str[:50]}")
            
            padding_needed = len(b64_str) % 4
            if padding_needed:
                b64_str += '=' * (4 - padding_needed)
            pa_logger.error(f"[PA-DEBUG] After Padding: len={len(b64_str)}")
                
            file_content = base64.b64decode(b64_str, validate=True)
            pa_logger.error(f"[PA-DEBUG] Decoded Bytes len: {len(file_content)}, start: {file_content[:10]}")
            
            # THE ULTIMATE ROOT CAUSE FIX: Power Automate Double-Encoding.
            # Fallback: if the first decode did NOT yield a valid binary signature (like %PDF),
            # but IT IS a base64 string that, when decoded AGAIN, yields a valid binary, accept it.
            # This guarantees we NEVER accidentally corrupt standard valid binaries.
            import binascii
            if not is_valid_binary_magic(file_content):
                current_decode = file_content
                for _ in range(2):
                    try:
                        next_layer = base64.b64decode(current_decode, validate=True)
                        if is_valid_binary_magic(next_layer):
                            file_content = next_layer
                            pa_logger.error(f"[PA-DEBUG] DOUBLE-DECODED successfully. Bytes len: {len(file_content)}, start: {file_content[:10]}")
                            break
                        current_decode = next_layer
                    except binascii.Error:
                        break
                
            job_id = str(uuid.uuid4())
            file_url = await upload_bytes_to_blob(file_content, filename, f"connector/{job_id}")

            pa_debug_str = None
            if filename != "document.pdf":
                pa_debug_str = f"LEN={len(file_content)} | RAW: {str(raw_content)[:100]}... | PRE-DECODE: {b64_str[:80]}..."
                
            log = await extraction_logs.save_extraction_log(
                model_id=payload.model_id,
                user_id=current_user.id,
                filename=filename,
                status="pending",
                file_url=file_url,
                tenant_id=current_user.tenant_id,
                user_name=current_user.name if hasattr(current_user, 'name') else None,
                user_email=current_user.email if hasattr(current_user, 'email') else None,
                metadata=parsed_metadata,
                debug_data={"pa_debug": pa_debug_str} if pa_debug_str else None
            )
            
            from app.services import extraction_jobs
            job = await extraction_jobs.create_job(
                model_id=payload.model_id,
                user_id=current_user.id,
                user_name=current_user.name if hasattr(current_user, 'name') else None,
                user_email=current_user.email if hasattr(current_user, 'email') else None,
                filename=filename,
                file_url=file_url,
                file_urls=[file_url],
                filenames=[filename],
                original_log_id=log.id if log else None,
                tenant_id=current_user.tenant_id
            )

            if log:
                await extraction_logs.save_extraction_log(
                    model_id=payload.model_id,
                    user_id=current_user.id,
                    filename=filename,
                    status="pending",
                    file_url=file_url,
                    log_id=log.id,
                    job_id=job.id,
                    tenant_id=current_user.tenant_id,
                    metadata=parsed_metadata,
                    user_name=current_user.name if hasattr(current_user, 'name') else None,
                    user_email=current_user.email if hasattr(current_user, 'email') else None
                )

            background_tasks.add_task(
                run_extraction_with_metadata,
                job_id=job.id,
                model_id=payload.model_id,
                file_urls=[file_url],
                filenames=[filename],
                metadata=parsed_metadata
            )

            results.append(BatchUploadItemResponse(
                filename=filename,
                job_id=log.id,
                status="pending",
                message="추출 작업이 시작되었습니다",
                poll_url=f"/api/v1/connectors/result/{log.id}"
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
    log = await extraction_logs.get_log(job_id)

    if not log:
        raise HTTPException(status_code=404, detail="Job not found")

    # ========== HYDRATE OFFLOADED DATA ==========
    # If the payload was massive (e.g. 100+ rows), it might have been offloaded to Blob Storage
    if log.extracted_data and isinstance(log.extracted_data, dict):
        if log.extracted_data.get("source") == "blob_storage" and log.extracted_data.get("blob_path"):
            try:
                from app.services.storage import load_json_from_blob
                hydrated = await load_json_from_blob(log.extracted_data["blob_path"])
                if hydrated is not None:
                    log.extracted_data = hydrated
            except Exception as e:
                logger.error(f"[Connector] Failed to hydrate extracted_data from blob: {e}")

    # ========== IDOR Security Check ==========
    if log.user_id != current_user.id:
        is_super = await is_super_admin(current_user)
        if not is_super:
            # Maybe they are admin of this model?
            from app.core.permissions import check_model_permission
            has_permission = await check_model_permission(current_user, log.model_id, "Admin")
            if not has_permission:
                raise HTTPException(status_code=403, detail="Not authorized to view this extraction result")

    # Get model name
    model_name = None
    try:
        from app.services.models import get_model_by_id
        model = await get_model_by_id(log.model_id)
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
        "file_url": log.file_url,
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



@router.get("/results", response_model=QueryResultList, response_model_by_alias=True,
            summary="🔍 다중 문서 결과 조회 (List Extractions)",
            description="모델별, 기간별, 상태별 및 메타데이터 필터를 통해 추출 결과를 배열(Array) 형태로 조회합니다. (Pagination 지원)")
async def query_extraction_results(
    request: Request,
    model_id: str,
    status: Optional[str] = Query(None, description="상태 필터 (success, error, pending 등)"),
    start_date: Optional[str] = Query(None, description="ISO 8601 UTC 예: 2026-02-23T00:00:00Z"),
    end_date: Optional[str] = Query(None, description="ISO 8601 UTC 예: 2026-02-23T23:59:59Z"),
    filename_contains: Optional[str] = Query(None, description="파일명 포함 단어 (대소문자 무시)"),
    metadata_key: Optional[str] = Query(None, description="메타데이터 필터용 Key"),
    metadata_value: Optional[str] = Query(None, description="메타데이터 필터용 Value"),
    continuation_token: Optional[str] = Query(None, description="다음 페이지용 토큰"),
    limit: int = Query(100, ge=1, le=100, description="최대 100건 제한 (파워오토메이트 페이징용)"),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    조건에 맞는 추출 이력(Job) 리스트를 한 번의 DB 조회로 가져오는 페이징 API.
    100건이 넘더라도 @odata.nextLink 값을 던져주면 Power Automate가 자체적으로 합칩니다.
    """
    import base64
    import json
    import asyncio
    import urllib.parse
    from app.services.extraction_logs import get_extractions_container
    
    # ========== PERMISSION CHECK ==========
    is_super = await is_super_admin(current_user)
    if not is_super:
        model_role = await get_model_role_by_group(
            current_user.id,
            current_user.tenant_id,
            model_id,
            access_token=getattr(current_user, 'access_token', None)
        )
        if not model_role or model_role not in ["View", "Admin"]:
            raise HTTPException(status_code=403, detail="Not authorized to query this model")

    container = get_extractions_container()
    if not container:
        raise HTTPException(status_code=500, detail="Database not configured")

    # ========== BUILD QUERY (Optimization: SINGLE QUERY) ==========
    query = """
        SELECT c.id AS job_id, c.status, c.model_id, c.filename, c.file_url, c.extracted_data, c.error, c.metadata, c.created_at
        FROM c 
        WHERE c.tenant_id = @tenant_id 
          AND c.model_id = @model_id
          AND (NOT IS_DEFINED(c.type) OR c.type = 'extraction_log')
    """
    parameters = [
        {"name": "@tenant_id", "value": current_user.tenant_id},
        {"name": "@model_id", "value": model_id}
    ]

    if status:
        query += " AND c.status = @status"
        parameters.append({"name": "@status", "value": status})
        
    if start_date:
        query += " AND (c.created_at >= @start_date)"
        parameters.append({"name": "@start_date", "value": start_date})
        
    if end_date:
        query += " AND (c.created_at <= @end_date)"
        parameters.append({"name": "@end_date", "value": end_date})
        
    if filename_contains:
        query += " AND CONTAINS(LOWER(c.filename), LOWER(@filename_contains))"
        parameters.append({"name": "@filename_contains", "value": filename_contains})
        
    if metadata_key and metadata_value:
        query += f" AND c.metadata['{metadata_key}'] = @metadata_value"
        parameters.append({"name": "@metadata_value", "value": metadata_value})

    query += " ORDER BY c.created_at DESC"

    # ========== EXECUTE PAGINATED QUERY ==========
    try:
        safe_token = continuation_token
        query_iterable = container.query_items(
            query=query,
            parameters=parameters,
            partition_key=model_id,
            max_item_count=limit
        )

        pager = query_iterable.by_page(continuation_token=safe_token)
        page = await pager.__anext__()
        raw_items = [item async for item in page]
        next_chunk_token = pager.continuation_token
    except StopIteration:
        raw_items = []
        next_chunk_token = None
    except Exception as e:
        logger.error(f"[Connector] Query execution failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to query items")

    # ========== HYDRATE BLOBS (Concurrency Safeguard) ==========
    sem = asyncio.Semaphore(10)
    
    async def process_item(item):
        extracted_data = item.get("extracted_data")
        if extracted_data and isinstance(extracted_data, dict):
            if extracted_data.get("source") == "blob_storage" and extracted_data.get("blob_path"):
                try:
                    from app.services.storage import load_json_from_blob
                    async with sem:
                        hydrated = await load_json_from_blob(extracted_data["blob_path"])
                    if hydrated is not None:
                        extracted_data = hydrated
                except Exception as e:
                    logger.error(f"[Connector] Hydration for {item.get('job_id')} failed: {e}")
                    extracted_data = None
                    
        return QueryResultItem(
            job_id=item.get("job_id", ""),
            status=item.get("status", "pending"),
            model_id=item.get("model_id", ""),
            filename=item.get("filename"),
            file_url=item.get("file_url"),
            extracted_data=extracted_data,
            is_table=isinstance(extracted_data, list),
            error=item.get("error"),
            metadata=item.get("metadata"),
            created_at=item.get("created_at", "")
        )

    hydrated_results = await asyncio.gather(*(process_item(item) for item in raw_items))

    # ========== ASSEMBLE PAGINATED RESPONSE ==========
    next_url = None
    if next_chunk_token:
        qs = dict(request.query_params)
        qs["continuation_token"] = next_chunk_token
        next_url = "?" + urllib.parse.urlencode(qs)

    response_data = {
        "total": len(hydrated_results),
        "limit": limit,
        "results": hydrated_results
    }
    if next_url:
        response_data["@odata.nextLink"] = next_url

    return response_data


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
    all_models = [m for m in await load_models() if getattr(m, "is_active", True)]

    # Filter by permission
    if await is_super_admin(current_user):
        accessible = all_models
    else:
        accessible_ids = await get_accessible_model_ids(
            current_user.id,
            current_user.tenant_id,
            access_token=getattr(current_user, 'access_token', None)
        )
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
    log = await extraction_logs.get_log(job_id)

    if not log:
        raise HTTPException(status_code=404, detail="Job not found")

    if log.status in ["success", "error"]:
        raise HTTPException(status_code=400, detail="Cannot cancel completed job")

    # Update status to cancelled
    await extraction_logs.save_extraction_log(
        model_id=log.model_id,
        user_id=log.user_id,
        filename=log.filename,
        status="cancelled",
        file_url=log.file_url,
        log_id=job_id,
        tenant_id=getattr(log, 'tenant_id', 'default'),
        user_name=getattr(log, 'user_name', None),
        user_email=getattr(log, 'user_email', None),
        metadata=log.metadata,
        error="Cancelled by user"
    )

    return {"job_id": job_id, "status": "cancelled", "message": "작업이 취소되었습니다"}
