from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, UploadFile, File, Form
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from app.services import doc_intel, extraction_logs
from app.services.models import get_model_by_id
from app.services import extraction_jobs
from app.core.auth import get_current_user, is_admin, CurrentUser
from app.core.config import settings
from app.core.enums import ExtractionStatus
import json
import logging

import logging

"""
========================================================================
[DAOM Extraction Pipeline - Main Router (B2B Document Processing)]
========================================================================

이 파일(`extraction_preview.py` - 이전 파일명 호환성 유지)은 DAOM 시스템의
가장 핵심적인 문서 추출 및 처리 API 엔드포인트들을 담당합니다.

주요 역할 (Roles):
1. /start-extraction: 최초 파일 업로드 후 백그라운드 추출 Job 생성 및 실행
2. /retry (재추출): 이미 추출 완료된 문서에 대해 실패하거나 변경된 스키마로 다시 백그라운드 추출 실행
3. /status/{job_id}: 폴링용 API (프론트엔드가 Job의 진행 상태를 P100 -> SUCCESS 까지 확인)
4. /save-extraction: 추출이 끝나고 최종 검수를 통과한 데이터를 DB (Cosmos DB)에 저장

*주의: 추출 파이프라인(LLM 호출 등) 자체는 무겁기 때문에, BackgroundTasks를 이용해
동기식 워커(Threadpool) 로 넘겨서 메인 API 서버가 멈추지(Blocking) 않도록 설계되어 있습니다.
========================================================================
"""

logger = logging.getLogger(__name__)

router = APIRouter()


class PreviewRequest(BaseModel):
    file_url: str


class PreviewWithGuideRequest(BaseModel):
    file_url: str
    model_id: str  # Model with guide fields


class RefineRequest(BaseModel):
    file_url: str
    selected_columns: List[str]  # Column names selected by user
    model_id: str
    language: str = "ko"


class MatchColumnsRequest(BaseModel):
    extracted_columns: List[str]  # Column names extracted by AI
    target_fields: List[Dict[str, str]]  # Model fields [{key, label}]


class SaveExtractionRequest(BaseModel):
    model_id: str
    filename: str
    file_url: str
    guide_extracted: Any  # Model field values (Dict for form, List for table)
    other_data: Optional[List[Dict[str, Any]]] = []  # Additional selected data (values can be any type)
    log_id: Optional[str] = None  # Optional: Update existing log
    debug_data: Optional[Dict[str, Any]] = None  # Raw debug data to persist


class StartExtractionRequest(BaseModel):
    """Request to start async extraction job"""
    model_id: str
    filename: str
    file_url: str


# Background task — delegates to extraction_orchestrator for clean separation
async def process_extraction_job(job_id: str, model_id: str, file_url: str, candidate_file_url: Optional[str] = None, candidate_file_urls: Optional[List[str]] = None, candidate_filenames: Optional[List[str]] = None, barcode: Optional[str] = None):
    """Background task to run full extraction or comparison pipeline.
    Business logic lives in app.services.extraction_orchestrator."""
    from app.services.extraction_orchestrator import run_pipeline_job
    await run_pipeline_job(
        job_id=job_id,
        model_id=model_id,
        file_url=file_url,
        candidate_file_url=candidate_file_url,
        candidate_file_urls=candidate_file_urls,
        candidate_filenames=candidate_filenames,
        barcode=barcode,
    )



