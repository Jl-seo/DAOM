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

    async def run_extraction_pipeline(self, job_id: str, model_id: str, file_url: str):
        """
        Orchestrates the full extraction pipeline with Multi-Document Support:
        1. OCR (Doc Intelligence)
        2. Splitting (Azure or GPT)
        3. Extraction per Split
        4. Aggregation
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
                model = models.get_model_by_id(model_id)
                if not model:
                    raise ValueError(f"Model {model_id} not found")
                # Dynamic Strategy - BUT for LLM extraction, 'prebuilt-layout' is consistently best for bbox/words.
                # 'prebuilt-invoice' often lacks detailed word maps on secondary pages or uses different coordinate logic.
                # We enforce layout to ensure Highlighting works reliable.
                azure_model = "prebuilt-layout" # getattr(model, "azure_model_id", "prebuilt-layout")

            with open("debug_pipeline.log", "a") as f:
                f.write(f"calling doc_intel with {azure_model}\n")
            
            doc_intel_output = doc_intel.extract_with_strategy(file_url, azure_model)
            
            # ... (OCR log) ...

            # 2. Splitting (Same as before)
            # ...

            # 3. Process Each Split
            sub_documents = []
            for split in splits:
                try:
                    # ... (log) ...
                    
                    if model.id == "system-universal":
                         split_result = await self._process_single_split_universal(doc_intel_output, split)
                    else:
                         split_result = await self._process_single_split(doc_intel_output, split, model)
                    
                    sub_documents.append(split_result)
                except Exception as e:
                    # ... (error handling) ...

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

    async def _unwrap_universal_extraction(self, ocr_data: Dict[str, Any], focus_pages: List[int] = None) -> Dict[str, Any]:
        """Ask LLM to discover ANY relevant fields"""
        focus_instruction = ""
        if focus_pages:
            logger.info(f"[LLM-Universal] Focusing on pages: {focus_pages}")
            focus_instruction = f"\nIMPORTANT: FOCUS ONLY ON DATA FROM PAGES {focus_pages}. IGNORE OTHER PAGES."

        prompt = f"""You are a universal document data extractor.

Given this document data extracted by Document Intelligence:
{json.dumps(ocr_data, ensure_ascii=False, indent=2)}

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
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"[LLM] Universal Extraction Error: {e}")
            return {"guide_extracted": {}, "error": str(e)}

    def _validate_and_format_universal(self, raw_data: Dict[str, Any], pages_info: List[Dict[str, Any]], default_page: int = 1) -> Dict[str, Any]:
        """Relaxed validation for universal mode"""
        guide_extracted = raw_data.get("guide_extracted", {})
        validated_extracted = {}
        
        page_dims = {p["page_number"]: (p["width"], p["height"]) for p in pages_info}

        for key, item in guide_extracted.items():
            if not isinstance(item, dict): continue
            
            value = item.get("value")
            bbox = item.get("bbox")
            page_number = item.get("page_number")
            
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
            
            with open("debug_pipeline.log", "a") as f:
                f.write(f"All splits processed. Total sub_documents: {len(sub_documents)}\n")
            
            with open("debug_pipeline.log", "a") as f:
                f.write(f"Calling update_job with status=SUCCESS...\n")
            
            # OPTIMIZATION: Only save sub_documents
            preview_payload = {
                "sub_documents": sub_documents
            }
            
            result = extraction_jobs.update_job(
                job_id, 
                status=ExtractionStatus.SUCCESS.value, 
                preview_data=preview_payload
            )
            
            if not result:
                logger.error(f"Failed to update job {job_id} with success data. Payload might be too large.")
                extraction_jobs.update_job(job_id, status=ExtractionStatus.ERROR.value, error="Failed to save extraction results (Data too large)")
                return
            
            # Also update the associated Log status to S100
            job = extraction_jobs.get_job(job_id)
            if job and job.original_log_id:
                extraction_logs.save_extraction_log(
                    model_id=model_id,
                    user_id=job.user_id,
                    user_name=job.user_name,
                    user_email=job.user_email,
                    filename=job.filename,
                    file_url=file_url,
                    status=ExtractionStatus.SUCCESS.value,
                    extracted_data=sub_documents[0]["data"].get("guide_extracted", {}) if sub_documents else {},
                    preview_data=preview_payload,
                    log_id=job.original_log_id,
                    job_id=job_id,
                    llm_model=current_llm_model
                )
                with open("debug_pipeline.log", "a") as f:
                    f.write(f"Updated Log {job.original_log_id} to S100 with preview_data\\n")
            
            with open("debug_pipeline.log", "a") as f:
                f.write(f"update_job result: {result is not None}\n")
            
            logger.info(f"Extraction job {job_id} completed with {len(sub_documents)} sub-documents")

        except Exception as e:
            with open("debug_pipeline.log", "a") as f:
                f.write(f"EXCEPTION: {e}\n")
            extraction_jobs.update_job(job_id, status=ExtractionStatus.ERROR.value, error=str(e))
            
            # Also update the associated Log status to ERROR
            job = extraction_jobs.get_job(job_id)
            if job and job.original_log_id:
                extraction_logs.save_extraction_log(
                    model_id=model_id,
                    user_id=job.user_id,
                    user_name=job.user_name,
                    user_email=job.user_email,
                    filename=job.filename,
                    file_url=file_url,
                    status=ExtractionStatus.ERROR.value,
                    error=str(e),
                    log_id=job.original_log_id,
                    llm_model=current_llm_model
                )


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

