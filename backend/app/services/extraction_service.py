"""
Extraction Service
Handles document data extraction, validation, and post-processing.
Delegates LLM calls to specialized services (Beta Chunking) or handles them directly via Legacy logic.
"""
import json
import logging
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime

from app.services.doc_intel import analyze_document_layout
from app.services.models import get_model_by_id
from app.schemas.model import ExtractionModel
from app.core.config import settings
from app.services.llm import call_llm_single, get_current_model

# Async Azure OpenAI client for direct calls
from openai import AsyncAzureOpenAI

logger = logging.getLogger(__name__)

class ExtractionService:
    def __init__(self):
        self.azure_openai = AsyncAzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT
        )

    async def run_extraction_pipeline(self, file_content: bytes, model_id: str, filename: str = "", mime_type: str = "") -> Dict[str, Any]:
        """
        Main entry point for extraction.
        1. OCR (Layout Analysis)
        2. Field Extraction (LLM)
        3. Post-processing/Validation
        """
        start_time = datetime.utcnow()
        logger.info(f"[Extraction] Starting pipeline for model {model_id}, file: {filename}")

        # 1. Get Model
        try:
            model = get_model_by_id(model_id)
        except Exception as e:
            logger.error(f"[Extraction] Model not found: {e}")
            return {"error": f"Model {model_id} not found"}

        # 2. Document Intelligence (OCR)
        try:
            ocr_result = await analyze_document_layout(file_content, mime_type=mime_type)
        except Exception as e:
            logger.error(f"[Extraction] OCR failed: {e}")
            return {"error": f"OCR Analysis failed: {str(e)}"}
            
        # 3. LLM Extraction
        try:
            # We pass the full model object to allow checking flags/rules
            processed_data = await self._unwrap_llm_extraction(ocr_result, model)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.error(f"[Extraction] LLM Extraction failed: {e}", exc_info=True)
            return {"error": f"Extraction failed: {str(e)}\n\nTraceback:\n{tb}"}

        # 4. Validation & Formatting
        final_result = self._validate_and_format(processed_data, model, ocr_result.get("pages", []))

        duration = (datetime.utcnow() - start_time).total_seconds()
        final_result["_meta"] = {
            "duration_seconds": duration,
            "filename": filename,
            "model_name": model.name,
            "timestamp": start_time.isoformat()
        }

        return final_result

    def _filter_ocr_data(self, ocr_data: Dict[str, Any], focus_pages: List[int]) -> Dict[str, Any]:
        """Filter OCR data to only include specific pages"""
        if not focus_pages:
            return ocr_data

        filtered = {
            "content": "",
            "pages": [],
            "paragraphs": [],
            "tables": [],
            "styles": ocr_data.get("styles", [])
        }
        
        # Helper to check if item is on focus pages
        def is_on_focus_page(item):
            regions = item.get("bounding_regions") or item.get("boundingRegions") or []
            for region in regions:
                pn = region.get("page_number") or region.get("pageNumber")
                if pn in focus_pages:
                    return True
            return False

        # Filter items
        filtered["pages"] = [p for p in ocr_data.get("pages", []) 
                           if (p.get("page_number") or p.get("pageNumber")) in focus_pages]
        
        filtered["paragraphs"] = [p for p in ocr_data.get("paragraphs", []) if is_on_focus_page(p)]
        filtered["tables"] = [t for t in ocr_data.get("tables", []) if is_on_focus_page(t)]
        
        # Reconstruct content from valid paragraphs
        filtered["content"] = "\n".join([p.get("content", "") for p in filtered["paragraphs"]])
        
        return filtered

    async def _unwrap_llm_extraction(self, ocr_data: Dict[str, Any], model: ExtractionModel, focus_pages: Optional[List[int]] = None) -> Dict[str, Any]:
        """ask LLM to extract data based on model fields"""

        # OPTIMIZATION: Filter payload to only relevant pages
        ocr_data_to_send = self._filter_ocr_data(ocr_data, focus_pages) if focus_pages else ocr_data.copy()



        # [Scenario Router] - FIRST STEP
        # Decide strategy immediately based on model configuration.
        use_beta = model.beta_features.get("use_optimized_prompt", False) if model.beta_features else False
        
        logger.info(f"[LLM] Dispatching to mode: {'BETA (LayoutParser)' if use_beta else 'GENERAL (Legacy)'}")

        if use_beta:
            # Check for Chunking Condition (e.g., > 3 pages OR massive text > 10k chars)
            page_count = len(ocr_data_to_send.get("pages", []))
            json_payload_len = len(json.dumps(ocr_data_to_send))
            
            CHUNK_PAGE_LIMIT = 3
            CHUNK_CHAR_LIMIT = 10000 # Approx 2.5k tokens
            
            if page_count > CHUNK_PAGE_LIMIT or json_payload_len > CHUNK_CHAR_LIMIT:
                logger.info(f"[Beta] Large Document ({page_count} pages, {json_payload_len} chars). Triggering Beta Chunking.")
                # Use smaller chunks (2 pages) to avoid output truncation
                return await self._extract_beta_chunked(model, ocr_data_to_send, page_count, chunk_size=2)
            
            return await self._extract_beta_mode(model, ocr_data_to_send, focus_pages)
        else:
            return await self._extract_general_mode(model, ocr_data_to_send, focus_pages)

    async def _extract_beta_chunked(self, model: ExtractionModel, ocr_data: Dict[str, Any], total_pages: int, chunk_size: int) -> Dict[str, Any]:
        """
        [Beta Chunking]
        Splits document into page groups, processes them in parallel using Beta Mode, and merges results.
        """
        chunks = []
        for i in range(0, total_pages, chunk_size):
            # focus_pages is 1-based index list
            chunk_pages = list(range(i + 1, min(i + chunk_size + 1, total_pages + 1)))
            chunks.append(chunk_pages)
            
        logger.info(f"[Beta Chunking] Created {len(chunks)} chunks: {chunks}")
        
        # Run in parallel
        tasks = []
        for chunk in chunks:
             # OPTIMIZATION: Create a mini-OCR payload for this chunk only
             # This ensures LayoutParser only processes these specific pages, preventing token overflow.
             chunk_ocr_data = self._filter_ocr_data(ocr_data, chunk)
             # Disable further chunking to prevent infinite recursion
             tasks.append(self._extract_beta_mode(model, chunk_ocr_data, focus_pages=None, allow_chunking=False))
             
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Merge Results
        merged_rows = []
        errors = []
        token_usage_total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        
        for idx, res in enumerate(results):
            if isinstance(res, Exception):
                logger.error(f"[Beta Chunking] Chunk {idx} failed: {res}")
                errors.append(str(res))
                continue
                
            # Merge rows
            rows = res.get("rows", [])
            # If standard Beta mode normalized it to _table_rows, capture that too if 'rows' missing
            if not rows and res.get("_table_rows"):
                rows = res.get("_table_rows")
                
            # Filter empty rows
            if rows:
                # Patch Page Numbers (Relative -> Absolute)
                # LayoutParser in the chunk thinks pages are 1..N.
                # We need to map them back to the real page numbers in 'chunks[idx]'.
                current_chunk_pages = chunks[idx] # e.g. [3, 4]
                
                patched_rows = []
                for row in rows:
                    new_row = row.copy()
                    # Check extraction metadata fields
                    for key, val in new_row.items():
                        if isinstance(val, dict) and "page_number" in val:
                            rel_page = val.get("page_number", 1)
                            # Map relative 1-based index to real page
                            # If rel_page is 1, it's current_chunk_pages[0]
                            if isinstance(rel_page, int) and 1 <= rel_page <= len(current_chunk_pages):
                                val["page_number"] = current_chunk_pages[rel_page - 1]
                                
                    # Also check row-level metadata if any (e.g. _page)
                    if "_page" in new_row:
                        rel_page = new_row["_page"]
                         if isinstance(rel_page, int) and 1 <= rel_page <= len(current_chunk_pages):
                                new_row["_page"] = current_chunk_pages[rel_page - 1]

                    patched_rows.append(new_row)
                    
                merged_rows.extend(patched_rows)
                
            # Accumulate Token Usage
            usage = res.get("_token_usage", {})
            if usage:
                token_usage_total["prompt_tokens"] += usage.get("prompt_tokens", 0)
                token_usage_total["completion_tokens"] += usage.get("completion_tokens", 0)
                token_usage_total["total_tokens"] += usage.get("total_tokens", 0)

        logger.info(f"[Beta Chunking] Merged {len(merged_rows)} rows from {len(results)} chunks.")
        
        return {
            "rows": merged_rows,
            "_table_rows": merged_rows,
            "_is_table": True, # Chunking always implies table/list output
            "_token_usage": token_usage_total,
            "_beta_chunking_debug": {"chunks": chunks, "errors": errors},
            # We don't merge parsed_content or ref_map for now as they are huge and mostly for debugging single-shot.
            # If needed, we could merge them, but it might blow up memory.
            "error": f"Chunk failures: {errors}" if errors else None
        }

    async def _extract_general_mode(self, model: ExtractionModel, ocr_data: Dict[str, Any], focus_pages: List[int] = None) -> Dict[str, Any]:
        """
        [General Mode] Legacy extraction using raw text and admin prompt.
        Target: Simple documents, key-value pairs.
        """
        json_payload = json.dumps(ocr_data, ensure_ascii=False)
        payload_len = len(json_payload)
        page_count = len(ocr_data.get("pages", []))
        
        # 1. Legacy Chunking Check
        if payload_len > settings.CHUNK_THRESHOLD_CHARS or page_count > 15:
            logger.info(f"[LLM-General] Payload > Threshold ({payload_len} chars). Triggering Legacy Chunking.")
            try:
                from app.services.chunked_extraction import extract_with_chunking
                
                # General Mode = Always use Legacy Chunking (model_info=None)
                merged_result, errors = await extract_with_chunking(
                    doc_intel_output=ocr_data,
                    model_fields=model.fields,
                    model_info=None, 
                    max_tokens_per_chunk=settings.LLM_CHUNK_MAX_TOKENS,
                    max_concurrent=8
                )

                if errors:
                    logger.warning(f"[LLM-General] Chunking errors: {errors}")

                # Merge structured result
                raw_tables = ocr_data.get("tables", [])
                merge_debug = merged_result.get("_merge_info", {})

                return {
                    "guide_extracted": {k: {"value": v.get("value"), "confidence": v.get("confidence", 0.0), "bbox": v.get("bbox"), "page_number": v.get("page_number")} for k, v in merged_result.items() if not k.startswith("_")},
                    "other_data": [{"type": "raw_tables", "tables": raw_tables}] if raw_tables else [],
                    "_chunked": True,
                    "_debug_chunking": merge_debug,
                    "_chunking_errors": errors if errors else None,
                    "raw_content": ocr_data.get("content", "")
                }
            except Exception as chunk_error:
                logger.error(f"[LLM-General] Legacy Chunking Failed: {chunk_error}")
                # Fallback to Single Shot? Or Fail?
                # Legacy behavior was fail if chunking fails.
                raise chunk_error

        # 2. Legacy Single Shot (Reference Admin Prompt)
        from app.services import prompt_service

        try:
            system_template = await prompt_service.get_prompt_content("extraction_system")
            if not system_template:
                logger.warning("[LLM] Admin prompt 'extraction_system' not found, using default.")
                system_template = prompt_service.DEFAULT_PROMPTS["extraction_system"]["content"]

            # 2. Prepare Variables
            field_descs = []
            for field in model.fields:
                desc = f"- {field.key} ({field.label})"
                if field.description: desc += f": {field.description}"
                if field.type: desc += f" [Type: {field.type}]"
                field_descs.append(desc)
            field_block = "\n".join(field_descs)

            rules_block = f"\nGLOBAL RULES:\n{model.global_rules}\n" if model.global_rules else ""
            focus_block = f"\nFOCUS ONLY ON PAGES: {focus_pages}" if focus_pages else ""

            # 3. Format Prompt
            formatted_system_prompt = system_template.replace("{ocr_data}", json_payload) \
                                                     .replace("{field_descriptions}", field_block) \
                                                     .replace("{global_rules}", rules_block) \
                                                     .replace("{focus_instruction}", focus_block)
            
            messages = [
                {"role": "system", "content": formatted_system_prompt},
                {"role": "user", "content": "Start extraction now."}
            ]
        except Exception as e:
            logger.error(f"[LLM] General Mode Prompt Error: {e}")
            raise e

        # 4. Call LLM
        return await self._call_llm(messages, ocr_data.get("content", ""))

    async def _extract_beta_mode(self, model: ExtractionModel, ocr_data: Dict[str, Any], focus_pages: List[int] = None) -> Dict[str, Any]:
        """
        [Beta Mode] Advanced extraction using LayoutParser + RefinerEngine.
        Target: Complex layouts, tables, heavy documents.
        """
        # 1. Layout Parsing (Structure-Aware Tagging)
        from app.services.layout_parser import LayoutParser
        parser = LayoutParser(ocr_data)
        tagged_text, ref_map = parser.parse(focus_pages=focus_pages)
        
        # 2. Refiner Prompt
        from app.services.refiner import RefinerEngine
        system_prompt = RefinerEngine.construct_prompt(model, language="ko")
        
        user_prompt = f"""
DOCUMENT DATA (Tagged Layout Format):
{tagged_text}

TASK: Extract fields based on system instructions.
Return valid JSON.
"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # 3. Call LLM
        result = await self._call_llm(messages, ocr_data.get("content", ""))
        
        # 4. Post-processing (Refiner/Parser specifics)
        # Store technical metadata for debugging
        result["_beta_parsed_content"] = tagged_text
        result["_beta_ref_map"] = ref_map
        
        # Normalization: Map 'rows' to 'guide_extracted' for Frontend Compatibility
        if "rows" in result:
             result["_is_table"] = True
             result["_table_rows"] = result["rows"]
             
             # If guide_extracted is missing/empty, try to populate from first row
             # This handles cases where Refiner uses Table Mode for Key-Value documents
             if not result.get("guide_extracted") and len(result["rows"]) > 0:
                 first_row = result["rows"][0]
                 converted_guide = {}
                 
                 # Refiner might return values directly, or maybe we can improve prompt to return tags?
                 # ideally prompt should return value. LayoutParser has value->bbox map.
                 
                 for key, val in first_row.items():
                     # Default (Missing)
                     bbox = None
                     page = 1
                     confidence = 0.9

                     # Attempt to find BBox via LayoutParser's ref_map logic
                     # We can use parser.find_coordinate_by_text(val)
                     if val and isinstance(val, str):
                         found_result = parser.find_coordinate_by_text(val)
                         if found_result:
                             bbox, page = found_result
                             # bbox is List[float], page is int

                     converted_guide[key] = {
                         "value": val,
                         "confidence": confidence,
                         "bbox": bbox, 
                         "page_number": page
                     }
                 result["guide_extracted"] = converted_guide
                 logger.info(f"[Beta] Converted 1st row to guide_extracted ({len(converted_guide)} fields) with BBox lookup")
             
        return result

    async def _call_llm(self, messages: List[Dict[str, str]], raw_content: str) -> Dict[str, Any]:
        """Shared LLM Caller"""
        logger.info(f"[LLM] Sending request to Azure OpenAI...")
        try:
            current_model_name = get_current_model()
            response = await self.azure_openai.chat.completions.create(
                model=current_model_name,
                messages=messages,
                temperature=settings.LLM_DEFAULT_TEMPERATURE,
                max_tokens=settings.LLM_DEFAULT_MAX_TOKENS,
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content or "{}"
            
            token_usage = None
            if response.usage:
                token_usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                }
                logger.info(f"[LLM-Token] Usage: {token_usage}")

            result = json.loads(content)
            result["_token_usage"] = token_usage
            if "raw_content" not in result:
                result["raw_content"] = raw_content
            return result
        except Exception as e:
            logger.error(f"[LLM] Call Failed: {e}")
            raise e

    def _validate_and_format(self, raw_data: Dict[str, Any], model: ExtractionModel, pages_info: List[Dict[str, Any]] = [], default_page: int = 1) -> Dict[str, Any]:
        """
        Strictly validates and formats data based on field types.
        AI provides the raw string, Code ensures it matches the Type.
        Adds confidence flags and normalizes bbox for frontend rendering.
        
        For TABLE mode: passes through _table_rows directly without field-by-field validation.
        """
        # TABLE MODE: standard logic
        # If strictly ONE row, we prefer falling through to standard Validation
        # to render as "Form View" in Frontend (matching General Mode).
        # Multi-row (2+) will keep using Table Mode.
        table_rows = raw_data.get("_table_rows", [])
        is_single_row = len(table_rows) == 1
        
        # Only treat as "Table Mode" (List return) if it is NOT a single row
        # This effectively toggles: 
        #   1 Row -> Form View (Dict)
        #   2+ Rows -> Table View (List)
        if raw_data.get("_is_table") and not is_single_row:
            logger.info(f"[Validation] TABLE MODE (Multi-Row): passing through {len(table_rows)} rows")
            
            # CRITICAL FIX: Even in Table Mode, we must parse nested JSON strings for complex fields
            # The LLM often returns "[{...}]" as a string for nested lists.
            for row in table_rows:
                for col_key, col_val in row.items():
                    # Check against model schema if possible, or just heuristic
                    # We can use model.fields to find type
                    field_def = next((f for f in model.fields if f.key == col_key), None)
                    if field_def and field_def.type in ("array", "list", "object", "table"):
                         if isinstance(col_val, str):
                            col_val = col_val.strip()
                            if (col_val.startswith("[") and col_val.endswith("]")) or \
                               (col_val.startswith("{") and col_val.endswith("}")):
                                try:
                                    row[col_key] = json.loads(col_val)
                                except:
                                    pass

            return {
                "guide_extracted": table_rows,
                "_is_table": True,
                "raw_tables": raw_data.get("raw_tables"),
                "_token_usage": raw_data.get("_token_usage"),
                "_beta_chunking_info": raw_data.get("_beta_chunking_info"),
                "_beta_pipeline_stages": raw_data.get("_beta_pipeline_stages"),
                "_beta_parsed_content": raw_data.get("_beta_parsed_content"),
                "_beta_ref_map": raw_data.get("_beta_ref_map"),
                "error": raw_data.get("error"),
            }

        guide_extracted = self._normalize_guide_extracted(
            raw_data.get("guide_extracted", {}), context="Validation"
        )

        validated_extracted = {}

        CONFIDENCE_THRESHOLD = settings.LLM_CONFIDENCE_THRESHOLD

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

            
            # --- SMART PAGE DISCOVERY ---------------------------------
            # If page_number is missing or ambiguous, try to find the text on the default page or surrounding pages.
            # -----------------------------------------------------------
            detected_page = page_number
            if not detected_page:
                 detected_page = default_page
                 # logger.debug(f"[SmartDiscovery] {key}: Page Missing, defaulting to {default_page}")

            snapped_bbox = None
            final_page_number = detected_page

            # Try to snap bbox using Exact Match first
            # We iterate pages_info to find 'words' array for the target page
            
            def search_page(p_num):
                # pages_info has snake_case keys from DocIntel
                p_data = next((p for p in pages_info if (p.get("page_number") or p.get("pageNumber", 0)) == p_num), None)
                if p_data and "words" in p_data:
                    return self._snap_bbox_to_words(str(value), bbox, p_data["words"])
                return None

            if value:
                # Attempt 1: Check intended page
                snapped_bbox = search_page(final_page_number)

                # Attempt 2: If not found, check ALL other pages (fallback)
                if not snapped_bbox and pages_info:
                      for p_info in pages_info:
                         p_num = p_info.get("page_number") or p_info.get("pageNumber")
                         if p_num == final_page_number: continue
                         
                         found_bbox = search_page(p_num)
                         if found_bbox:
                             snapped_bbox = found_bbox
                             final_page_number = p_num
                             logger.info(f"[SmartDiscovery] Value '{value}' for '{key}' found on Page {p_num} (originally thought {page_number})")
                             break
            
            page_number = final_page_number
            # -----------------------------------------------------------


            # Normalize BBox (convert generic coords to % of page)
            normalized_bbox = None
            if snapped_bbox:
                # Use page dims
                p_w, p_h = 100, 100
                if page_number and page_number in page_dims:
                    p_w, p_h = page_dims[page_number]
                
                normalized_bbox = self._normalize_bbox(snapped_bbox, p_w, p_h)
            elif bbox and isinstance(bbox, list) and len(bbox) == 4:
                # Trust LLM bbox if we couldn't snap it?
                # Maybe, but LLM bbox is usually raw pixels or normalized 0-1 depending on model.
                # Assuming simple pass-through if strict snapping failed.
                normalized_bbox = bbox
            

            # Type Validation & JSON Parsing for Complex Fields
            validation_status = "valid"
            
            # 1. Complex Types (Array/List/Object/Table) - Auto-Parse JSON strings
            if field.type in ("array", "list", "object", "table"):
                if isinstance(value, str):
                    value = value.strip()
                    # Only attempt if it looks like JSON
                    if (value.startswith("[") and value.endswith("]")) or \
                       (value.startswith("{") and value.endswith("}")):
                        try:
                            value = json.loads(value)
                            # logger.debug(f"[Validation] Auto-parsed JSON string for field '{key}'")
                        except json.JSONDecodeError:
                            validation_status = "error_json_format"
                            logger.warning(f"[Validation] Failed to parse JSON for field '{key}': {value[:50]}...")

            # 2. Simple Types
            elif field.type == "number":
                parsed = parse_number(value)
                if parsed is not None:
                    value = parsed
                else:
                    if value:
                        validation_status = "error_type_mismatch"
            elif field.type == "date":
                # Basic check, maybe enhance
                pass 
                if value and len(str(value)) < 6: # Heuristic
                    if value:
                        validation_status = "error_date_format"

            validated_extracted[key] = {
                "value": value,
                "original_value": item.get("value"), # Debug consistency
                "confidence": confidence,
                "bbox": normalized_bbox, # standard [x,y,w,h] or [x1,y1,x2,y2]? Frontend expects [x,y,w,h] usually for highlights? 
                                         # actually _normalize_bbox returns [x, y, w, h] % ?
                                         # Let's check _normalize_bbox implementation.
                                         # It returns [left, top, width, height] as percentages (0-100). Valid.
                "page_number": page_number,
                "validation_status": validation_status
            }

        # Initialize result container
        result = {
            "guide_extracted": validated_extracted,
            "other_data": raw_data.get("other_data", []),
            "raw_content": raw_data.get("raw_content", "")
        }

        # Preserve technical fields from Beta path
        if "_beta_parsed_content" in raw_data:
            result["_beta_parsed_content"] = raw_data["_beta_parsed_content"]
        if "_beta_ref_map" in raw_data:
            result["_beta_ref_map"] = raw_data["_beta_ref_map"]
        
        # Preserve chunking debug info
        if "_beta_chunking_info" in raw_data:
            result["_beta_chunking_info"] = raw_data["_beta_chunking_info"]
        if "_beta_pipeline_stages" in raw_data:
            result["_beta_pipeline_stages"] = raw_data["_beta_pipeline_stages"]
        
        # Pass token usage
        if "_token_usage" in raw_data:
            result["_token_usage"] = raw_data["_token_usage"]
            
        # Error propagation
        if "error" in raw_data:
            result["error"] = raw_data["error"]

        return result

    def _snap_bbox_to_words(self, value_str: str, rough_bbox: List[float], words: List[Dict]) -> Optional[List[float]]:
        """
        Attempts to find exact bounding box of value_str within the page words.
        1. Exact string match in words (sequence)
        2. Fuzzy match? (Keep simple for now)
        3. If rough_bbox provided, use it to narrow down search?
        
        For now: simple exact sequence match.
        """
        if not value_str: return None
        value_str = str(value_str).strip()
        if not value_str: return None

        # Clean words content
        page_text_sequence = []
        for w in words:
            page_text_sequence.append(w["content"])
        
        # Simple substring search? constructing full text from words may have spacing issues.
        # This is a complex problem. 
        # Strategy:
        # - Iterate words, check if `value_str` equals `word.content` (perfect match)
        # - Or if `value_str` is contained in `word.content`
        
        # Best effort: find single word match
        for w in words:
            if value_str == w["content"].strip():
                return w["polygon"]
        
        return None

    def _normalize_bbox(self, polygon: List[float], page_width: int, page_height: int) -> List[float]:
        """
        Convert polygon [x1,y1, x2,y2, x3,y3, x4,y4] to normalized [x, y, w, h] percentage
        """
        if not polygon or len(polygon) < 8:
            return None
            
        xs = polygon[0::2]
        ys = polygon[1::2]
        
        min_x = min(xs)
        min_y = min(ys)
        max_x = max(xs)
        max_y = max(ys)
        
        w = max_x - min_x
        h = max_y - min_y
        
        # Avoid div by zero
        if page_width == 0: page_width = 1
        if page_height == 0: page_height = 1
        
        return [
            (min_x / page_width) * 100,
            (min_y / page_height) * 100,
            (w / page_width) * 100,
            (h / page_height) * 100
        ]
        
    def _normalize_guide_extracted(self, extracted: Any, context: str = "") -> Dict[str, Any]:
        """Helper to safely ensure extracted data is a dictionary of objects"""
        if not isinstance(extracted, dict):
            # If standard list or garbage, return empty or wrap
            return {}
        return extracted


# Helper functions
def parse_number(s: Any) -> Optional[float]:
    if s is None: return None
    if isinstance(s, (int, float)): return s
    try:
        # Remove commas, currency symbols
        clean = str(s).replace(',', '').replace('$', '').replace('₩', '').strip()
        return float(clean)
    except:
        return None

# Singleton Instance
extraction_service = ExtractionService()