@router.post("/start-job")
async def start_job_with_upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    candidate_files: List[UploadFile] = File(None),  # Multi-file support
    model_id: str = Form(...),
    barcode: Optional[str] = Form(None), # DEX target validation (optional)
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Upload file(s) and start extraction/comparison job.
    If candidate_files provided, it's a comparison job.
    """
    # Unified file type validation — Azure DI Layout supports all these formats
    allowed_exts = ('.pdf', '.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp', '.xlsx', '.xls', '.csv', '.docx')

    if not file.filename.lower().endswith(allowed_exts):
        raise HTTPException(status_code=400, detail=f"Invalid file type. Allowed: {', '.join(allowed_exts)}")

    # 1. Upload files
    from app.services.storage import upload_file_to_blob
    try:
        file_url = await upload_file_to_blob(file)

        candidate_file_urls = []
        candidate_filenames = []  # NEW: Store original filenames
        candidate_file_url = None # Legacy support

        if candidate_files:
            for c_file in candidate_files:
                url = await upload_file_to_blob(c_file)
                candidate_file_urls.append(url)
                candidate_filenames.append(c_file.filename)  # NEW: Store original filename

            # Set legacy single URL to the first one for backward compatibility
            if candidate_file_urls:
                candidate_file_url = candidate_file_urls[0]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")

    # 2. Create Log (Initial Pending State)
    user_id = current_user.id if current_user else "unknown"

    # Logs might need schema update too, but for now specific log fields are flexible or we use extracted_data
    # We won't break log schema yet, just store primary candidate in legacy field if needed
    log = await extraction_logs.save_extraction_log(
        model_id=model_id,
        user_id=user_id,
        user_name=current_user.name if current_user else None,
        user_email=current_user.email if current_user else None,
        filename=file.filename,
        file_url=file_url,
        candidate_file_url=candidate_file_url,
        candidate_file_urls=candidate_file_urls,  # NEW: Multi candidate files
        status="P100",  # Pending
        tenant_id=current_user.tenant_id if current_user else None
    )
    log_id = log.id if log else None

    # 3. Create Job linked to Log
    job = await extraction_jobs.create_job(
        model_id=model_id,
        user_id=user_id,
        filename=file.filename,
        file_url=file_url,
        candidate_file_url=candidate_file_url,
        candidate_file_urls=candidate_file_urls, # NEW
        user_name=current_user.name if current_user else None,
        user_email=current_user.email if current_user else None,
        original_log_id=log_id,  # Link to the log
        tenant_id=current_user.tenant_id if current_user else None
    )

    # 4. Start Background Process
    background_tasks.add_task(
        process_extraction_job,
        job.id,
        model_id,
        file_url,
        candidate_file_url,
        candidate_file_urls,
        candidate_filenames,
        barcode # DEX validation
    )

    return {
        "job_id": job.id,
        "log_id": log_id,
        "file_url": file_url,
        "candidate_file_urls": candidate_file_urls,
        "status": job.status
    }

@router.post("/start-batch-jobs")
async def start_batch_jobs(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    model_id: str = Form(...),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Upload multiple files and start independent extraction jobs for each (Phase 1 Batch Mode).
    """
    allowed_exts = ('.pdf', '.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp', '.xlsx', '.xls', '.csv', '.docx')
    user_id = current_user.id if current_user else "unknown"
    
    from app.services.storage import upload_file_to_blob
    results = []
    
    # Filter out empty/null files sent by Power Automate's IF logic
    valid_files = [f for f in files if f is not None and getattr(f, "filename", None) and getattr(f, "size", 1) > 0]
    
    if not valid_files:
        raise HTTPException(status_code=400, detail="No valid files received. If using Power Automate, check your file array logic for null/empty items.")
        
    if len(valid_files) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 files allowed per batch request to prevent timeouts. Please upload in smaller chunks.")
    
    for file in valid_files:
        if not file.filename.lower().endswith(allowed_exts):
            results.append({"filename": file.filename, "error": f"Invalid extension"})
            continue
            
        try:
            file_url = await upload_file_to_blob(file)
            
            # Create Log
            log = await extraction_logs.save_extraction_log(
                model_id=model_id,
                user_id=user_id,
                user_name=current_user.name if current_user else None,
                user_email=current_user.email if current_user else None,
                filename=file.filename,
                file_url=file_url,
                status="P100",  # Pending
                tenant_id=current_user.tenant_id if current_user else None
            )
            log_id = log.id if log else None
            
            # Create Job
            job = await extraction_jobs.create_job(
                model_id=model_id,
                user_id=user_id,
                filename=file.filename,
                file_url=file_url,
                user_name=current_user.name if current_user else None,
                user_email=current_user.email if current_user else None,
                original_log_id=log_id,
                tenant_id=current_user.tenant_id if current_user else None
            )
            
            # Start Background Task
            background_tasks.add_task(
                process_extraction_job,
                job.id,
                model_id,
                file_url,
                None,  # No single candidate
                None,  # No candidate_file_urls
                None   # No candidate_filenames
            )
            
            results.append({
                "filename": file.filename,
                "job_id": job.id,
                "log_id": log_id,
                "status": "started"
            })
            
        except Exception as e:
            logger.error(f"[Batch Upload] Failed for {file.filename}: {str(e)}")
            results.append({"filename": file.filename, "error": str(e)})

    return {"results": results}

