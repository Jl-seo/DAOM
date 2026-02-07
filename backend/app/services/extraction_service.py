"""
Extraction Service
Core business logic for document extraction, validation, and processing.
Separates AI (flexible) from Code (strict) logic.
"""
import json
import logging
from typing import Dict, Any, List, Optional
from openai import AsyncAzureOpenAI
from app.core.config import settings
from app.services.llm import get_current_model
from app.core.enums import ExtractionStatus
from app.services import doc_intel, models, extraction_jobs, extraction_logs
from app.services.extraction_utils import parse_number, parse_date, normalize_bbox
from app.schemas.model import ExtractionModel, FieldDefinition

logger = logging.getLogger(__name__)

class ExtractionService:
    def __init__(self):
        self.azure_openai = AsyncAzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT
        )

    async def run_extraction_pipeline(self, job_id: str, model_id: str, file_url: str, candidate_file_url: Optional[str] = None, candidate_file_urls: Optional[List[str]] = None, candidate_filenames: Optional[List[str]] = None):
        """
        Orchestrates the full extraction pipeline with Multi-Document Support:
        1. OCR (Doc Intelligence)
        2. Splitting (Azure or GPT)
        3. Extraction per Split
        4. Aggregation
        
        Also handles COMPARISON jobs if candidate_file_url/urls are present.
        """
        # Capture current LLM model for logging
        current_llm_model = get_current_model()
        
        try:
            with open("debug_pipeline.log", "a") as f:
                f.write(f"\n=== JOB {job_id} STARTED (Model: {current_llm_model}) ===\n")

            # Update status
            extraction_jobs.update_job(job_id, status=ExtractionStatus.ANALYZING.value)
            
            # ... (omitted similar lines for brevity, focusing on log save)
            
            # 1. Get Model & OCR
            # UNIVERSAL MODE CHECK
            if model_id == "system-universal":
                model = ExtractionModel(
                    id="system-universal",
                    name="Universal",
                    description="Auto-detected extraction",
                    fields=[], # No predefined fields
                    tenant_id="generic",
                    created_at="now",
                    data_structure="key-value"
                )
                azure_model = "prebuilt-layout" # Default for universal
            else:
                try:
                    model = models.get_model_by_id(model_id)
                except Exception:
                    model = None
                
                if not model:
                    # Fallback for transient model errors or if model_id is just a string in some contexts
                    # But usually it should exist. If comparison, maybe strict model check isn't needed?
                    # For now keep strict check unless it's a comparison job without strict model reqs
                    # But comparison usually uses a generic "Comparison" model or similar.
                    pass 

                # Dynamic Strategy
                azure_model = getattr(model, "azure_model_id", "prebuilt-layout") if model else "prebuilt-layout"

            # --- COMPARISON MODE CHECK ---
            # Compile all candidate URLs
            all_candidates = []
            if candidate_file_urls:
                all_candidates.extend(candidate_file_urls)
            if candidate_file_url and candidate_file_url not in all_candidates:
                all_candidates.insert(0, candidate_file_url) # Legacy takes precedence or is added

            if all_candidates:
                logger.info(f"[Pipeline] Starting 1:N Comparison for Job {job_id} on {len(all_candidates)} candidates")
                from app.services import llm
                import asyncio
                
                # Prepare custom rules if model exists
                custom_rules = model.global_rules if model and model.global_rules else None
                if custom_rules:
                    logger.info(f"[Pipeline] Applying custom comparison rules: {custom_rules[:50]}...")

                # Define comparison task for a single candidate
                async def compare_single(idx: int, c_url: str, c_filename: Optional[str] = None) -> dict:
                    logger.info(f"[Pipeline] Comparing Candidate {idx+1}/{len(all_candidates)}: {c_filename or 'unnamed'}")
                    try:
                        # Extract comparison settings safely
                        comp_settings = model.comparison_settings.dict() if model and model.comparison_settings else None
                        
                        res = await llm.compare_images(
                            file_url, 
                            c_url, 
                            custom_instructions=custom_rules,
                            comparison_settings=comp_settings # PASS SETTINGS HERE
                        )
                        # Use provided filename directly (from upload time)
                        # Fallback to URL parsing if not provided
                        filename = c_filename
                        if not filename:
                            try:
                                from urllib.parse import urlparse, unquote
                                parsed = urlparse(c_url)
                                path_part = parsed.path.split('/')[-1]
                                decoded = unquote(path_part)
                                import re
                                uuid_prefix_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_(.+)$'
                                match = re.match(uuid_prefix_pattern, decoded, re.I)
                                if match:
                                    filename = match.group(1)
                                elif not re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}', decoded, re.I):
                                    filename = decoded
                            except Exception as url_parse_err:
                                logger.debug(f"[Pipeline] URL parse fallback for filename: {url_parse_err}")
                        return {
                            "candidate_index": idx,
                            "file_url": c_url,
                            "filename": filename,  # Original filename from upload
                            "result": res
                        }
                    except Exception as comp_error:
                        logger.error(f"[Pipeline] Comparison failed for candidate {c_url}: {comp_error}")
                        return {
                            "candidate_index": idx,
                            "file_url": c_url,
                            "filename": c_filename,  # Still return provided filename
                            "error": str(comp_error),
                            "result": {}
                        }
                
                # Build filename lookup (safely handle None or mismatched lengths)
                all_filenames = candidate_filenames or []
                
                # Run all comparisons in PARALLEL using asyncio.gather
                comparison_tasks = [
                    compare_single(idx, c_url, all_filenames[idx] if idx < len(all_filenames) else None) 
                    for idx, c_url in enumerate(all_candidates)
                ]
                comparison_results = await asyncio.gather(*comparison_tasks)
                comparison_results = list(comparison_results)  # Convert tuple to list

                # Save results
                # We store differences in 'preview_data'
                # For backward compatibility, if there's only 1 candidate, we might want to structure it simply
                # BUT new frontend expects 'comparisons' list.
                
                preview_payload = {
                    "comparisons": comparison_results,
                    "mode": "comparison",
                    "comparison_count": len(all_candidates)
                }
                
                # If single result, populate legacy field 'comparison_result' for older frontends if needed
                if len(comparison_results) == 1:
                    preview_payload["comparison_result"] = comparison_results[0]["result"]

                result = extraction_jobs.update_job(
                    job_id, 
                    status=ExtractionStatus.SUCCESS.value, 
                    preview_data=preview_payload,
                    extracted_data={"comparisons": comparison_results} # Use extracted_data for final persistence?
                )
                
                if not result:
                    logger.error(f"Failed to update job {job_id} with comparison results.")
                    return

                # Sync status to ExtractionLog if linked
                job = extraction_jobs.get_job(job_id)
                if job and (job.original_log_id or job.log_id):
                    log_id_to_update = job.original_log_id or job.log_id
                    extraction_logs.update_log_status(
                        log_id_to_update, 
                        status=ExtractionStatus.SUCCESS.value,
                        preview_data=preview_payload
                    )
                
                return # Exit pipeline for comparison jobs
            # -----------------------------

            # --- EXCEL ROUTING (Beta: use_virtual_excel_ocr) ---
            # Excel/CSV files cannot be processed by Azure Doc Intelligence.
            # When the beta feature is enabled, route to ExcelMapper instead.
            file_ext = file_url.rsplit(".", 1)[-1].lower().split("?")[0]  # strip query params
            is_excel_file = file_ext in ("xlsx", "xls", "csv")
            use_excel_ocr = (
                model 
                and hasattr(model, "beta_features") 
                and model.beta_features.get("use_virtual_excel_ocr", False)
            )
            
            if is_excel_file and use_excel_ocr:
                logger.info(f"[Pipeline] Excel file detected ({file_ext}), using ExcelMapper (virtual OCR)")
                from app.services.excel_mapper import ExcelMapper
                doc_intel_output = await ExcelMapper.from_url(file_url)
            else:
                logger.info(f"[Pipeline-Debug] Calling doc_intel with {azure_model}")
                doc_intel_output = await doc_intel.extract_with_strategy(file_url, azure_model)
            
            # ... (OCR log) ...
            
            # --- DEBUG DATA PERSISTENCE (PARALLEL) ---
            # OPTIMIZATION: Run Blob Upload in parallel with LLM extraction.
            # Await it at the end to ensure data integrity without race conditions.
            import asyncio
            async def _upload_debug_data():
                try:
                    blob_path = doc_intel_output.get("_cache_blob_path")
                    if not blob_path:
                        from app.services import storage
                        blob_path = f"ocr_cache/{azure_model}/{job_id}.ocr.json"
                        await storage.save_json_as_blob(doc_intel_output, blob_path)
                        logger.info(f"[DebugData] Explicitly saved raw ADI data to {blob_path}")
                    return blob_path
                except Exception as e:
                    logger.error(f"Failed to persist debug data: {e}")
                    return None
            
            # Start task but don't await yet
            debug_upload_task = asyncio.create_task(_upload_debug_data())
            # ------------------------------
            # ------------------------------

            # 2. Splitting (Same as before)
            # 2. Splitting (Use new Splitting Service or simple page iteration)
            # For MVP, we treat the whole document as one split unless user hints otherwise
            splits = [{"index": 0, "type": "document", "page_ranges": [p["page_number"] for p in doc_intel_output.get("pages", [])]}]

            # 3. Process Each Split (Parallel with rate limit protection)
            import asyncio
            
            async def process_split(split):
                try:
                    if model.id == "system-universal":
                        return await self._process_single_split_universal(doc_intel_output, split)
                    else:
                        return await self._process_single_split(doc_intel_output, split, model)
                except Exception as e:
                    logger.error(f"Error processing split {split.get('index', 0)}: {e}")
                    return {
                        "index": split.get("index", 0),
                        "type": split.get("type", "unknown"),
                        "page_ranges": split.get("page_ranges", []),
                        "status": "error",
                        "error": str(e),
                        "data": {"guide_extracted": {}}
                    }
            
            # Process splits in parallel (max 3 concurrent to avoid rate limits)
            semaphore = asyncio.Semaphore(3)
            
            async def process_with_limit(split):
                async with semaphore:
                    return await process_split(split)
            
            sub_documents = await asyncio.gather(*[process_with_limit(s) for s in splits])
            sub_documents = list(sub_documents)  # Convert tuple to list
            
            # 4. Save Results
            logger.info(f"[Pipeline-Debug] All splits processed. Total sub_documents: {len(sub_documents)}")
            
            # --- DEBUG DATA MERGE (Parallel Await) ---
            debug_info_final = None
            if debug_upload_task:
                try:
                    blob_path = await debug_upload_task
                    if blob_path:
                        debug_info_final = {
                            "source": "blob_storage",
                            "raw_data_blob_path": blob_path, 
                            "doc_intel_summary": {
                                "page_count": len(doc_intel_output.get("pages", [])),
                                "model_id": doc_intel_output.get("model_id"),
                                "api_version": doc_intel_output.get("api_version")
                            },
                            # Provide FULL content for frontend visualization
                            "ocr_result": {
                                "content": doc_intel_output.get("content", ""),
                                "tables": doc_intel_output.get("tables", [])
                            },
                            # Legacy key for backward compatibility
                            "doc_intel_content_preview": doc_intel_output.get("content", "")[:1000]
                        }
                        logger.info(f"[Pipeline] Debug data merged successfully")
                except Exception as dbg_err:
                    logger.error(f"[Pipeline] Failed to await debug upload: {dbg_err}")
            # -----------------------------------------

            # Extract LLM debug info from sub_documents and merge into debug_data
            # CRITICAL: This entire block is wrapped in try/except because debug info
            # must NEVER crash the extraction pipeline. Any len()/key errors here are non-fatal.
            try:
                llm_debug_info = {}
                if sub_documents and len(sub_documents) > 0:
                    first_doc_data = sub_documents[0].get("data") or {}
                    if "_debug_chunking" in first_doc_data:
                        llm_debug_info["_debug_chunking"] = first_doc_data["_debug_chunking"]
                    if "_chunked" in first_doc_data:
                        llm_debug_info["_chunked"] = first_doc_data["_chunked"]
                    if "_chunking_errors" in first_doc_data:
                        llm_debug_info["_chunking_errors"] = first_doc_data["_chunking_errors"]
                    # Extract token usage (from both beta and legacy paths)
                    if first_doc_data.get("_token_usage"):
                        llm_debug_info["token_usage"] = first_doc_data["_token_usage"]
                    # Beta-specific debug info
                    beta_content = first_doc_data.get("_beta_parsed_content")
                    if beta_content:
                        llm_debug_info["beta_mode"] = True
                        llm_debug_info["beta_parsed_content_length"] = len(beta_content)
                    beta_ref = first_doc_data.get("_beta_ref_map")
                    if beta_ref:
                        llm_debug_info["beta_ref_map_count"] = len(beta_ref)
                    # Beta chunking info
                    chunking_info = first_doc_data.get("_beta_chunking_info")
                    if chunking_info:
                        llm_debug_info["beta_chunking"] = {
                            "total_chunks": chunking_info.get("total_chunks"),
                            "successful_chunks": chunking_info.get("successful_chunks"),
                            "field_sources": chunking_info.get("field_sources"),
                            "errors": chunking_info.get("errors"),
                        }
                    # Capture LLM error if present
                    if "error" in first_doc_data:
                        llm_debug_info["llm_error"] = first_doc_data["error"]
                    # Pipeline stage diagnostics (for step-by-step debugging)
                    if "_beta_pipeline_stages" in first_doc_data:
                        llm_debug_info["beta_pipeline_stages"] = first_doc_data["_beta_pipeline_stages"]
                
                # Merge OCR debug and LLM debug
                if debug_info_final:
                    debug_info_final.update(llm_debug_info)
                else:
                    debug_info_final = llm_debug_info if llm_debug_info else None
            except Exception as debug_err:
                import traceback
                logger.error(f"[Pipeline] Debug info assembly failed (non-fatal): {debug_err}\n{traceback.format_exc()}")
                # Don't let debug failure kill the pipeline

            preview_payload = {
                "sub_documents": sub_documents,
                "raw_content": doc_intel_output.get("content", ""),
                "raw_tables": doc_intel_output.get("tables", [])
            }
            
            # ============================================================
            # UNIFIED BLOB STORAGE: Always store large data in Blob 
            # Cosmos only holds blob_path references (same as ocr_cache pattern)
            # ============================================================
            from app.services import storage
            
            # 1. Save preview_data to Blob (always)
            preview_blob_path = f"preview_data/{job_id}.preview.json"
            try:
                await storage.save_json_as_blob(preview_payload, preview_blob_path)
                logger.info(f"[Pipeline] preview_data saved to blob: {preview_blob_path}")
            except Exception as blob_err:
                logger.error(f"[Pipeline] Failed to save preview_data to blob: {blob_err}")
                preview_blob_path = None
            
            # 2. Save debug_data to Blob (always, if exists)
            debug_blob_path = None
            if debug_info_final:
                debug_blob_path = f"debug_data/{job_id}.debug.json"
                try:
                    await storage.save_json_as_blob(debug_info_final, debug_blob_path)
                    logger.info(f"[Pipeline] debug_data saved to blob: {debug_blob_path}")
                except Exception as blob_err:
                    logger.error(f"[Pipeline] Failed to save debug_data to blob: {blob_err}")
                    debug_blob_path = None
            
            # 3. Cosmos gets lightweight references only
            # - sub_documents: needed for rendering extracted fields (stripped of debug data)
            # - raw_content: truncated for "OCR Text" tab quick preview
            # - blob paths: for hydration of raw_tables/raw_content/debug
            
            # Sub_documents: KEEP guide_extracted (core data), strip debug/internal/large keys
            # CRITICAL: TABLE MODE puts raw_tables in data — this contains full ExcelMapper
            # table cells with polygons/bounding_regions and is the root cause of 
            # RequestEntityTooLarge for Excel files
            _internal_keys = {
                "_debug_chunking", "_chunked", "_chunking_errors", "_token_usage",
                "_beta_parsed_content", "_beta_ref_map", "_beta_chunking_info",
                "_beta_pipeline_stages", "_raw_llm_response", "_prompt_used",
                "raw_tables",  # ExcelMapper table data — huge, already in blob
            }
            cosmos_sub_docs = []
            for sd in (sub_documents or []):
                light_sd = {
                    "index": sd.get("index"),
                    "type": sd.get("type"),
                    "page_ranges": sd.get("page_ranges"),
                    "status": sd.get("status"),
                }
                # Keep guide_extracted + other essential data, strip internal debug keys
                if isinstance(sd.get("data"), dict):
                    light_sd["data"] = {
                        k: v for k, v in sd["data"].items()
                        if k not in _internal_keys
                    }
                cosmos_sub_docs.append(light_sd)
            
            cosmos_preview = {
                "sub_documents": cosmos_sub_docs,
                "raw_content": doc_intel_output.get("content", "")[:5000],  # Truncated preview
                "raw_tables": [],  # Full data in blob only
                "_preview_blob_path": preview_blob_path,
            }
            
            cosmos_debug = {
                "_debug_blob_path": debug_blob_path,
                "token_usage": debug_info_final.get("token_usage") if debug_info_final else None,
            } if debug_info_final else None
            
            # Don't duplicate guide_extracted in extracted_data — it's already in sub_documents
            # This saves ~50% of Cosmos payload size
            
            import json as _diag_json
            _cosmos_size = len(_diag_json.dumps(cosmos_preview, ensure_ascii=False, default=str))
            logger.info(f"[Pipeline] Saving to Cosmos: preview={_cosmos_size}b, blob={preview_blob_path}")
            
            result = extraction_jobs.update_job(
                job_id, 
                status=ExtractionStatus.SUCCESS.value, 
                preview_data=cosmos_preview,
                extracted_data=None,  # Not duplicated — use sub_documents[0].data.guide_extracted
                debug_data=cosmos_debug
            )
            
            if not result:
                diag_reason = extraction_jobs.get_last_update_error() or "unknown"
                logger.error(f"[Pipeline] update_job returned None for job {job_id}: {diag_reason}")
                extraction_jobs.update_job(job_id, status=ExtractionStatus.ERROR.value, error=f"Failed to save extraction results [{diag_reason}]")
                return
            
            
            logger.info(f"[Pipeline-Debug] Job {job_id} completed successfully!")
            
            # Sync status to ExtractionLog if linked
            job = extraction_jobs.get_job(job_id)
            if job and (job.original_log_id or job.log_id):
                log_id_to_update = job.original_log_id or job.log_id
                # Also save preview_data to log so it can be viewed later
                extraction_logs.update_log_status(
                    log_id_to_update, 
                    status=ExtractionStatus.SUCCESS.value,
                    preview_data=cosmos_preview,  # Blob refs only, not raw data
                    extracted_data=flat_extracted, # Pass None is fine, update_log_status will derive if needed
                    debug_data=cosmos_debug
                )

        except Exception as e:
            logger.error(f"Pipeline error for job {job_id}: {e}")
            extraction_jobs.update_job(job_id, status=ExtractionStatus.ERROR.value, error=str(e))
            
            # Sync error status to ExtractionLog if linked
            try:
                job = extraction_jobs.get_job(job_id)
                if job and (job.original_log_id or job.log_id):
                    log_id_to_update = job.original_log_id or job.log_id
                    extraction_logs.update_log_status(
                        log_id_to_update, 
                        status=ExtractionStatus.ERROR.value
                    )
            except Exception as sync_error:
                logger.error(f"Failed to sync error status to log for job {job_id}: {sync_error}")

    async def _process_single_split_universal(self, full_ocr_data: Dict[str, Any], split: Dict[str, Any]) -> Dict[str, Any]:
        """Universal extraction without predefined schema"""
        # Unwrap LLM Extraction (Universal)
        raw_extraction = await self._unwrap_universal_extraction(full_ocr_data, focus_pages=split["page_ranges"])
        
        # In universal mode, we trust the LLM's structure mostly
        # But we still try to normalize bboxes if possible
        start_page = split["page_ranges"][0] if split["page_ranges"] else 1
        validated_data = self._validate_and_format_universal(raw_extraction, full_ocr_data.get("pages", []), default_page=start_page)
        
        return {
            "index": split["index"],
            "type": split["type"],
            "page_ranges": split["page_ranges"],
            "status": "success",
            "data": validated_data
        }

    def _filter_ocr_data(self, ocr_data: Dict[str, Any], page_numbers: List[int]) -> Dict[str, Any]:
        """
        Filter OCR data to include only specific pages to save tokens.
        Preserves 'content' only if it seems reasonably sized or just omits it in favor of structural elements.
        """
        if not page_numbers:
            return ocr_data
        
        # Robust check: ocr_data must be a dict
        if not isinstance(ocr_data, dict):
            logger.warning(f"[_filter_ocr_data] ocr_data is not a dict: {type(ocr_data)}")
            # Fallback: attempt to wrap if it looks like a list of pages
            if isinstance(ocr_data, list):
                 return {"pages": ocr_data} # Best effort fallback
            return {}

        # PRESERVE CONTENT: Essential for LLM context! 
        # If filtering pages, we can't easily filter content string without spans, 
        # but providing full content is safer than providing none.
        # We'll truncate if absolutely massive (e.g. > 100k chars), but 32k is handled by chunking.
        filtered_data = {
            "api_version": ocr_data.get("api_version"),
            "model_id": ocr_data.get("model_id"),
            "content": ocr_data.get("content", ""), # Restore content
            "pages": [],
            "tables": [],
            "paragraphs": [] # Optional, might be heavy
        }
        


        # 1. Filter Pages
        target_pages = set(page_numbers)
        
        pages = ocr_data.get("pages", [])
        if isinstance(pages, list):
            for p in pages:
                if isinstance(p, dict) and p.get("page_number", 0) in target_pages:
                    # PRESERVE WORDS: LLM needs word-level precision for accurate BBox extraction
                    # We rely on Pre-emptive Chunking to handle token limits if this gets too big.
                    filtered_data["pages"].append(p.copy())

        # 2. Filter Tables
        tables = ocr_data.get("tables", [])
        if isinstance(tables, list):
            for t in tables:
                if not isinstance(t, dict): continue
                
                # Check bounding regions for page number
                # If bounding_regions missing (e.g. old doc_intel), include table conservatively or check cells?
                # We'll rely on doc_intel update.
                matches = False
                regions = t.get("bounding_regions", [])
                if isinstance(regions, list):
                    for region in regions:
                        if isinstance(region, dict) and region.get("page_number") in target_pages:
                            matches = True
                            break
                if matches:
                    filtered_data["tables"].append(t)
                
        # 3. Filter Paragraphs (if present)
        paragraphs = ocr_data.get("paragraphs", [])
        if isinstance(paragraphs, list):
            for para in paragraphs:
                 if isinstance(para, dict):
                     regions = para.get("bounding_regions")
                     if isinstance(regions, list) and regions:
                         if isinstance(regions[0], dict) and regions[0].get("page_number") in target_pages:
                             filtered_data["paragraphs"].append(para)

        return filtered_data

    async def _unwrap_universal_extraction(self, full_ocr_data: Dict[str, Any], focus_pages: List[int] = None) -> Dict[str, Any]:
        """Ask LLM to discover ANY relevant fields"""
        
        # OPTIMIZATION: Filter payload to only relevant pages
        ocr_data_to_send = self._filter_ocr_data(full_ocr_data, focus_pages) if focus_pages else full_ocr_data.copy()
        

        
        focus_instruction = ""
        if focus_pages:
            logger.info(f"[LLM-Universal] Focusing on pages: {focus_pages}")
            focus_instruction = f"\nIMPORTANT: FOCUS ONLY ON DATA FROM PAGES {focus_pages}. IGNORE OTHER PAGES."

        prompt = f"""You are a universal document data extractor.

Given this document data extracted by Document Intelligence (Pages: {focus_pages}):
{json.dumps(ocr_data_to_send, ensure_ascii=False)}

INSTRUCTIONS:
1. Identify ALL significant key-value pairs, tables, and entities in the document.
2. Group related information (e.g., "Vendor Details", "Financials", "Line Items").
3. Determine the best label (key) and data type for each item.
4. **CRITICAL**: Extract values EXACTLY as they appear.
5. **CRITICAL**: Include 'bbox' [x1, y1, x2, y2] for every value.
6. **CRITICAL**: Include 'page_number' (1-based index) for every value.

Return a JSON object with:
1. "guide_extracted": Object where Keys are the labels you discovered, and Values are objects:
   - "value": The extracted value
   - "type": inferred type (string, number, date, currency, address)
   - "category": grouping name (optional)
   - "confidence": 0.0 to 1.0
   - "bbox": [x1, y1, x2, y2] (REQUIRED)
   - "page_number": 1-based index (REQUIRED)

2. "other_data": Any unstructured highlights.

IMPORTANT: 
- Be granular. Don't lump big chunks of text.
- Return ONLY valid JSON.{focus_instruction}"""
        
        # ... (Call LLM similar to _unwrap_llm_extraction)
        try:
            from app.services.llm import get_current_model
            current_model_name = get_current_model()
            
            response = await self.azure_openai.chat.completions.create(
                model=current_model_name,
                messages=[
                    {"role": "system", "content": "You are a universal document analyzer. Return valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0,
                response_format={"type": "json_object"}
            )
            raw_content = response.choices[0].message.content or ""
            logger.info(f"[LLM-Universal-Debug] Success! Length: {len(raw_content)}")
            logger.info(f"[LLM-Universal-Debug] Preview: {raw_content[:200]}")
            return json.loads(raw_content)
        except Exception as e:
            error_str = str(e).lower()
            
            # Check if token limit exceeded - fallback to chunked processing
            # Only switch to chunked if it's genuinely a context length issue. 
            # 429 Rate Limit should be handled by retry, not chunking.
            if "context_length" in error_str or "maximum context" in error_str:
                logger.warning(f"[LLM-Universal] Token limit exceeded, switching to chunked extraction...")
                
                try:
                    from app.services.chunked_extraction import extract_with_chunking
                    
                    # Universal mode: discover all fields
                    model_fields = [{"key": "_discover", "label": "Discover all fields", "description": "Extract all key-value pairs"}]
                    
                    merged_result, errors = await extract_with_chunking(
                        ocr_data_to_send,
                        model_fields,
                        max_tokens_per_chunk=8000, # Increased chunk size
                        max_concurrent=8 # Increased concurrency
                    )
                    
                    if errors:
                        logger.warning(f"[LLM-Universal-Chunked] Some chunks failed: {errors}")
                    
                    # Merge structured result
                    return {
                        "guide_extracted": {k: {"value": v.get("value"), "confidence": v.get("confidence", 0.0), "bbox": v.get("bbox"), "page_number": v.get("page_number")} for k, v in merged_result.items() if not k.startswith("_")},
                        "other_data": [],
                        "_chunked": True
                    }
                except Exception as chunk_error:
                    logger.error(f"[LLM-Universal-Chunked] Fallback also failed: {chunk_error}")
            
            logger.error(f"[LLM] Universal Extraction Error: {e}")
            return {"guide_extracted": {}, "error": str(e)}

    def _validate_and_format_universal(self, raw_data: Dict[str, Any], pages_info: List[Dict[str, Any]], default_page: int = 1) -> Dict[str, Any]:
        """Relaxed validation for universal mode"""
        guide_extracted = raw_data.get("guide_extracted", {})
        
        # Defensive: if LLM returns a list instead of dict, convert or skip
        if isinstance(guide_extracted, list):
            logger.warning(f"[Validation-Universal] guide_extracted is a list, converting to dict")
            guide_extracted = {f"item_{i}": item for i, item in enumerate(guide_extracted) if isinstance(item, dict)}
        elif not isinstance(guide_extracted, dict):
            logger.error(f"[Validation-Universal] guide_extracted is not a dict or list: {type(guide_extracted)}")
            guide_extracted = {}
        
        validated_extracted = {}
        
        page_dims = {p["page_number"]: (p["width"], p["height"]) for p in pages_info}

        for key, item in guide_extracted.items():
            if not isinstance(item, dict): continue
            
            value = item.get("value")
            bbox = item.get("bbox")
            try:
                page_number = int(item.get("page_number")) if item.get("page_number") else None
            except (ValueError, TypeError):
                page_number = None
            
            # --- SMART PAGE DISCOVERY (Universal Mode) ---
            detected_page = page_number
            if not detected_page:
                 detected_page = default_page

            snapped_bbox = None
            final_page_number = detected_page

            # Helper (inline for safely accessing self if needed, though self is available)
            def search_page_univ(p_num):
                p_data = next((p for p in pages_info if p["page_number"] == p_num), None)
                if p_data and "words" in p_data:
                    return self._snap_bbox_to_words(str(value), bbox, p_data["words"])
                return None

            # Attempt 1: Check intended page
            snapped_bbox = search_page_univ(final_page_number)

            # Attempt 2: Check other pages
            if not snapped_bbox and pages_info:
                  for p_info in pages_info:
                     p_num = p_info["page_number"]
                     if p_num == final_page_number: continue
                     
                     found_bbox = search_page_univ(p_num)
                     if found_bbox:
                         snapped_bbox = found_bbox
                         final_page_number = p_num
                         logger.info(f"[SmartDiscovery-Univ] Value '{value}' found on Page {p_num}")
                         break
            
            page_number = final_page_number
            # ---------------------------------------------

            # Normalize
            normalized_bbox = None
            if snapped_bbox:
                p_w, p_h = 100, 100
                if page_number and page_number in page_dims: p_w, p_h = page_dims[page_number]
                normalized_bbox = self._normalize_bbox(snapped_bbox, p_w, p_h)

            validated_extracted[key] = {
                "value": value,
                "type": item.get("type", "string"), # Conserve inferred type
                "category": item.get("category"),
                "confidence": item.get("confidence", 0),
                "bbox": normalized_bbox,
                "page_number": page_number,
                "validation_status": "inferred"
            }

        # Initialize result container
        result = {
            "guide_extracted": validated_extracted,
            "other_data": raw_data.get("other_data", []),
            "model_fields": [{"key": k, "label": k} for k in validated_extracted.keys()] # Dynamic fields
        }
        
        # Preserve Raw Content (Critical for UI)
        if "raw_content" in raw_data:
            result["raw_content"] = raw_data["raw_content"]
            
        # Preserve Beta Fields (LayoutParser) if present
        if "_beta_parsed_content" in raw_data:
            result["_beta_parsed_content"] = raw_data["_beta_parsed_content"]
        if "_beta_ref_map" in raw_data:
            result["_beta_ref_map"] = raw_data["_beta_ref_map"]
            
        return result


    async def _process_single_split(self, full_ocr_data: Dict[str, Any], split: Dict[str, Any], model: ExtractionModel) -> Dict[str, Any]:
        """
        Runs extraction on a specific sub-document split.
        """
        # Unwrap LLM Extraction with focus on specific pages
        raw_extraction = await self._unwrap_llm_extraction(full_ocr_data, model, focus_pages=split["page_ranges"])
        
        # Validation
        # Pass the first page of the split as default_page to handle missing page_number from LLM
        start_page = split["page_ranges"][0] if split["page_ranges"] else 1
        validated_data = self._validate_and_format(raw_extraction, model, full_ocr_data.get("pages", []), default_page=start_page)
        
        return {
            "index": split["index"],
            "type": split["type"],
            "page_ranges": split["page_ranges"],
            "data": validated_data
        }

    async def _unwrap_llm_extraction(self, ocr_data: Dict[str, Any], model: ExtractionModel, focus_pages: List[int] = None) -> Dict[str, Any]:
        """ask LLM to extract data based on model fields"""
        
        # OPTIMIZATION: Filter payload to only relevant pages
        ocr_data_to_send = self._filter_ocr_data(ocr_data, focus_pages) if focus_pages else ocr_data.copy()
        
        # BETA FEATURE: Delegate to centralized LLM service for LayoutParser support
        use_beta = False
        
        # Robust check for beta_features (handle Pydantic model, ORM object, or Dict)
        beta_features = None
        if hasattr(model, "beta_features"):
            beta_features = model.beta_features
        elif isinstance(model, dict) and "beta_features" in model:
            beta_features = model["beta_features"]
            
        if beta_features and isinstance(beta_features, dict):
            use_beta = beta_features.get("use_optimized_prompt", False)
            
            # OPTIMIZATION: Check if input source explicitly requested bypass
            # e.g. Excel/CSV files are already perfectly structured and don't need layout parsing
            if ocr_data.get("_layout_parser_bypass"):
                logger.info(f"[LLM-Beta-Check] _layout_parser_bypass flag detected. Skipping Beta despite model setting.")
                use_beta = False
                
            logger.info(f"[LLM-Beta-Check] Beta detected. features={beta_features}, use_beta={use_beta}")
        else:
            logger.info(f"[LLM-Beta-Check] No beta_features found or disabled. model_type={type(model)}, features={beta_features}")
        
        if use_beta:
            from app.services.beta_chunking import extract_beta_with_chunking
            logger.info("[LLM] Beta feature enabled. Delegating to beta_chunking...")
            llm_result = await extract_beta_with_chunking(
                ocr_data=ocr_data_to_send,
                model_info=model,
                language="ko",
            )
            
            # DIAGNOSTIC: Log result shape (wrapped in try/except — diagnostics must NEVER crash extraction)
            try:
                logger.info(f"[LLM-Beta] Result keys: {list(llm_result.keys()) if llm_result else 'None'}")
                guide = llm_result.get("guide_extracted") or {}
                logger.info(f"[LLM-Beta] guide_extracted: {len(guide)} fields")
                for k in list(guide.keys())[:3]:
                    logger.info(f"[LLM-Beta] guide_extracted['{k}']: {str(guide.get(k, ''))[:200]}")
                
                chunking_info = llm_result.get("_beta_chunking_info")
                if chunking_info:
                    logger.info(
                        f"[LLM-Beta] Chunking: {chunking_info.get('successful_chunks')}"
                        f"/{chunking_info.get('total_chunks')} chunks succeeded"
                    )
                    if chunking_info.get("errors"):
                        for err in chunking_info["errors"]:
                            logger.warning(f"[LLM-Beta] Chunk error: {err}")
            except Exception as diag_err:
                logger.warning(f"[LLM-Beta] Diagnostic logging failed (non-fatal): {diag_err}")

            # Ensure guide_extracted is never None
            if not llm_result.get("guide_extracted"):
                llm_result["guide_extracted"] = {}

            # Ensure raw_content is attached (OCR original text)
            if "raw_content" not in llm_result:
                llm_result["raw_content"] = ocr_data_to_send.get("content", "")
            if "raw_tables" not in llm_result:
                llm_result["raw_tables"] = ocr_data_to_send.get("tables", [])

            return llm_result
        
        # --- LEGACY PATH (No Beta) ---
        
        # PRE-EMPTIVE CHUNKING: If document is too large, skip direct call and chunk immediately.
        # Check actual JSON payload size, not just text content (metadata can be huge)
        json_payload = json.dumps(ocr_data_to_send, ensure_ascii=False)
        payload_len = len(json_payload)
        page_count = len(ocr_data_to_send.get("pages", []))
        
        # DEBUG: Print to ensure logging works
        logger.debug(f"[DEBUG-LLM] Payload size: {payload_len}, Pages: {page_count}")
        
        # Threshold: 20k chars or 5 pages (Production Tuned)
        if payload_len > 20000 or page_count > 5:
            logger.debug(f"[DEBUG-LLM] CHUNKING TRIGGERED! Size: {payload_len}, Pages: {page_count}")
            logger.info(f"[LLM] Payload too large (Size: {payload_len}, Pages: {page_count}), starting Pre-emptive Chunking...")
            try:
                from app.services.chunked_extraction import extract_with_chunking
                merged_result, errors = await extract_with_chunking(
                    ocr_data_to_send,
                    model.fields,
                    max_tokens_per_chunk=8000,
                    max_concurrent=8
                )
                
                if errors:
                    logger.warning(f"[LLM-Chunked] Some chunks failed: {errors}")
                
                # Merge structured result
                # Include raw tables in other_data so user can see something even if LLM fails
                raw_tables = ocr_data_to_send.get("tables", [])
                
                # IMPORTANT: Preserve _merge_info for debugging (contains LLM prompt/response info)
                merge_debug = merged_result.get("_merge_info", {})
                
                return {
                    "guide_extracted": {k: {"value": v.get("value"), "confidence": v.get("confidence", 0.0), "bbox": v.get("bbox"), "page_number": v.get("page_number")} for k, v in merged_result.items() if not k.startswith("_")},
                    "other_data": [{"type": "raw_tables", "tables": raw_tables}] if raw_tables else [],
                    "_chunked": True,
                    "_debug_chunking": merge_debug,  # LLM debug info (prompt sizes, responses, etc.)
                    "_chunking_errors": errors if errors else None
                }
            except Exception as chunk_error:
                logger.error(f"[LLM-Chunked] Pre-emptive chunking failed: {chunk_error}")
                # Don't silently fallback - raise error so user knows what happened
                raise Exception(f"DOCUMENT_CHUNKING_FAILED: {chunk_error}")

        
        field_descriptions = []
        for field in model.fields:
            desc = f"- {field.key}: {field.label}"
            if field.description:
                desc += f" ({field.description})"
            field_descriptions.append(desc)

        focus_instruction = ""
        if focus_pages:
            logger.info(f"[LLM] Focusing on pages: {focus_pages}")
            focus_instruction = f"\nIMPORTANT: FOCUS ONLY ON DATA FROM PAGES {focus_pages}. IGNORE OTHER PAGES."

        # Inject Global Rules if present
        global_rules_instruction = ""
        if model.global_rules:
            global_rules_instruction = f"\nGLOBAL EXTRACTION RULES (MUST FOLLOW):\n{model.global_rules}\n"

        # Inject Reference Data if present (Phase 1: structured JSON)
        reference_data_instruction = ""
        if model.reference_data:
            reference_data_instruction = f"""
REFERENCE DATA (Use for value mapping and validation):
{json.dumps(model.reference_data, ensure_ascii=False, indent=2)}

Use this reference data to:
- Map codes to names (e.g., customer_code → customer_name)
- Validate extracted values against expected patterns
- Apply transformation rules as specified
"""

        prompt = f"""You are a document data extractor.

Given this document data extracted by Document Intelligence (Pages: {focus_pages}):
{json.dumps(ocr_data_to_send, ensure_ascii=False)}

Extract values for these specific fields:
{chr(10).join(field_descriptions)}
{global_rules_instruction}{reference_data_instruction}
INSTRUCTIONS:
1. Analyze the document structure. If it looks like a table/grid, respect the columns.
2. For specific fields like 'Item' or 'Amount', look for corresponding headers in the table.
3. If a field represents a list of items (e.g. line items in a table), extract it as a JSON Array of objects with relevant keys.
4. Distinguish between 'Item' (product code/name) and 'Description' (details).
5. **Key-Value Tables**: If a table has a structure like [Field Name | Value], map the 'Value' column to the corresponding requested field. Do not treat it as a line item list.
6. **CRITICAL**: Extract values EXACTLY as they appear in the text. Do not reformat dates or numbers yet.
7. **CRITICAL**: You MUST include the 'bbox' (bounding box) for every extracted value. Copy it exactly from source.
8. **CRITICAL**: You MUST include the 'page_number' (1-based index) for every extracted value.

Return a JSON object with TWO parts:
1. "guide_extracted": Object with each field key containing:
   - "value": The extracted value exactly as in text
   - "confidence": Your confidence level from 0.0 to 1.0
   - "bbox": The bounding box [x1, y1, x2, y2] from the source data (REQUIRED)
   - "page_number": The page number (1-based integer) (REQUIRED)

2. "other_data": Array of other data found that wasn't matched to fields.

IMPORTANT:
- Use exact field keys.
- If value is not found, set value to null.
- Return ONLY valid JSON.{focus_instruction}"""

        logger.info(f"[LLM] Prompt prepared. Sending request to Azure OpenAI (Focus: {focus_pages})...")
        try:
            # Use dynamic model from Admin Settings
            from app.services.llm import get_current_model
            current_model_name = get_current_model()
            
            response = await self.azure_openai.chat.completions.create(
                model=current_model_name,
                messages=[
                    {"role": "system", "content": "You are a precise document data extractor. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0,
                response_format={"type": "json_object"}
            )
            raw_content = response.choices[0].message.content or ""
            
            # Capture token usage
            token_usage = None
            if response.usage:
                token_usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                }
                logger.info(f"[LLM-Token] Usage: {token_usage}")
            
            logger.info(f"[LLM-Custom-Debug] Success! Length: {len(raw_content)}")
            logger.info(f"[LLM-Custom-Debug] Preview: {raw_content[:200]}")
            
            result = json.loads(raw_content)
            result["_token_usage"] = token_usage  # Include token usage in result
            
            # ATTACH RAW CONTENT (CRITICAL FIX FOR LEGACY PATH)
            # Ensure OCR text is available even when not using Beta LayoutParser
            if "raw_content" not in result:
                result["raw_content"] = ocr_data_to_send.get("content", "")
                
            return result
        except Exception as e:
            error_str = str(e).lower()
            
            # Check if token limit exceeded - fallback to chunked processing
            if "token" in error_str or "context_length" in error_str or ("429" in str(e) and "rate" not in error_str):
                logger.warning(f"[LLM] Token limit exceeded, switching to chunked extraction...")
                
                try:
                    from app.services.chunked_extraction import extract_with_chunking
                    
                    # Convert model fields to dict format for chunked extraction
                    model_fields = [{"key": f.key, "label": f.label, "description": f.description} for f in model.fields]
                    
                    # Use chunked extraction
                    merged_result, errors = await extract_with_chunking(
                        ocr_data_to_send,
                        model_fields,
                        max_tokens_per_chunk=16000,  # Increased from 4000 for fewer LLM calls
                        max_concurrent=8  # Increased from 5 for better parallelism
                    )
                    
                    if errors:
                        logger.warning(f"[LLM-Chunked] Some chunks failed: {errors}")
                    
                    # Convert to expected format (Merged result is now rich object dict)
                    return {
                        "guide_extracted": {k: v for k, v in merged_result.items() if not k.startswith("_")},
                        "other_data": [],
                        "_chunked": True,
                        "_chunk_errors": errors,
                        "raw_content": ocr_data_to_send.get("content", "")  # CRITICAL: Attach OCR text
                    }
                except Exception as chunk_error:
                    logger.error(f"[LLM-Chunked] Fallback also failed: {chunk_error}")
                    raise e  # Re-raise original error
            
            logger.error(f"[LLM] Extraction failed: {e}")
            raise e

    def _validate_and_format(self, raw_data: Dict[str, Any], model: ExtractionModel, pages_info: List[Dict[str, Any]] = [], default_page: int = 1) -> Dict[str, Any]:
        """
        Strictly validates and formats data based on field types.
        AI provides the raw string, Code ensures it matches the Type.
        Adds confidence flags and normalizes bbox for frontend rendering.
        
        For TABLE mode: passes through _table_rows directly without field-by-field validation.
        """
        # TABLE MODE: early return — no field-by-field validation needed
        if raw_data.get("_is_table"):
            logger.info(f"[Validation] TABLE MODE: passing through {len(raw_data.get('_table_rows', []))} rows")
            return {
                "guide_extracted": raw_data.get("_table_rows", []),
                "_is_table": True,
                "raw_tables": raw_data.get("raw_tables"),
                "_token_usage": raw_data.get("_token_usage"),
                "_beta_chunking_info": raw_data.get("_beta_chunking_info"),
                "_beta_pipeline_stages": raw_data.get("_beta_pipeline_stages"),
                "_beta_parsed_content": raw_data.get("_beta_parsed_content"),
                "_beta_ref_map": raw_data.get("_beta_ref_map"),
                "error": raw_data.get("error"),
            }
        
        guide_extracted = raw_data.get("guide_extracted", {})
        
        # Defensive: if LLM returns a list instead of dict, convert or handle gracefully
        if isinstance(guide_extracted, list):
            logger.warning(f"[Validation] guide_extracted is a list, converting to dict")
            # Try to convert list to dict using 'key' field if present, otherwise numeric index
            converted = {}
            for i, item in enumerate(guide_extracted):
                if isinstance(item, dict) and 'key' in item:
                    converted[item['key']] = item
                elif isinstance(item, dict):
                    converted[f"item_{i}"] = item
            guide_extracted = converted
        elif not isinstance(guide_extracted, dict):
            logger.error(f"[Validation] guide_extracted is not a dict or list: {type(guide_extracted)}")
            guide_extracted = {}
        
        validated_extracted = {}

        CONFIDENCE_THRESHOLD = 0.7  # Flag values below this
        
        # Create a lookup for page dimensions (handle both snake_case and camelCase)
        page_dims = {
            (p.get("page_number") or p.get("pageNumber", i+1)): (p.get("width", 0), p.get("height", 0))
            for i, p in enumerate(pages_info)
        }

        for field in model.fields:
            key = field.key
            item = guide_extracted.get(key, {})
            if not item:
                logger.debug(f"[Validation] Field '{key}' NOT found in guide_extracted. Available keys: {list(guide_extracted.keys())[:10]}")
            # Defensive: item must also be a dict
            if not isinstance(item, dict):
                item = {"value": item} if item is not None else {}
            original_value = item.get("value")
            value = original_value
            confidence = item.get("confidence", 0)
            bbox = item.get("bbox")
            try:
                # Support both "page_number" (legacy path) and "page" (RefinerEngine beta path)
                raw_page = item.get("page_number") or item.get("page")
                page_number = int(raw_page) if raw_page else None
            except (ValueError, TypeError):
                page_number = None
            
            # Type Validation Logic (Restored)
            validation_status = "valid"
            if value is not None:
                if field.type == "number" or field.type == "currency":
                    parsed = self._parse_number(value)
                    if parsed is None and original_value is not None:
                        validation_status = "parse_failed"
                        value = original_value  # Keep original on failure
                    else:
                        value = parsed
                elif field.type == "date":
                    parsed = self._parse_date(value)
                    if parsed != original_value:
                        validation_status = "normalized"
                    value = parsed
            
            # --- SMART PAGE DISCOVERY (FIX FOR PAGE MISMATCH) ---
            # If page_number is missing, or if we want to be robust, check if the value actually exists on that page.
            # If not, search other pages in the split.
            
            detected_page = page_number
            if not detected_page:
                 detected_page = default_page
            
            # 1. Try to find the value on the detected/default page first
            snapped_bbox = None
            final_page_number = detected_page
            
            # Helper to search a specific page
            def search_page(p_num):
                p_data = next((p for p in pages_info if p["page_number"] == p_num), None)
                if p_data and "words" in p_data:
                    return self._snap_bbox_to_words(str(value), bbox, p_data["words"])
                return None

            # Attempt 1: Default/Provided Page
            snapped_bbox = search_page(final_page_number)
            
            # Attempt 2: If no match, search ALL other pages in the split
            if not snapped_bbox and pages_info:
                 for p_info in pages_info:
                     p_num = p_info["page_number"]
                     if p_num == final_page_number: continue # Already checked
                     
                     found_bbox = search_page(p_num)
                     if found_bbox:
                         snapped_bbox = found_bbox
                         final_page_number = p_num
                         logger.info(f"[SmartDiscovery] Value '{value}' found on Page {p_num} (was defaulting to {detected_page})")
                         break
            
            page_number = final_page_number
            # ----------------------------------------------------

            # Low confidence flag
            low_confidence = confidence < CONFIDENCE_THRESHOLD

            # Normalize bbox for frontend rendering
            normalized_bbox = None
            if snapped_bbox:
                p_w, p_h = 100, 100 # Default fallback
                if page_number and page_number in page_dims:
                     p_w, p_h = page_dims[page_number]
                
                normalized_bbox = self._normalize_bbox(snapped_bbox, page_width=p_w, page_height=p_h)
            
            validated_extracted[key] = {
                "value": value,
                "original_value": original_value if value != original_value else None,
                "confidence": confidence,
                "low_confidence": low_confidence,
                "validation_status": validation_status,
                "bbox": normalized_bbox, # This is crucial for highlighting
                "page_number": page_number
            }

        # Initialize container
        result = {
            "guide_extracted": validated_extracted,
            "other_data": raw_data.get("other_data", []),
            "model_fields": [{"key": f.key, "label": f.label} for f in model.fields]
        }
        
        # Preserve Beta Fields (LayoutParser)
        if "_beta_parsed_content" in raw_data:
            result["_beta_parsed_content"] = raw_data["_beta_parsed_content"]
        if "_beta_ref_map" in raw_data:
            result["_beta_ref_map"] = raw_data["_beta_ref_map"]
            
        # Preserve Raw Content (Critical for UI)
        if "raw_content" in raw_data:
            result["raw_content"] = raw_data["raw_content"]
            
        # Passthrough debug metadata if present
        if "_debug_chunking" in raw_data:
            result["_debug_chunking"] = raw_data["_debug_chunking"]
        if "_chunked" in raw_data:
            result["_chunked"] = raw_data["_chunked"]
        if "_chunking_errors" in raw_data:
            result["_chunking_errors"] = raw_data["_chunking_errors"]
            
        # Preserve Raw Tables (for Tables Tab)
        if "raw_tables" in raw_data:
            result["raw_tables"] = raw_data["raw_tables"]
        
        # Preserve Token Usage (for debug panel)
        if "_token_usage" in raw_data:
            result["_token_usage"] = raw_data["_token_usage"]
        
        # Preserve Beta Chunking Info (for debug panel)
        if "_beta_chunking_info" in raw_data:
            result["_beta_chunking_info"] = raw_data["_beta_chunking_info"]
        
        # Preserve Pipeline Stage Diagnostics (for debug panel)
        if "_beta_pipeline_stages" in raw_data:
            result["_beta_pipeline_stages"] = raw_data["_beta_pipeline_stages"]
        
        # Preserve Beta Parsed Content (for Parsed Text tab — includes tables as markdown)
        if raw_data.get("_beta_parsed_content"):
            result["_beta_parsed_content"] = raw_data["_beta_parsed_content"]
        if raw_data.get("_beta_ref_map"):
            result["_beta_ref_map"] = raw_data["_beta_ref_map"]
        
        # Preserve LLM error info (for diagnostics)
        if "error" in raw_data:
            result["error"] = raw_data["error"]
        
        return result
    
    def _snap_bbox_to_words(self, value: str, approximate_bbox: Optional[List[float]], words: List[Dict[str, Any]]) -> Optional[List[float]]:
        """
        Refines the bounding box by snapping to the exact coordinates of the matching words from OCR.
        """
        if not value:
            return None
            
        value_clean = str(value).replace(" ", "").replace(",", "").replace(".", "").replace("-", "").lower()
        if not value_clean:
            return None

        # 1. Build a list of candidate words sequences that match the value 
        import math

        def get_bbox_center(b):
            return ((b[0]+b[2])/2, (b[1]+b[3])/2)
            
        def get_dist(b1, b2):
             c1 = get_bbox_center(b1)
             c2 = get_bbox_center(b2)
             return math.sqrt((c1[0]-c2[0])**2 + (c1[1]-c2[1])**2)

        candidate_polygons = []
        
        # Extended cleaning for token matching
        def clean_token(t):
             return str(t).replace(" ","").replace(",","").replace(".","").replace("-","").lower()

        # Try to find the exact value as a single token first
        exact_matches = [w for w in words if clean_token(w.get("content", "")) == value_clean]
        
        if exact_matches:
             for m in exact_matches:
                 poly = m.get("polygon")
                 if poly and len(poly) >= 8: 
                     xs = poly[0::2]
                     ys = poly[1::2]
                     candidate_polygons.append([min(xs), min(ys), max(xs), max(ys)])
        
        # Also try partial contains logical if no exact match (e.g. currency symbol in OCR)
        if not candidate_polygons:
             partial_matches = [w for w in words if value_clean in clean_token(w.get("content", ""))]
             for m in partial_matches:
                 poly = m.get("polygon")
                 if poly and len(poly) >= 8:
                     xs = poly[0::2]
                     ys = poly[1::2]
                     candidate_polygons.append([min(xs), min(ys), max(xs), max(ys)])

        if not candidate_polygons:
            return approximate_bbox # Fallback

        # 2. Select best match
        if not approximate_bbox:
            return candidate_polygons[0] # Return first match
            
        best_bbox = approximate_bbox
        min_dist = float('inf')
        
        for cand in candidate_polygons:
            d = get_dist(approximate_bbox, cand)
            if d < min_dist:
                min_dist = d
                best_bbox = cand
                
        return best_bbox

    def _parse_number(self, value: Any) -> Optional[float]:
        """Strict number parsing - delegates to extraction_utils"""
        return parse_number(value)

    def _parse_date(self, value: Any) -> Optional[str]:
        """Strict date parsing to ISO8601 - delegates to extraction_utils"""
        return parse_date(value)

    def _normalize_bbox(self, bbox: Any, page_width: float = 0, page_height: float = 0) -> Optional[List[float]]:
        """Normalize bbox to percentages - delegates to extraction_utils"""
        return normalize_bbox(bbox, page_width, page_height)

# Singleton instance
extraction_service = ExtractionService()