Given this document data extracted by Document Intelligence:
{json.dumps(ocr_data, ensure_ascii=False, indent=2)}

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
            
            # File Logging for Debug
            with open("debug_extraction.log", "a") as f:
                f.write(f"\n--- Extraction Request ---\nFocus: {focus_pages}\n")
                f.write(f"Response: {raw_content}\n")
            
            return json.loads(raw_content)
        except Exception as e:
            with open("debug_extraction.log", "a") as f:
                f.write(f"\n--- ERROR ---\n{e}\n")
                f.write(f"Config: Endpoint={settings.AZURE_OPENAI_ENDPOINT}, Version={settings.AZURE_OPENAI_API_VERSION}\n")
            
            logger.error(f"[LLM] Error calling OpenAI: {e}")
            logger.error(f"[LLM] Config Debug: Endpoint={settings.AZURE_OPENAI_ENDPOINT}, Model={settings.AZURE_OPENAI_DEPLOYMENT_NAME}")
            
            # Return detailed error for frontend
            return {
                "guide_extracted": {},
                "other_data": [],
                "error": str(e)
            }

    def _validate_and_format(self, raw_data: Dict[str, Any], model: ExtractionModel, pages_info: List[Dict[str, Any]] = [], default_page: int = 1) -> Dict[str, Any]:
        """
        Strictly validates and formats data based on field types.
        AI provides the raw string, Code ensures it matches the Type.
        Adds confidence flags and normalizes bbox for frontend rendering.
        """
        guide_extracted = raw_data.get("guide_extracted", {})
        validated_extracted = {}

        CONFIDENCE_THRESHOLD = 0.7  # Flag values below this
        
        # Create a lookup for page dimensions
        page_dims = {p["page_number"]: (p["width"], p["height"]) for p in pages_info}

        for field in model.fields:
            key = field.key
            item = guide_extracted.get(key, {})
            original_value = item.get("value")
            value = original_value
            confidence = item.get("confidence", 0)
            bbox = item.get("bbox")
            page_number = item.get("page_number")
            
            # Fallback for page_number if missing
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

    def _normalize_bbox(self, bbox: Any, page_width: float = 0, page_height: float = 0) -> Optional[Dict[str, float]]:
        """
        Normalize bbox to percentage coordinates (0-100) for frontend rendering.
        Accepts [x1, y1, x2, y2] and returns {x1, y1, width, height} in percentages.
        """
        if not bbox or not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
            return None
        
        try:
            x1, y1, x2, y2 = [float(b) for b in bbox[:4]]
            
            # If coordinates are seemingly already in 0-100 range (percentage)
            # Checking if both width/height are <= 1 might indicate normalized 0-1 too, 
            # but usually pixel coordinates for docs are much larger.
            # However, if page dims are not provided, we might assume they are already normalized? 
            # Or if they are very small.
            
            # Case 1: Already Percentage-ish
            # BUT: Azure usually returns Inches or Pixels.
            
            # Allow pure calculation if page dimensions are valid
            if page_width > 0 and page_height > 0:
                return {
                    "x1": (x1 / page_width) * 100,
                    "y1": (y1 / page_height) * 100,
                    "width": ((x2 - x1) / page_width) * 100,
                    "height": ((y2 - y1) / page_height) * 100
                }
            
            # Fallback: legacy logic or guess
            # If coordinates look like percentages (0-100) and no page info
            if all(0 <= v <= 100 for v in [x1, y1, x2, y2]):
                 return {
                    "x1": x1,
                    "y1": y1,
                    "width": x2 - x1,
                    "height": y2 - y1
                }

            return None
        except (ValueError, TypeError):
            return None

# Singleton instance
extraction_service = ExtractionService()