@router.post("/dex-validate")
async def dex_validate(
    cropped_image: UploadFile = File(...),
    barcode_value: str = Form(...),
    model_id: str = Form(...),
    target_field: str = Form(...),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Hybrid Progressive UX DEX Validation Endpoint.
    1. Receives a small cropped Image & Barcode from the React Scanner.
    2. Calls Azure DI to extract 'queryFields' (Handwritten Name).
    3. Mocks an LIS database lookup using the barcode.
    4. Compares and returns Pass/Fail.
    """
    allowed_exts = ('.jpg', '.jpeg', '.png')
    if not cropped_image.filename.lower().endswith(allowed_exts):
        raise HTTPException(status_code=400, detail="Invalid cropped image format.")

    try:
        image_bytes = await cropped_image.read()

        # Step 1: Mock LIS Lookup based on Barcode ID
        # In a real scenario, this would be `requests.get('https://gclabs.lis/api/patient?barcode=...')`
        async def mock_lis_lookup(barcode: str) -> str:
            # Deterministic mock based on the last digit of the barcode
            last_char = barcode[-1] if barcode else "0"
            mock_db = {
                "0": "김철수", "1": "홍길동", "2": "이영희", "3": "박지성", "4": "김연아",
                "5": "유재석", "6": "강호동", "7": "신동엽", "8": "이수근", "9": "전현무"
            }
            return mock_db.get(last_char, "알수없음")

        lis_name = mock_lis_lookup(barcode_value)

        # Clean up target_field to meet Azure DI queryFields regex ^[\\p{L}\\p{M}\\p{N}_]{1,64}$
        import re
        sanitized_query_field = re.sub(r'[^\w\s]', '', target_field) # Keep words, strip punctuation
        sanitized_query_field = re.sub(r'\s+', '_', sanitized_query_field) # Replace spaces with _
        sanitized_query_field = sanitized_query_field[:64] # Limit length

        # Step 2: Extract Handwritten text using Azure DI (query_fields)
        from app.services.doc_intel import extract_with_strategy
        # Using prebuilt-layout, requesting specific query fields
        di_result = await extract_with_strategy(
            file_source=image_bytes,
            model_type="prebuilt-layout",
            filename=cropped_image.filename,
            mime_type=cropped_image.content_type,
            features=["queryFields"],
            query_fields=[sanitized_query_field] # Targeting the dynamic handwritten name
        )

        handwritten_name = "인식 실패"
        
        # Step 3: Parse Azure DI Output for the query field
        # In Azure DI, query fields appear in `result.documents[0].fields`
        documents = di_result.get("documents", [])
        if documents and len(documents) > 0:
            fields = documents[0].get("fields", {})
            # Look for the exact query field name
            if sanitized_query_field in fields:
                field_data = fields[sanitized_query_field]
                # Azure DI SDK usually populates `value_string` or `content`
                handwritten_name = field_data.get("value_string") or field_data.get("content") or "인식 실패"
        
        # Clean up strings (remove spaces, standardize)
        import re
        clean_lis = re.sub(r'\s+', '', lis_name).strip()
        clean_handwritten = re.sub(r'\s+', '', handwritten_name).strip()

        # Step 4: String Matching Logic
        is_match = (clean_lis == clean_handwritten)

        # Allow basic Levenshtein distance fallback (e.g., 홍길동 vs 홍길둥)
        if not is_match and len(clean_lis) > 2 and len(clean_handwritten) > 2:
            import Levenshtein
            distance = Levenshtein.distance(clean_lis, clean_handwritten)
            if distance <= 1: # Tolerate 1 typo
                is_match = True

        return {
            "barcode": barcode_value,
            "lis_name": lis_name,
            "handwritten_name": handwritten_name,
            "is_match": is_match
        }

    except Exception as e:
        logger.error(f"[DEX Validate] Failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/start-extraction")
async def start_extraction(
    request: StartExtractionRequest,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Start async extraction job. Returns job_id immediately.
    Client should poll /job/{job_id} for status.
    """
    user_id = current_user.id if current_user else "unknown"

    # 1. Create Log first (status=P100 pending)
    log = await extraction_logs.save_extraction_log(
        model_id=request.model_id,
        user_id=user_id,
        user_name=current_user.name if current_user else None,
        user_email=current_user.email if current_user else None,
        filename=request.filename,
        file_url=request.file_url,
        status="P100",  # Pending
        tenant_id=current_user.tenant_id if current_user else None
    )
    log_id = log.id if log else None

    # 2. Create Job with reference to Log
    job = await extraction_jobs.create_job(
        model_id=request.model_id,
        user_id=user_id,
        filename=request.filename,
        file_url=request.file_url,
        user_name=current_user.name if current_user else None,
        user_email=current_user.email if current_user else None,
        original_log_id=log_id,
        tenant_id=current_user.tenant_id if current_user else None
    )

    # 3. Run extraction in background directly
    background_tasks.add_task(
        process_extraction_job,
        job.id,
        request.model_id,
        request.file_url,
        None, # candidate_file_url
        None, # candidate_file_urls
        None, # candidate_filenames
        None  # barcode
    )

    return {
        "job_id": job.id,
        "log_id": log_id,
        "status": job.status
    }


@router.get("/log/{log_id}")
async def get_log_by_id(
    log_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Get a single extraction log by ID (for deep-linking) — hydrates from Blob"""
    log = await extraction_logs.get_log(log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Extraction log not found")

    # Centralized hydration — never miss a field again
    from app.services.hydration import hydrate_preview_data, hydrate_debug_data
    preview_data = await hydrate_preview_data(log.preview_data)
    debug_data = await hydrate_debug_data(log.debug_data)

    return {
        "id": log.id,
        "model_id": log.model_id,
        "filename": log.filename,
        "file_url": log.file_url,
        "status": log.status,
        "extracted_data": log.extracted_data,
        "preview_data": preview_data,
        "debug_data": debug_data,
        "candidate_file_url": log.candidate_file_url,
        "candidate_file_urls": log.candidate_file_urls,
        "created_at": log.created_at,
        "updated_at": log.updated_at,
        "user_name": log.user_name,
        "user_email": log.user_email,
    }






@router.post("/confirm-job/{job_id}")
async def confirm_job(
    job_id: str,
    request: Dict[str, Any],
    current_user: CurrentUser = Depends(get_current_user)
):
    """Confirm and save extraction job.
    Business logic delegated to extraction_orchestrator."""
    from app.services.extraction_orchestrator import confirm_and_save_job

    edited_data = request.get("edited_data") if request else None
    user_id = current_user.id if current_user else "unknown"

    try:
        result = await confirm_and_save_job(
            job_id=job_id,
            edited_data=edited_data,
            user_id=user_id,
            user_name=(current_user.name if current_user else "Unknown"),
            user_email=(current_user.email if current_user else None),
            tenant_id=(current_user.tenant_id if current_user else None),
        )
        return result
    except ValueError as e:
        status = 404 if "not found" in str(e).lower() else 400
        raise HTTPException(status_code=status, detail=str(e))
    except Exception as e:
        logger.error(f"[ConfirmJob] Failed: {e}")
        raise HTTPException(status_code=500, detail=f"Save failed: {str(e)}")




@router.post("/save-extraction")
async def save_extraction(
    request: SaveExtractionRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Save the guide-based extraction result to database.
    """
    try:
        # Combine guide_extracted and any selected other_data
        raw_guide = request.guide_extracted
        extracted_data = list(raw_guide) if isinstance(raw_guide, list) else dict(raw_guide)

        # Add selected other_data as additional fields
        if request.other_data:
            for item in request.other_data:
                if 'column' in item and 'value' in item:
                    extracted_data[item['column']] = item['value']

        # Get user ID
        user_id = current_user.id if current_user else 'unknown'

        # Save to extraction logs
        log = await extraction_logs.save_extraction_log(
            model_id=request.model_id,
            user_id=user_id,
            user_name=current_user.name if current_user else "Unknown",
            user_email=current_user.email if current_user else None,
            filename=request.filename,
            file_url=request.file_url,
            status=ExtractionStatus.SUCCESS.value,
            extracted_data=extracted_data,
            log_id=request.log_id,
            tenant_id=current_user.tenant_id if current_user else None,
            debug_data=request.debug_data
        )

        return {
            "success": True,
            "log_id": log.id if log else None,
            "extracted_data": extracted_data
        }

    except Exception as e:
        import traceback
        traceback.print_exc()

        # Save error log
        try:
            user_id = current_user.id if current_user else 'unknown'
            await extraction_logs.save_extraction_log(
                model_id=request.model_id,
                user_id=user_id,
                user_name=current_user.name if current_user else "Unknown",
                filename=request.filename,
                file_url=request.file_url,
                status=ExtractionStatus.ERROR.value,
                error=str(e)
            )
        except Exception as log_err:
            logger.warning(f"[SaveExtraction] Failed to save error log: {log_err}")
            pass

        raise HTTPException(status_code=500, detail=f"Save failed: {str(e)}")


@router.post("/match-columns")
async def match_columns_with_ai(request: MatchColumnsRequest):
    """
    Use OpenAI to semantically match extracted column names with model fields.
    Returns list of column names that should be pre-selected.
    """
    try:
        from openai import AsyncAzureOpenAI
        from app.core.config import settings

        client = AsyncAzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT
        )

        model_field_descriptions = [
            f"- {f.get('key', '')}: {f.get('label', '')}"
            for f in request.target_fields
        ]

        prompt = f"""You are a data field matching expert.

Given these extracted column names from a document:
{json.dumps(request.extracted_columns, ensure_ascii=False)}

And these target model fields (key: label):
{chr(10).join(model_field_descriptions)}

Match the extracted columns to the model fields semantically. Consider:
- Exact matches (e.g., "인보이스 번호" matches "invoice_number: 인보이스 번호")
- Semantic similarity (e.g., "Invoice Number" matches "invoice_number: 인보이스 번호")
- Abbreviations or variations (e.g., "발행일자" matches "issue_date: 발행일")

Return ONLY a JSON array of extracted column names that should be selected:
["column1", "column2", ...]

If no columns match, return an empty array: []
Return ONLY valid JSON, no markdown code blocks."""

        response = await client.chat.completions.create(
            model=settings.AZURE_OPENAI_DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": "You are a field matching expert. Return only valid JSON array."},
                {"role": "user", "content": prompt}
            ],
            temperature=settings.LLM_DEFAULT_TEMPERATURE
        )

        result = json.loads(response.choices[0].message.content)
        return {"matched_columns": result if isinstance(result, list) else []}

    except Exception as e:
        import traceback
        traceback.print_exc()
        # Return empty on error - don't fail the whole flow
        return {"matched_columns": []}


