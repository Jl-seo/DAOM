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
from app.services.extraction_utils import normalize_bbox, parse_number

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

    async def run_extraction_pipeline(self, file_content: bytes, model_id: str, filename: str = "", mime_type: str = "", barcode: Optional[str] = None) -> Dict[str, Any]:
        """
        Main entry point for extraction.
        1. Check Vision mode (skip OCR if enabled)
        2. OCR (Layout Analysis)
        3. Field Extraction (LLM)
        4. Post-processing/Validation
        """
        start_time = datetime.utcnow()
        logger.info(f"[Extraction] Starting pipeline for model {model_id}, file: {filename}")

        # 1. Get Model
        try:
            model = get_model_by_id(model_id)
        except Exception as e:
            logger.error(f"[Extraction] Model not found: {e}")
            return {"error": f"Model {model_id} not found"}

        # 1b. Vision Extraction Mode — skip OCR entirely
        use_vision = model.beta_features.get("use_vision_extraction", False) if model.beta_features else False
        if use_vision:
            logger.info("[Extraction] Route: VISION MODE (OCR skipped)")
            try:
                from app.services.extraction.vision_extraction import VisionExtractionPipeline
                vision_pipeline = VisionExtractionPipeline(self.azure_openai)
                extraction_result = await vision_pipeline.execute(model, file_content, filename, mime_type)
                
                # Check for DEX target and try to get barcode via DI Read if needed
                if not barcode and mime_type not in ["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/vnd.ms-excel", "text/csv"]:
                    target_field_key = next((f.key for f in model.fields if getattr(f, "is_dex_target", False)), None)
                    if target_field_key:
                        try:
                            from app.services.doc_intel import extract_with_strategy, AzureModelType
                            logger.info("[Extraction] Vision Mode: Auto-fetching barcode via DI Read model")
                            di_res = await extract_with_strategy(file_content, model_type=AzureModelType.READ, mime_type=mime_type, features=["barcodes"])
                            for page in di_res.get("pages", []):
                                barcodes = page.get("barcodes", [])
                                if barcodes:
                                    barcode = barcodes[0].get("value", "")
                                    if barcode:
                                        logger.info(f"[Extraction] Vision Mode: Auto-detected barcode from DI: {barcode}")
                                        break
                        except Exception as e:
                            logger.warning(f"[Extraction] Auto-barcode fetch failed in Vision Mode: {e}")

                # Convert to dict for _validate_and_format compatibility
                result_dict = {
                    "guide_extracted": extraction_result.guide_extracted,
                    "_token_usage": extraction_result.token_usage.dict(),
                    "error": extraction_result.error,
                    "raw_content": extraction_result.raw_content,
                    "raw_tables": [],
                    "pages": [],
                    "other_data": [],
                }
                if extraction_result.beta_metadata:
                    result_dict["_vision_metadata"] = extraction_result.beta_metadata
                
                final_result = self._validate_and_format(result_dict, model, [])
                duration = (datetime.utcnow() - start_time).total_seconds()
                final_result["_meta"] = {
                    "duration_seconds": duration,
                    "filename": filename,
                    "model_name": model.name,
                    "timestamp": start_time.isoformat(),
                    "pipeline_mode": "vision-extraction",
                }

                if barcode:
                    final_result = self._apply_dex_validation(final_result, model, barcode)

                return final_result
            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                logger.error(f"[Extraction] Vision extraction failed: {e}", exc_info=True)
                return {"error": f"Vision extraction failed: {str(e)}\n\nTraceback:\n{tb}"}

        # 2. Document Intelligence (OCR) or Excel Direct Markdown
        ocr_result = None
        is_excel_mode = False
        
        if mime_type in ["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/vnd.ms-excel", "text/csv"] or filename.lower().endswith(('.xlsx', '.xls', '.csv')):
            logger.info("[Extraction] Route: EXCEL DIRECT MARKDOWN (OCR skipped)")
            try:
                from app.services.extraction.excel_parser import ExcelParser
                ext = filename.lower().rsplit('.', 1)[-1] if '.' in filename else 'xlsx'
                if mime_type == "text/csv": ext = "csv"
                
                md_content = ExcelParser.from_bytes(file_content, ext)
                
                # Mock OCR structure for compatibility with downstream
                ocr_result = {
                    "content": md_content,
                    "pages": [{"page_number": 1, "width": 1000, "height": 1000}], # dummy page
                    "tables": [],
                    "paragraphs": [],
                    "styles": [],
                    "_is_direct_markdown": True
                }
                is_excel_mode = True
            except Exception as e:
                logger.error(f"[Extraction] Excel Direct Parser failed: {e}. Falling back to OCR.")
                # Fallback to OCR if parser fails for some reason
        
        if not ocr_result:
            try:
                from app.services.doc_intel import analyze_document_layout
                ocr_result = await analyze_document_layout(file_content, mime_type=mime_type)
            except Exception as e:
                logger.error(f"[Extraction] OCR failed: {e}")
                return {"error": f"OCR Analysis failed: {str(e)}"}
            
        # 2.5 Auto-extract Barcode from OCR if not manually provided
        if not barcode and not is_excel_mode and ocr_result and "pages" in ocr_result:
            for page in ocr_result.get("pages", []):
                barcodes = page.get("barcodes", [])
                if barcodes:
                    barcode = barcodes[0].get("value", "")
                    if barcode:
                        logger.info(f"[Extraction] Auto-detected barcode from Azure DI: {barcode}")
                        break

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

        # 5. DEX Integration (LLM vs LIS Check)
        if barcode:
            final_result = self._apply_dex_validation(final_result, model, barcode)

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
            # [Refactored Phase 7] Use BetaPipeline
            from app.services.extraction.beta_pipeline import BetaPipeline
            
            # Lazy init or singleton? Better to init once. 
            # For now, instantiate here to avoid circular imports in __init__ if any.
            # Actually, let's keep it simple.
            pipeline = BetaPipeline(self.azure_openai)
            
            # Execute Pipeline (Standardized Result)
            extraction_result = await pipeline.execute(model, ocr_data_to_send, focus_pages)
            
            # Convert to Dictionary for Compatibility with _validate_and_format
            # We map Standard Schema -> Legacy Dict Schema
            result_dict = {
                "guide_extracted": extraction_result.guide_extracted,
                "_token_usage": extraction_result.token_usage.dict(),
                "error": extraction_result.error,
                "raw_content": ocr_data_to_send.get("content", ""),
                "raw_tables": ocr_data_to_send.get("tables", []),
                "pages": ocr_data_to_send.get("pages", []),
                "other_data": extraction_result.other_data or []
            }
            
            # Legacy "is_table" logic removed.
            # Table data is now part of guide_extracted.
                
            # Metadata
            if extraction_result.beta_metadata:
                result_dict["_beta_parsed_content"] = extraction_result.beta_metadata.get("parsed_content")
                result_dict["_beta_ref_map"] = extraction_result.beta_metadata.get("ref_map")
                
            return result_dict

        else:
            return await self._extract_general_mode(model, ocr_data_to_send, focus_pages)

    async def _extract_general_mode(self, model: ExtractionModel, ocr_data: Dict[str, Any], focus_pages: List[int] = None) -> Dict[str, Any]:
        """
        [General Mode] Legacy extraction using raw text and admin prompt.
        Target: Simple documents, key-value pairs.
        """
        json_payload = json.dumps(ocr_data, ensure_ascii=False)
        payload_len = len(json_payload)

        # 1. Check Size -> Auto-Switch to Beta Pipeline (Chunking) if large.
        # This prevents "Single Shot" truncation for large documents even in Legacy Mode.
        page_count = len(ocr_data.get("pages", []))
        
        if payload_len > 40000 or page_count > 2:
             logger.warning(f"[General] Payload massive ({payload_len} chars, {page_count} pages). Auto-switching to BetaPipeline for Chunking.")
             
             from app.services.extraction.beta_pipeline import BetaPipeline
             pipeline = BetaPipeline(self.azure_openai)
             
             # Execute Pipeline (Standardized Result)
             extraction_result = await pipeline.execute(model, ocr_data, focus_pages)
             
             # Map Standard Schema -> Legacy Dict Schema
             result_dict = {
                "guide_extracted": extraction_result.guide_extracted,
                "_token_usage": extraction_result.token_usage.dict(),
                "error": extraction_result.error,
                "raw_content": ocr_data.get("content", ""),
                "raw_tables": ocr_data.get("tables", []),
                "pages": ocr_data.get("pages", []),
                "other_data": extraction_result.other_data or []
             }
             
             # Metadata
             if extraction_result.beta_metadata:
                result_dict["_beta_parsed_content"] = extraction_result.beta_metadata.get("parsed_content")
                result_dict["_beta_ref_map"] = extraction_result.beta_metadata.get("ref_map")
                
             return result_dict

        # Build prompt variables
        fields_info = []
        for f in model.fields:
            field_entry = {"key": f.key, "label": f.label, "type": f.type}
            if f.description:
                field_entry["description"] = f.description
            if f.rules:
                field_entry["rules"] = f.rules
            fields_info.append(field_entry)
        
        field_descriptions = json.dumps(fields_info, ensure_ascii=False, indent=2)
        
        global_rules_text = ""
        if model.global_rules:
            global_rules_text = f"\n\nGlobal Rules (apply to ALL fields):\n{model.global_rules}"
        
        ref_data_text = ""
        if model.reference_data:
            ref_json = json.dumps(model.reference_data, ensure_ascii=False, indent=2)
            ref_data_text = f"\n\nReference Data:\n{ref_json}"

        focus_instruction = ""
        if focus_pages:
            focus_instruction = f"\nFOCUS: Only extract from pages {focus_pages}."

        # Use centralized prompt from prompt_service (editable in admin settings)
        from app.services.prompt_service import get_prompt_content
        prompt_template = await get_prompt_content("extraction_system")
        
        if prompt_template:
            system_prompt = prompt_template.format(
                ocr_data="{see user message}",
                field_descriptions=field_descriptions,
                global_rules=global_rules_text,
                reference_data=ref_data_text,
                focus_instruction=focus_instruction
            )
        else:
            # Fallback if prompt_service unavailable
            system_prompt = f"""You are a document data extractor.
Extract data according to this schema:
{field_descriptions}
{global_rules_text}
{ref_data_text}

Return a JSON object with a key 'guide_extracted' containing the extracted fields.
For each field, follow its 'rules' if specified.
If a field is not found, return null.
"""
        
        user_prompt = f"Document Content:\n{ocr_data.get('content', '')}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # Call LLM
        llm_result = await self._call_llm(messages, ocr_data.get("content", ""))
        
        # Merge Original Data (Pass-through)
        # Verify if raw_content flows through
        if "raw_content" not in llm_result:
            llm_result["raw_content"] = ocr_data.get("content", "")
            
        if "pages" not in llm_result:
             llm_result["pages"] = ocr_data.get("pages", [])

        return llm_result

    # _extract_beta_chunked and _extract_beta_mode are now DEPRECATED and REMOVED.
    # Logic moved to app.services.extraction.beta_pipeline.BetaPipeline

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
        # Unified Validation Logic (No more Table Mode split)
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
            detected_page = page_number
            if not detected_page:
                    detected_page = default_page

            snapped_bbox = None
            final_page_number = detected_page

            def search_page(p_num):
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
                p_w, p_h = 100, 100
                if page_number and page_number in page_dims:
                    p_w, p_h = page_dims[page_number]
                
                normalized_bbox = normalize_bbox(snapped_bbox, p_w, p_h)
            elif bbox and isinstance(bbox, list):
                if len(bbox) >= 8:
                    # 8-element polygon from LayoutParser/Beta pipeline: [x1,y1,...x4,y4]
                    p_w, p_h = 100, 100
                    if page_number and page_number in page_dims:
                        p_w, p_h = page_dims[page_number]
                    normalized_bbox = normalize_bbox(bbox, p_w, p_h)
                elif len(bbox) == 4:
                    # Already normalized [x%, y%, w%, h%] (legacy path)
                    normalized_bbox = bbox
            

            # Type Validation & JSON Parsing for Complex Fields
            validation_status = "valid"
            
            # 1. Complex Types (Array/List/Object/Table) - Auto-Parse JSON strings
            if field.type in ("array", "list", "object", "table"):
                if isinstance(value, str):
                    value = value.strip()
                    if (value.startswith("[") and value.endswith("]")) or \
                        (value.startswith("{") and value.endswith("}")):
                        try:
                            value = json.loads(value)
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
                pass 
                if value and len(str(value)) < 6:
                    if value:
                        validation_status = "error_date_format"

            validated_extracted[key] = {
                "value": value,
                "original_value": item.get("value"),
                "confidence": confidence,
                "bbox": normalized_bbox,
                "page_number": page_number,
                "validation_status": validation_status
            }

        # Initialize result container (STANDARD MODE)
        result = {
            "guide_extracted": validated_extracted,
        }

        # --- Common metadata (always included regardless of mode) ---
        result["other_data"] = raw_data.get("other_data", [])
        result["pages"] = raw_data.get("pages", [])
        result["raw_content"] = raw_data.get("raw_content", "")
        result["raw_tables"] = raw_data.get("raw_tables", [])

        # Preserve technical fields from Beta path
        for key in ["_beta_parsed_content", "_beta_ref_map", "_beta_chunking_info", "_beta_pipeline_stages"]:
            if key in raw_data:
                result[key] = raw_data[key]
        
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


        
    def _normalize_guide_extracted(self, extracted: Any, context: str = "") -> Dict[str, Any]:
        """Helper to safely ensure extracted data is a dictionary of objects"""
        if not isinstance(extracted, dict):
            # If standard list or garbage, return empty or wrap
            return {}
        return extracted

    def _apply_dex_validation(self, final_result: Dict[str, Any], model: ExtractionModel, barcode: str) -> Dict[str, Any]:
        """Applies DEX validation logic by comparing LIS expected value against LLM extracted value."""
        target_field_key = next((f.key for f in model.fields if getattr(f, "is_dex_target", False)), None)
        
        if target_field_key:
            # Mock LIS lookup
            def mock_lis_lookup(code: str) -> str:
                last_char = code[-1] if code else "0"
                mock_db = {
                    "0": "김철수", "1": "홍길동", "2": "이영희", "3": "박지성", "4": "김연아",
                    "5": "유재석", "6": "강호동", "7": "신동엽", "8": "이수근", "9": "전현무"
                }
                return mock_db.get(last_char, "알수없음")
            
            lis_expected = mock_lis_lookup(barcode)
            
            # Retrieve extracted LLM value
            llm_extracted_item = final_result.get("guide_extracted", {}).get(target_field_key, {})
            # Unwrap {"value": "...", "confidence": ...}
            if isinstance(llm_extracted_item, dict):
                llm_value = llm_extracted_item.get("value", llm_extracted_item)
                if isinstance(llm_value, dict):
                    import json
                    llm_value = json.dumps(llm_value, ensure_ascii=False)
            else:
                llm_value = str(llm_extracted_item)
            
            # Compare
            import re
            clean_lis = re.sub(r'\s+', '', str(lis_expected)).strip()
            clean_llm = re.sub(r'\s+', '', str(llm_value or "")).strip()
            
            is_match = (clean_llm != "") and (clean_llm == clean_lis)
            
            # Append Metadata
            final_result["__dex_validation__"] = {
                "status": "PASS" if is_match else "FAIL",
                "barcode": barcode,
                "target_field_key": target_field_key,
                "lis_expected_value": lis_expected,
                "llm_extracted_value": llm_value
            }
            logger.info(f"[Extraction DEX] Validated barcode {barcode}. Expected: {lis_expected}, Got: {llm_value}. Status: {'PASS' if is_match else 'FAIL'}")
        
        return final_result


# Singleton Instance
extraction_service = ExtractionService()
