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
        try:
            with open("debug_pipeline.log", "a") as f:
                f.write(f"\n=== JOB {job_id} STARTED ===\n")

            # Update status
            extraction_jobs.update_job(job_id, status=ExtractionStatus.ANALYZING.value)

            # 1. Get Model & OCR
            model = models.get_model_by_id(model_id)
            if not model:
                raise ValueError(f"Model {model_id} not found")

            # Dynamic Strategy
            azure_model = getattr(model, "azure_model_id", "prebuilt-layout")
            with open("debug_pipeline.log", "a") as f:
                f.write(f"calling doc_intel with {azure_model}\n")
            
            doc_intel_output = doc_intel.extract_with_strategy(file_url, azure_model)
            
            with open("debug_pipeline.log", "a") as f:
                f.write(f"OCR finish. Keys: {doc_intel_output.keys()}, Pages: {len(doc_intel_output.get('pages', []))}\n")

            # 2. Splitting
            from app.services import splitter
            splits = await splitter.detect_and_split(doc_intel_output, file_url)
            
            with open("debug_pipeline.log", "a") as f:
                f.write(f"Splits detected: {len(splits)}\n")
            
            # 3. Process Each Split
            sub_documents = []
            for split in splits:
                try:
                    with open("debug_pipeline.log", "a") as f:
                        f.write(f"Processing split {split['index']}...\n")
                    
                    split_result = await self._process_single_split(doc_intel_output, split, model)
                    sub_documents.append(split_result)
                except Exception as e:
                    with open("debug_pipeline.log", "a") as f:
                        f.write(f"Error processing split {split['index']}: {e}\n")
                    logger.error(f"Error processing split {split['index']}: {e}")
                    # Continue to next split (don't fail entire job)
                    sub_documents.append({
                         "index": split["index"],
                         "status": "error",
                         "error": str(e)
                    })
                    logger.error(f"[Extraction] Split {split['index']} failed: {e}")
                    sub_documents.append({
                        "index": split["index"],
                        "status": "error",
                        "error": str(e)
                    })

            # 4. Aggregation & Save
            # We preserve the legacy 'preview_data' structure for the first document 
            # to maintain backward compatibility for now, OR switch entirely.
            # Let's switch to a structure that supports both.
            
            with open("debug_pipeline.log", "a") as f:
                f.write(f"All splits processed. Total sub_documents: {len(sub_documents)}\n")
            
            # Legacy fallback: Use first doc
            legacy_preview = sub_documents[0]["data"] if sub_documents and "data" in sub_documents[0] else {}

            with open("debug_pipeline.log", "a") as f:
                f.write(f"Calling update_job with status=SUCCESS...\n")
            
            result = extraction_jobs.update_job(
                job_id, 
                status=ExtractionStatus.SUCCESS.value, 
                preview_data={
                    "sub_documents": sub_documents,
                    **legacy_preview # Flatten first doc for legacy UI support
                }
            )
            
            # Also update the associated Log status to S100 (완료)
            job = extraction_jobs.get_job(job_id)
            if job and job.original_log_id:
                # Build the same preview_data structure for the log
                log_preview_data = {
                    "sub_documents": sub_documents,
                    **legacy_preview  # Flatten first doc for legacy UI support
                }
                extraction_logs.save_extraction_log(
                    model_id=model_id,
                    user_id=job.user_id,
                    user_name=job.user_name,
                    user_email=job.user_email,
                    filename=job.filename,
                    file_url=file_url,
                    status=ExtractionStatus.SUCCESS.value,  # S100 - 완료
                    extracted_data=legacy_preview.get("guide_extracted", {}),  # ✅ Add extracted data
                    preview_data=log_preview_data,  # ✅ Add preview data
                    log_id=job.original_log_id,
                    job_id=job_id
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
                    log_id=job.original_log_id
                )


    async def _process_single_split(self, full_ocr_data: Dict[str, Any], split: Dict[str, Any], model: ExtractionModel) -> Dict[str, Any]:
        """
        Runs extraction on a specific sub-document split.
        """
        # Unwrap LLM Extraction with focus on specific pages
        raw_extraction = await self._unwrap_llm_extraction(full_ocr_data, model, focus_pages=split["page_ranges"])
        
        # Validation
        validated_data = self._validate_and_format(raw_extraction, model, full_ocr_data.get("pages", []))
        
        return {
            "index": split["index"],
            "type": split["type"],
            "page_ranges": split["page_ranges"],
            "status": "success",
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

Return a JSON object with TWO parts:
1. "guide_extracted": Object with each field key containing:
   - "value": The extracted value (string or null if not found)
   - "confidence": Your confidence level from 0.0 to 1.0
   - "bbox": The bounding box [x1, y1, x2, y2] (extracted exactly as appearing in the source JSON)
   - "page_number": The page number (1-based) from source data if available

2. "other_data": Array of other data found that wasn't matched to fields.

IMPORTANT:
- Use exact field keys.
- If value is not found, set value to null.
- Return ONLY valid JSON.{focus_instruction}"""

        logger.info(f"[LLM] Prompt prepared. Sending request to Azure OpenAI (Focus: {focus_pages})...")
        try:
            response = await self.azure_openai.chat.completions.create(
                model=settings.AZURE_OPENAI_DEPLOYMENT_NAME,
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
            logger.error(f"[LLM] Error calling OpenAI: {e}")
            raise e

    def _validate_and_format(self, raw_data: Dict[str, Any], model: ExtractionModel, pages_info: List[Dict[str, Any]] = []) -> Dict[str, Any]:
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
            if value and pages_info:
                # Determine target page (use AI's page or default to 1)
                target_page = page_number if page_number else 1
                
                # Find page data
                page_data = next((p for p in pages_info if p["page_number"] == target_page), None)
                
                if page_data and "words" in page_data:
                     best_match_bbox = self._snap_bbox_to_words(value, bbox, page_data["words"])
                     if best_match_bbox:
                         snapped_bbox = best_match_bbox
                         # If we found it on this page, ensure page_number is set
                         page_number = target_page

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
                "bbox": normalized_bbox,
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
        Strategy:
        1. Find all occurrences of the 'value' string in the words list (could be multi-word).
        2. If 'approximate_bbox' is provided, pick the occurrence closest to it (IOU or Center Distance).
        3. If no 'approximate_bbox', pick the first distinct match (risky, but better than nothing).
        """
        if not value:
            return None
            
        value_clean = str(value).replace(" ", "").lower()
        if not value_clean:
            return None

        # 1. Build a list of candidate words sequences that match the value 
        # (This is a simplified implementation: Checking combined strings)
        # Real-world: Need n-gram search or sliding window. 
        # Low-latency approach: Check if value exists as a substring of combined words? 
        # Better: iterate words and try to form the string.
        
        matches = [] # List of [bbox]
        
        # Sliding window? O(N*M). Words ~1000. manageable.
        current_sequence = []
        current_str = ""
        
        # Optimization: Filter words that might contain parts of the value
        # But values can be "Total Amount" (2 words).
        
        import math

        def get_bbox_center(b):
            return ((b[0]+b[2])/2, (b[1]+b[3])/2)
            
        def get_dist(b1, b2):
             c1 = get_bbox_center(b1)
             c2 = get_bbox_center(b2)
             return math.sqrt((c1[0]-c2[0])**2 + (c1[1]-c2[1])**2)

        # Simplified Snapping: Look for exact word matches first
        # Because full sentence matching is complex.
        
        candidate_polygons = []
        
        # Try to find the exact value as a single token first (e.g. ID numbers, Dates)
        exact_matches = [w for w in words if str(w["content"]).replace(" ","").lower() == value_clean]
        if exact_matches:
             # Gather their bboxes
             for m in exact_matches:
                 poly = m["polygon"]
                 if len(poly) >= 8: # Azure returns 8 points [x1,y1, x2,y2...]
                     xs = poly[0::2]
                     ys = poly[1::2]
                     candidate_polygons.append([min(xs), min(ys), max(xs), max(ys)])
        else:
             # Multi-word match?
             # For now, simplistic approach: if value is long, we rely on approximate_bbox. 
             # If approximate_bbox is BAD, we can't fix it easily without vector search.
             pass

        if not candidate_polygons:
            return approximate_bbox # Fallback to LLM's guess if no OCR match found

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
                
        # heuristic: if distance is massive, maybe it's the wrong instance? 
        # But usually better than random.
        
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

