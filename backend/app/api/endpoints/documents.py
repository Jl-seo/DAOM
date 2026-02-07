from fastapi import APIRouter, UploadFile, File, HTTPException, Query
import logging
from app.schemas.document import DocumentUploadResponse, AnalysisResponse, AnalysisRequest
from app.services.storage import upload_file_to_blob
from app.services.doc_intel import extract_content_from_url
from app.services.llm import analyze_document_content
from app.services.models import get_model_by_id
from app.services.extraction_logs import save_extraction_log, get_logs_by_model, get_all_logs
from app.core.enums import ExtractionStatus
from typing import Optional

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(file: UploadFile = File(...)):
    if not file.filename.endswith(('.pdf', '.jpg', '.jpeg', '.png')):
        raise HTTPException(status_code=400, detail="Invalid file type")

    try:
        file_url = await upload_file_to_blob(file)
        return DocumentUploadResponse(
            filename=file.filename,
            url=file_url,
            message="File uploaded successfully"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_document(request: AnalysisRequest):
    filename = request.file_url.split("/")[-1] if request.file_url else "unknown"

    try:
        # 1. Extract Text & Layout
        ocr_result = await extract_content_from_url(request.file_url)

        # 2. Analyze with LLM
        model_info = None
        if request.model_id:
            model_info = get_model_by_id(request.model_id)

        structured_data = await analyze_document_content(
            ocr_result=ocr_result,
            language=request.language,
            model_info=model_info
        )

        # 3. Save extraction log to Cosmos DB
        if request.model_id:
            save_extraction_log(
                model_id=request.model_id,
                filename=filename,
                file_url=request.file_url,
                status=ExtractionStatus.SUCCESS.value,
                extracted_data=structured_data
            )

        return AnalysisResponse(
            status=ExtractionStatus.SUCCESS.value,
            extracted_text=ocr_result.get("content", ""),
            structured_data=structured_data
        )
    except Exception as e:
        # Save error log
        if request.model_id:
            save_extraction_log(
                model_id=request.model_id,
                filename=filename,
                file_url=request.file_url,
                status=ExtractionStatus.ERROR.value,
                error=str(e)
            )

        logger.error(f"Analysis failed: {e}")
        return AnalysisResponse(
            status=ExtractionStatus.ERROR.value,
            extracted_text=str(e)
        )


@router.get("/logs")
async def get_extraction_logs(
    model_id: Optional[str] = Query(None, description="Filter by model ID"),
    limit: int = Query(50, ge=1, le=100)
):
    """Get extraction logs, optionally filtered by model"""
    if model_id:
        logs = get_logs_by_model(model_id, limit)
    else:
        logs = get_all_logs(limit)

    return {"logs": [log.model_dump() for log in logs]}