@router.post("/preview-with-guide")
async def get_preview_with_guide(
    request: PreviewWithGuideRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Extract data guided by model fields.
    Returns:
    - guide_extracted: Values extracted for each model field (key-value pairs)
    - other_data: Other extracted data for optional selection
    """
    # Extract filename from URL for logging
    filename = request.file_url.split('/')[-1] if request.file_url else 'unknown'
    user_id = current_user.id if current_user else 'unknown'

    try:
        from openai import AsyncAzureOpenAI
        from app.core.config import settings

        # Get model definition
        model = await get_model_by_id(request.model_id)
        if not model:
            # Log model not found error
            await extraction_logs.save_extraction_log(
                model_id=request.model_id,
                user_id=user_id,
                filename=filename,
                file_url=request.file_url,
                status='error',
                error='Model not found'
            )
            raise HTTPException(status_code=404, detail="Model not found")

        # Get raw Document Intelligence output using Dynamic Strategy
        azure_model = getattr(model, "azure_model_id", settings.OCR_DEFAULT_MODEL)
        doc_intel_output = await doc_intel.extract_with_strategy(request.file_url, azure_model)

        # Build field descriptions for AI
        field_descriptions = []
        for field in model.fields:
            desc = f"- {field.key}: {field.label}"
            if hasattr(field, 'description') and field.description:
                desc += f" ({field.description})"
            field_descriptions.append(desc)

        # Build global rules and reference data sections
        global_rules_section = ""
        if hasattr(model, 'global_rules') and model.global_rules:
            global_rules_section = f"\n\nGlobal Rules (apply to ALL fields):\n{model.global_rules}"

        ref_data_section = ""
        if hasattr(model, 'reference_data') and model.reference_data:
            ref_json = json.dumps(model.reference_data, ensure_ascii=False, indent=2)
            ref_data_section = f"\n\nReference Data:\n{ref_json}"

        # AI prompt to extract values for each model field with confidence and positions
        extraction_prompt = f"""You are a document data extractor.

Given this document data extracted by Document Intelligence:
{json.dumps(doc_intel_output, ensure_ascii=False, indent=2)}

Extract values for these specific fields:
{chr(10).join(field_descriptions)}
{global_rules_section}
{ref_data_section}

Return a JSON object with TWO parts:
1. "guide_extracted": Object with each field key containing:
   - "value": The extracted value (string or null if not found)
   - "confidence": Your confidence level from 0.0 to 1.0 (e.g., 0.95 for high confidence)
   - "bbox": Bounding box if available from Document Intelligence [x1, y1, x2, y2] as percentages, or null

2. "other_data": Array of other data found that wasn't matched to fields, each with:
   - "column": The field/column name
   - "value": The value (can be string, array, or object)
   - "confidence": Confidence level 0.0 to 1.0
   - "bbox": Bounding box if available, or null

Example format:
{{
  "guide_extracted": {{
    "invoice_number": {{"value": "INV-2024-001", "confidence": 0.98, "bbox": [10, 5, 30, 8]}},
    "issue_date": {{"value": "2024-01-15", "confidence": 0.92, "bbox": [50, 5, 70, 8]}},
    "amount": {{"value": "324.66", "confidence": 0.85, "bbox": [60, 40, 80, 43]}}
  }},
  "other_data": [
    {{"column": "VAT", "value": "32.47", "confidence": 0.90, "bbox": [60, 45, 80, 48]}},
    {{"column": "Line Items", "value": [{{"description": "Item 1", "qty": 2, "price": 100}}], "confidence": 0.88, "bbox": null}}
  ]
}}

IMPORTANT:
- For guide_extracted, use the exact field keys provided
- If a field value cannot be found, set value to null and confidence to 0
- Confidence should reflect how certain you are the extraction is correct
- bbox coordinates are percentages (0-100) of page dimensions [left, top, right, bottom]
- If Document Intelligence provides bounding box, include it; otherwise null
- Return ONLY valid JSON, no markdown code blocks."""

        client = AsyncAzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT
        )

        response = await client.chat.completions.create(
            model=settings.AZURE_OPENAI_DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": "You are a precise document data extractor. Return only valid JSON."},
                {"role": "user", "content": extraction_prompt}
            ],
            temperature=settings.LLM_DEFAULT_TEMPERATURE
        )

        result = json.loads(response.choices[0].message.content)

        # Ensure proper structure
        return {
            "guide_extracted": result.get("guide_extracted", {}),
            "other_data": result.get("other_data", []),
            "model_fields": [{"key": f.key, "label": f.label} for f in model.fields]
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()

        # Save error log for any failure
        try:
            await extraction_logs.save_extraction_log(
                model_id=request.model_id,
                user_id=user_id,
                filename=filename,
                file_url=request.file_url,
                status='error',
                error=str(e)
            )
        except Exception as log_err:
            logger.warning(f"[PreviewWithGuide] Failed to save error log: {log_err}")
            pass  # Don't fail if logging fails

        raise HTTPException(status_code=500, detail=f"Guide extraction failed: {str(e)}")


@router.post("/preview")
async def get_extraction_preview(request: PreviewRequest):
    """
    Step 1: Get Document Intelligence output using generic layout model, then ask AI to structure it into a table
    Returns AI-structured data with clear columns and sample rows
    """
    try:
        # Get raw Document Intelligence output using Dynamic Strategy
        # Use analyze_document_layout for backward compatibility with layout model
        # Or specifically use extract_with_strategy if model ID is available
        # Here we follow existing logic: Layout model for "full preview" unless specified otherwise
        doc_intel_output = await doc_intel.analyze_document_layout(request.file_url)

        # Ask AI to structure this into a meaningful table
        structuring_prompt = f"""
You are a data structuring expert. Given the following Document Intelligence extraction results (tables and key-value pairs), 
create a unified, structured table format.

Document Intelligence Output:
{json.dumps(doc_intel_output, ensure_ascii=False, indent=2)}

Your task:
1. Identify meaningful column headers (e.g., "상호명", "공급가액", "날짜" etc.)
2. Structure the data into rows with those columns
3. Return ONLY a JSON object with this structure:
{{
  "columns": [
    {{
      "name": "column_name",
      "sample_values": ["value1", "value2", "value3"]
    }}
  ],
  "total_rows": number
}}

Make column names clear and descriptive in Korean. Include up to 5 sample values per column.
Return ONLY valid JSON, no markdown code blocks.
"""

        # Call LLM to structure the data
        from openai import AsyncAzureOpenAI
        from app.core.config import settings

        client = AsyncAzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT
        )

        response = await client.chat.completions.create(
            model=settings.AZURE_OPENAI_DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": "You are a data structuring expert. Return only valid JSON."},
                {"role": "user", "content": structuring_prompt}
            ],
            temperature=settings.LLM_DEFAULT_TEMPERATURE
        )

        structured_result = json.loads(response.choices[0].message.content)

        return {
            "raw_data": doc_intel_output,  # Keep for debugging
            "structured_table": structured_result
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Preview failed: {str(e)}")


@router.post("/refine")
async def refine_extraction(
    request: RefineRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Step 2: Given user-selected columns, extract those specific fields from the document
    """
    try:
        # 1. Get Model to determine strategy
        model = await get_model_by_id(request.model_id)
        # Default to layout if model not found or no strategy
        azure_model = getattr(model, "azure_model_id", settings.OCR_DEFAULT_MODEL) if model else settings.OCR_DEFAULT_MODEL

        # Get Document Intelligence output using correct strategy
        doc_intel_output = await doc_intel.extract_with_strategy(request.file_url, azure_model)

        # Extract only selected columns
        extraction_prompt = f"""
Given this Document Intelligence data:
{json.dumps(doc_intel_output, ensure_ascii=False, indent=2)}

Extract the following columns ONLY:
{', '.join(request.selected_columns)}

Return a JSON object where keys are the column names and values are the extracted data.
Example: {{"상호명": "회사이름", "공급가액": "1000000"}}

Return ONLY valid JSON, no markdown.
"""

        from openai import AsyncAzureOpenAI
        from app.core.config import settings

        client = AsyncAzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT
        )

        response = await client.chat.completions.create(
            model=settings.AZURE_OPENAI_DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": "You are a data extraction expert. Return only valid JSON."},
                {"role": "user", "content": extraction_prompt}
            ],
            temperature=settings.LLM_DEFAULT_TEMPERATURE
        )

        extracted_data = json.loads(response.choices[0].message.content)

        # Save extraction log
        user_id = current_user.id if current_user else 'unknown'

        await extraction_logs.save_extraction_log(
            model_id=request.model_id,
            user_id=user_id,
            user_name=current_user.name if current_user else "Unknown",
            user_email=current_user.email if current_user else None,
            filename=request.file_url.split('/')[-1],  # Extract filename from URL
            status=ExtractionStatus.SUCCESS.value,
            file_url=request.file_url,
            extracted_data=extracted_data,
            tenant_id=current_user.tenant_id if current_user else None
        )

        return {
            "structured_data": extracted_data,
            "selected_columns": request.selected_columns
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()

        # Save error log
        try:
            user_id = current_user.id if current_user else 'unknown'

            await extraction_logs.save_extraction_log(
                model_id=request.model_id,
                user_id=user_id,
                user_name=current_user.name if current_user else "Unknown",
                filename=request.file_url.split('/')[-1],
                status=ExtractionStatus.ERROR.value,
                file_url=request.file_url,
                error=str(e)
            )
        except Exception as log_err:
            logger.warning(f"[Refine] Failed to save error log: {log_err}")
            pass  # Don't fail if logging fails

        raise HTTPException(status_code=500, detail=f"Refinement failed: {str(e)}")


@router.get("/logs")
async def get_extraction_logs_by_model(
    model_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    limit: int = 500
):
    """
    Get extraction logs for a specific model
    """
    if await is_admin(current_user):
        logs = await extraction_logs.get_logs_by_model(model_id=model_id, limit=limit)
    else:
        # Non-admin: only their own logs for this model
        logs = await extraction_logs.get_logs_by_user(user_id=current_user.id, limit=limit)
        logs = [log for log in logs if log.model_id == model_id]
    return [log.model_dump() for log in logs]


@router.get("/logs/all")
async def get_all_extraction_logs(
    current_user: CurrentUser = Depends(get_current_user),
    limit: int = 500,
    model_id: Optional[str] = None
):
    """
    Get all extraction logs (admin) or user's logs (regular user)
    Optional filter by model_id
    """
    user_oid = current_user.id

    # Admin can see all logs, regular users see only their logs
    if await is_admin(current_user):
        logs = await extraction_logs.get_all_logs(limit=limit)
    else:
        logs = await extraction_logs.get_logs_by_user(user_id=user_oid, limit=limit)

    # Filter by model_id if provided
    if model_id:
        logs = [log for log in logs if log.model_id == model_id]

    return [log.model_dump() for log in logs]


@router.delete("/logs/bulk-delete")
async def bulk_delete_logs(
    log_ids: List[str],
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Bulk delete extraction logs.
    Admins can delete any logs, regular users can only delete their own.
    """
    if not log_ids:
        raise HTTPException(status_code=400, detail="No log IDs provided")

    # Verify permissions for each log
    if not await is_admin(current_user):
        # Non-admin: verify they own all logs
        for log_id in log_ids:
            log = await extraction_logs.get_log(log_id)
            if not log or log.user_id != current_user.id:
                raise HTTPException(
                    status_code=403,
                    detail=f"You don't have permission to delete log {log_id}"
                )

    deleted_count = await extraction_logs.delete_logs(log_ids)

    return {
        "success": True,
        "deleted_count": deleted_count,
        "requested_count": len(log_ids)
    }
