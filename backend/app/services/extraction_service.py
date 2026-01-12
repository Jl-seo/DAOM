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
from app.schemas.model import ExtractionModel, FieldDefinition

logger = logging.getLogger(__name__)

class ExtractionService:
    def __init__(self):
        self.azure_openai = AsyncAzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT
        )

    async def run_extraction_pipeline(self, job_id: str, model_id: str, file_url: str, candidate_file_url: Optional[str] = None, candidate_file_urls: Optional[List[str]] = None):
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
                print(f"[Pipeline] Starting 1:N Comparison for Job {job_id} on {len(all_candidates)} candidates")
                from app.services import llm
                
                comparison_results = []
                
                # Run Comparison using GPT-4 Vision for EACH candidate
                # Process in parallel for speed if possible, or sequential for safety
                # Using simple loop for now to avoid complexity
                for idx, c_url in enumerate(all_candidates):
                    print(f"[Pipeline] Comparing Candidate {idx+1}/{len(all_candidates)}")
                    try:
                        res = await llm.compare_images(file_url, c_url)
                        comparison_results.append({
                            "candidate_index": idx,
                            "file_url": c_url,
                            "result": res
                        })
                    except Exception as comp_error:
                        logger.error(f"[Pipeline] Comparison failed for candidate {c_url}: {comp_error}")
                        comparison_results.append({
                            "candidate_index": idx,
                            "file_url": c_url,
                            "error": str(comp_error),
                            "result": {}
                        })

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

            print(f"[Pipeline-Debug] Calling doc_intel with {azure_model}")
            
            doc_intel_output = await doc_intel.extract_with_strategy(file_url, azure_model)
            
            # ... (OCR log) ...

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
            print(f"[Pipeline-Debug] All splits processed. Total sub_documents: {len(sub_documents)}")
            
            preview_payload = {
                "sub_documents": sub_documents
            }
            
            result = extraction_jobs.update_job(
                job_id, 
                status=ExtractionStatus.SUCCESS.value, 
                preview_data=preview_payload
            )
            
            if not result:
                logger.error(f"Failed to update job {job_id} with success data.")
                extraction_jobs.update_job(job_id, status=ExtractionStatus.ERROR.value, error="Failed to save extraction results")
                return
            
            
            print(f"[Pipeline-Debug] Job {job_id} completed successfully!")
            
            # Sync status to ExtractionLog if linked
            job = extraction_jobs.get_job(job_id)
            if job and (job.original_log_id or job.log_id):
                log_id_to_update = job.original_log_id or job.log_id
                # Also save preview_data to log so it can be viewed later
                extraction_logs.update_log_status(
                    log_id_to_update, 
                    status=ExtractionStatus.SUCCESS.value,
                    preview_data=preview_payload
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

        filtered_data = {
            "api_version": ocr_data.get("api_version"),
            "model_id": ocr_data.get("model_id"),
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
                    filtered_data["pages"].append(p)

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
            raw_content = response.choices[0].message.content
            print(f"[LLM-Universal-Debug] Success! Length: {len(raw_content)}")
            print(f"[LLM-Universal-Debug] Preview: {raw_content[:200]}")
            return json.loads(raw_content)
        except Exception as e:
            error_str = str(e).lower()
            
            # Check if token limit exceeded - fallback to chunked processing
            if "token" in error_str or "context_length" in error_str or ("429" in str(e) and "rate" not in error_str):
                logger.warning(f"[LLM-Universal] Token limit exceeded, switching to chunked extraction...")
                
                try:
                    from app.services.chunked_extraction import extract_with_chunking
                    
                    # Universal mode: discover all fields
                    model_fields = [{"key": "_discover", "label": "Discover all fields", "description": "Extract all key-value pairs"}]
                    
                    merged_result, errors = await extract_with_chunking(
                        ocr_data_to_send,
                        model_fields,
                        max_tokens_per_chunk=2000,
                        max_concurrent=3
                    )
                    
                    if errors:
                        logger.warning(f"[LLM-Universal-Chunked] Some chunks failed: {errors}")
                    
                    return {
                        "guide_extracted": {k: {"value": v, "confidence": 0.8, "type": "string"} for k, v in merged_result.items() if not k.startswith("_")},
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
            
            if not page_number:
                page_number = default_page
            
            # Try basic snapping
            snapped_bbox = bbox
            if value and pages_info:
                target_page = page_number
                page_data = next((p for p in pages_info if p["page_number"] == target_page), None)
                if page_data and "words" in page_data:
                     best = self._snap_bbox_to_words(str(value), bbox, page_data["words"])
                     if best: snapped_bbox = best

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

        return {
            "guide_extracted": validated_extracted,
            "other_data": raw_data.get("other_data", []),
            "model_fields": [{"key": k, "label": k} for k in validated_extracted.keys()] # Dynamic fields
        }


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

        prompt = f"""You are a document data extractor.

Given this document data extracted by Document Intelligence (Pages: {focus_pages}):
{json.dumps(ocr_data_to_send, ensure_ascii=False)}

Extract values for these specific fields:
{chr(10).join(field_descriptions)}
{global_rules_instruction}
INSTRUCTIONS:
1. Analyze the document structure. If it looks like a table/grid, respect the columns.
2. For specific fields like 'Item' or 'Amount', look for corresponding headers in the table.
3. If a field represents a list of items (e.g. line items in a table), extract it as a JSON Array of objects with relevant keys.
4. Distinguish between 'Item' (product code/name) and 'Description' (details).
5. **CRITICAL**: Extract values EXACTLY as they appear in the text. Do not reformat dates or numbers yet.
6. **CRITICAL**: You MUST include the 'bbox' (bounding box) for every extracted value. Copy it exactly from source.
7. **CRITICAL**: You MUST include the 'page_number' (1-based index) for every extracted value.

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
            raw_content = response.choices[0].message.content
            
            print(f"[LLM-Custom-Debug] Success! Length: {len(raw_content)}")
            print(f"[LLM-Custom-Debug] Preview: {raw_content[:200]}")
            
            return json.loads(raw_content)
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
                        max_tokens_per_chunk=2000,
                        max_concurrent=3
                    )
                    
                    if errors:
                        logger.warning(f"[LLM-Chunked] Some chunks failed: {errors}")
                    
                    # Convert to expected format
                    return {
                        "guide_extracted": {k: {"value": v, "confidence": 0.8} for k, v in merged_result.items() if not k.startswith("_")},
                        "other_data": [],
                        "_chunked": True,
                        "_chunk_errors": errors
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
        """
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
        
        # Create a lookup for page dimensions
        page_dims = {p["page_number"]: (p["width"], p["height"]) for p in pages_info}

        for field in model.fields:
            key = field.key
            item = guide_extracted.get(key, {})
            # Defensive: item must also be a dict
            if not isinstance(item, dict):
                item = {"value": item} if item is not None else {}
            original_value = item.get("value")
            value = original_value
            confidence = item.get("confidence", 0)
            bbox = item.get("bbox")
            try:
                page_number = int(item.get("page_number")) if item.get("page_number") else None
            except (ValueError, TypeError):
                page_number = None
            
            if not page_number:
                page_number = default_page

            # Type Validation Logic
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
                # String is default, no processing needed
            
            # Low confidence flag
            low_confidence = confidence < CONFIDENCE_THRESHOLD
            
            # Smart Snapping: Correct LLM's rough bbox using precise OCR word coordinates
            snapped_bbox = bbox
            if original_value and pages_info:
                # Determine target page
                target_page = page_number 
                
                # Find page data
                page_data = next((p for p in pages_info if p["page_number"] == target_page), None)
                
                if page_data and "words" in page_data:
                     # Use original_value for snapping to avoid format mismatch
                     best_match_bbox = self._snap_bbox_to_words(str(original_value), bbox, page_data["words"])
                     if best_match_bbox:
                         snapped_bbox = best_match_bbox

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

        return {
            "guide_extracted": validated_extracted,
            "other_data": raw_data.get("other_data", []),
            "model_fields": [{"key": f.key, "label": f.label} for f in model.fields]
        }
    
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
        exact_matches = [w for w in words if clean_token(w["content"]) == value_clean]
        
        if exact_matches:
             for m in exact_matches:
                 poly = m["polygon"]
                 if len(poly) >= 8: 
                     xs = poly[0::2]
                     ys = poly[1::2]
                     candidate_polygons.append([min(xs), min(ys), max(xs), max(ys)])
        
        # Also try partial contains logical if no exact match (e.g. currency symbol in OCR)
        if not candidate_polygons:
             partial_matches = [w for w in words if value_clean in clean_token(w["content"])]
             for m in partial_matches:
                 poly = m["polygon"]
                 if len(poly) >= 8:
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
        """Strict number parsing"""
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            # Remove currency symbols and commas
            clean = value.replace(",", "").replace("₩", "").replace("$", "").replace("원", "").strip()
            try:
                return float(clean)
            except ValueError:
                return None # Fail gracefully or set flag
        return None

    def _parse_date(self, value: Any) -> Optional[str]:
        """Strict date parsing to ISO8601 YYYY-MM-DD"""
        import re
        
        if not isinstance(value, str) or not value:
            return None
        
        value = value.strip()
        
        # Already ISO format
        if re.match(r'^\d{4}-\d{2}-\d{2}$', value):
            return value
        
        # Common Korean formats
        # YYYY년 MM월 DD일
        match = re.match(r'^(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일', value)
        if match:
            return f"{match.group(1)}-{match.group(2).zfill(2)}-{match.group(3).zfill(2)}"
        
        # YYYY.MM.DD or YYYY/MM/DD
        match = re.match(r'^(\d{4})[./](\d{1,2})[./](\d{1,2})', value)
        if match:
            return f"{match.group(1)}-{match.group(2).zfill(2)}-{match.group(3).zfill(2)}"
        
        # DD/MM/YYYY or MM/DD/YYYY (assume MM/DD/YYYY for US format)
        match = re.match(r'^(\d{1,2})[./](\d{1,2})[./](\d{4})', value)
        if match:
            # Assume MM/DD/YYYY
            return f"{match.group(3)}-{match.group(1).zfill(2)}-{match.group(2).zfill(2)}"
        
        # If nothing matched, return original (let AI's normalization stand)
        return value

    def _normalize_bbox(self, bbox: Any, page_width: float = 0, page_height: float = 0) -> Optional[List[float]]:
        """
        Normalize bbox to percentage coordinates (0-100) for frontend rendering.
        Accepts [x1, y1, x2, y2] or polygon and returns [x1, y1, x2, y2] in percentages.
        """
        if not bbox or not isinstance(bbox, (list, tuple, dict)):
            return None
        
        try:
            # Handle 8-point polygon (x1,y1, x2,y2, x3,y3, x4,y4) -> convert to bbox [min_x, min_y, max_x, max_y]
            if isinstance(bbox, dict):
                 # Handle dictionary input (e.g. from LLM)
                 x1 = float(bbox.get("x1", bbox.get("x", 0)))
                 y1 = float(bbox.get("y1", bbox.get("y", 0)))
                 x2 = float(bbox.get("x2", bbox.get("w", 0) + x1)) # Handle w/h if needed or x2
                 y2 = float(bbox.get("y2", bbox.get("h", 0) + y1))
            elif len(bbox) >= 8:
                xs = bbox[0::2]
                ys = bbox[1::2]
                x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)
            else:
                x1, y1, x2, y2 = [float(b) for b in bbox[:4]]
            
            # Case 1: Page dimensions are provided - calculate percentages
            if page_width > 0 and page_height > 0:
                return [
                    (x1 / page_width) * 100,
                    (y1 / page_height) * 100,
                    (x2 / page_width) * 100,
                    (y2 / page_height) * 100
                ]
            
            # Case 2: Coordinates already look like percentages (0-100 range)
            # CAUTION: If document is tiny (inches < 20), this might mistakenly treat inches as percentages.
            # But since LLMs or OCR might output inches, we should check reasonable bounds.
            # If width > 20, it's likely pixels. If < 20, likely inches.
            # If strict 0-100 used for percentages, we can't distinguish 5 inches from 5%.
            # However, doc intel "inches" usually implies we SHOULD normalize against 8.5x11.
            
            # Case 3: Azure Document Intelligence returns inches (typically 0-11 for letter size)
            if all(0 <= v <= 20 for v in [x1, y1, x2, y2]):
                # Assume standard letter size in inches if no page dims provided
                default_page_width = 8.5
                default_page_height = 11.0
                return [
                    (x1 / default_page_width) * 100,
                    (y1 / default_page_height) * 100,
                    (x2 / default_page_width) * 100,
                    (y2 / default_page_height) * 100
                ]
            
            # Case 4: Coordinates might be in pixels 
            if x2 > 100 or y2 > 100:
                estimated_width = max(x2 * 1.1, 612)
                estimated_height = max(y2 * 1.1, 792)
                return [
                    (x1 / estimated_width) * 100,
                    (y1 / estimated_height) * 100,
                    (x2 / estimated_width) * 100,
                    (y2 / estimated_height) * 100
                ]
            
            # Fallback (Case 2 match): Return as-is if it looks like percentages (0-100) but not inches (<20 handled above)
            return [x1, y1, x2, y2]

        except (ValueError, TypeError) as e:
            logger.error(f"[_normalize_bbox] Error: {e}, bbox: {bbox}")
            return None

# Singleton instance
extraction_service = ExtractionService()

