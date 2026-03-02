import asyncio
import hashlib
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.schemas.model import ExtractionModel
from app.services.extraction.core import ExtractionPipeline, ExtractionResult, TokenUsage
from app.services.layout_parser import LayoutParser
from app.services.refiner import RefinerEngine
from app.services.llm import call_llm_single, get_current_model
from app.core.config import settings
from openai import AsyncAzureOpenAI

logger = logging.getLogger(__name__)

# Module-level cache for Designer work orders (per model hash)
_work_order_cache: Dict[str, dict] = {}

class BetaPipeline(ExtractionPipeline):
    """
    Two-Phase LLM Extraction Strategy (Designer → Engineer):
    1. LayoutParser: Structure-aware tagging (markdown tables + ^C/^W/^P)
    2. Designer LLM: Schema → Work Order (cacheable per model)
    3. Engineer LLM: Work Order + Tagged Text → JSON with ref tags
    4. Post-Processor: ref_map → exact bbox lookup + uncertainty preservation
    """
    
    def __init__(self, azure_client: AsyncAzureOpenAI):
        self.azure_client = azure_client
        self.semaphore = asyncio.Semaphore(5)

    # ==================================================================
    # Main Entry Point
    # ==================================================================

    async def execute(self, model: ExtractionModel, ocr_data: Dict[str, Any], focus_pages: Optional[List[int]] = None) -> ExtractionResult:
        """
        Designer → Engineer Pipeline:
        1. LayoutParser (tagged text + ref_map)
        2. Designer LLM (work order from schema — cached)
        3. Engineer LLM (extraction with ref tags)
        4. Post-Processor (ref → bbox + uncertainty)
        """
        start_time = datetime.utcnow()
        
        # --- 1. Layout Parsing (or Direct Markdown Bypass) ---
        if ocr_data.get("_is_direct_markdown"):
             logger.info("[BetaPipeline] Bypassing LayoutParser (Direct Markdown provided)")
             tagged_text = ocr_data.get("content", "")
             ref_map = {} # References not used for direct Excel parsing since no BBox exists
        else:
             parser = LayoutParser(ocr_data)
             tagged_text, ref_map = parser.parse(focus_pages=focus_pages)
        
        content_len = len(tagged_text)
        page_count = len(ocr_data.get("pages", []))
        logger.info(f"[BetaPipeline] Analysis: pages={page_count}, content_len={content_len} chars")

        # --- 2. Designer LLM (Work Order — Cached) ---
        work_order = await self._run_designer(model)
        
        # --- 3. Engineer LLM (Extraction) ---
        is_excel = ocr_data.get("_is_direct_markdown", False)
        
        # Excel direct markdown leverages massive LLM context (128k tokens) to prevent severing multi-table context
        TEXT_CHUNK_SIZE = 150_000 if is_excel else 15_000
        # SINGLE_SHOT_CHAR_LIMIT must equal TEXT_CHUNK_SIZE for PDF to ensure proper chunking.
        # Previously 50,000 for PDF, which caused 15K-50K documents to bypass chunking and
        # trigger LLM lazy completion (outputting only ~20 rows of large tables).
        SINGLE_SHOT_CHAR_LIMIT = 300_000 if is_excel else TEXT_CHUNK_SIZE
        
        if content_len <= SINGLE_SHOT_CHAR_LIMIT:
            logger.info("[BetaPipeline] Route: Single-Shot Engineer")
            engineer_output = await self._run_engineer(work_order, tagged_text, model)
            
            # Fallback 1: Input too large
            if engineer_output.get("_truncated"):
                logger.warning("[BetaPipeline] Single-Shot truncated! Falling back to Chunked Engineer.")
                engineer_output = await self._run_engineer_chunked(work_order, tagged_text, TEXT_CHUNK_SIZE, model)
        else:
            logger.info("[BetaPipeline] Route: Chunked Engineer with Header Preservation")
            engineer_output = await self._run_engineer_chunked(work_order, tagged_text, TEXT_CHUNK_SIZE, model)
            
        # Fallback 2: Output schema too large (Massive Tables)
        if engineer_output.get("_truncated"):
            logger.warning("[BetaPipeline] Chunked Engineer ALSO truncated! Falling back to Schema Split (Per Table).")
            engineer_output = await self._run_engineer_per_table(work_order, tagged_text, TEXT_CHUNK_SIZE, model)
        
        # --- 4. Post-Process (ref → bbox) ---
        final_guide = RefinerEngine.post_process_with_ref(
            engineer_output, ref_map
        )
        
        # --- 4a. Dictionary Auto-Normalization ---
        if model.dictionaries:
            try:
                from app.services.extraction.index_engine import IndexEngine
                index_engine = IndexEngine()
                guide_data = final_guide.get("guide_extracted", {})
                final_guide["guide_extracted"] = await index_engine.normalize(
                    guide_data, model.dictionaries
                )
                logger.info(f"[BetaPipeline] Dictionary normalization applied for categories: {model.dictionaries}")
            except Exception as e:
                logger.warning(f"[BetaPipeline] Dictionary normalization skipped: {e}")
        
        # --- 4b. Transform Rules (Row Expansion) ---
        if model.transform_rules:
            try:
                from app.services.extraction.transform_engine import TransformEngine
                guide_data = final_guide.get("guide_extracted", {})
                final_guide["guide_extracted"] = TransformEngine.apply(
                    guide_data, model.transform_rules
                )
                logger.info(f"[BetaPipeline] Transform rules applied: {len(model.transform_rules)} rules")
            except Exception as e:
                logger.warning(f"[BetaPipeline] Transform rules skipped: {e}")
        
        # --- 4c. Extract unmapped_critical_info → other_data ---
        other_data = []
        processed_guide = final_guide.get("guide_extracted", {})
        unmapped = processed_guide.pop("unmapped_critical_info", None)
        if unmapped:
            # Handle both single value and list of values
            unmapped_items = unmapped if isinstance(unmapped, list) else [unmapped]
            for item in unmapped_items:
                if isinstance(item, dict):
                    val = item.get("value")
                    if val and val is not None:
                        other_data.append({
                            "column": "unmapped_critical_info",
                            "value": val,
                            "confidence": item.get("confidence", 0.5),
                            "bbox": item.get("bbox")
                        })
                elif isinstance(item, str) and item:
                    other_data.append({
                        "column": "unmapped_critical_info",
                        "value": item,
                        "confidence": 0.5
                    })
        
        # --- 5. Build Result ---
        total_usage = engineer_output.get("_token_usage", {})
        
        final_result = ExtractionResult(
            guide_extracted=processed_guide,
            raw_content=ocr_data.get("content", ""),
            raw_tables=ocr_data.get("tables", []),
            token_usage=TokenUsage(**total_usage) if total_usage else TokenUsage(),
            work_order=work_order,
            other_data=other_data,
            beta_metadata={
                "parsed_content": tagged_text,
                "ref_map": ref_map,
                "pipeline_mode": "designer-engineer"
            },
            model_name=model.name,
            duration_seconds=(datetime.utcnow() - start_time).total_seconds()
        )
        
        return final_result

    # ==================================================================
    # Phase ①: Designer LLM (Work Order Generation — Cached)
    # ==================================================================

    async def _run_designer(self, model: ExtractionModel) -> dict:
        """
        Generate a work order from the model schema.
        Uses module-level cache keyed by hash(model.id + fields + rules + ref_data).
        Includes validation: if Designer output is malformed, builds fallback from schema.
        """
        global _work_order_cache
        
        cache_key = self._compute_cache_key(model)
        
        if cache_key in _work_order_cache:
            logger.info(f"[BetaPipeline] Designer: Cache HIT for model '{model.name}'")
            return _work_order_cache[cache_key]
        
        logger.info(f"[BetaPipeline] Designer: Cache MISS — generating work order for '{model.name}'")
        
        system_prompt = RefinerEngine.construct_designer_prompt(model)
        user_prompt = "Generate the work order JSON. Output ONLY valid JSON, nothing else."
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        raw_result = await self.call_llm(messages)
        
        # Normalize: ensure { work_order: { ... } } structure
        if "work_order" in raw_result and isinstance(raw_result["work_order"], dict):
            work_order = raw_result
        elif isinstance(raw_result, dict) and "error" not in raw_result:
            work_order = {"work_order": raw_result}
        else:
            logger.warning(f"[BetaPipeline] Designer LLM returned error/empty, using fallback")
            work_order = self._build_fallback_work_order(model)
        
        # Validate: work_order must have common_fields or table_fields
        wo_inner = work_order.get("work_order", {})
        has_fields = wo_inner.get("common_fields") or wo_inner.get("table_fields")
        if not has_fields:
            logger.warning(f"[BetaPipeline] Designer output missing field definitions, using fallback")
            work_order = self._build_fallback_work_order(model)
        
        # Strip internal metadata before caching (prevents _token_usage leaking into Engineer prompt)
        work_order.pop("_token_usage", None)
        
        _work_order_cache[cache_key] = work_order
        logger.info(f"[BetaPipeline] Designer: Work order cached (key={cache_key[:16]}...)")
        
        return work_order

    @staticmethod
    def _build_fallback_work_order(model: ExtractionModel) -> dict:
        """Build a minimal work order directly from model schema when Designer fails."""
        TABLE_FIELD_TYPES = ('list', 'table', 'array')
        
        common_fields = []
        table_fields = []
        
        for f in model.fields:
            entry = {
                "key": f.key,
                "instruction": f"Extract '{f.label}' from the document.",
                "expected_format": f.type,
                "rules": []
            }
            if f.description:
                entry["instruction"] += f" Description: {f.description}"
            if f.rules:
                entry["rules"].append(f.rules)
            
            if f.type in TABLE_FIELD_TYPES:
                entry["columns"] = {}
                entry["rules"].append("Extract ALL rows.")
                table_fields.append(entry)
            else:
                common_fields.append(entry)
        
        return {
            "work_order": {
                "document_type": getattr(model, 'description', None) or model.name,
                "extraction_mode": "table" if table_fields else "data",
                "common_fields": common_fields,
                "table_fields": table_fields,
                "integrity_rules": [
                    "Copy values exactly as written. No conversion/calculation/translation.",
                    "Missing values must be null.",
                    "Extract in original language. Do NOT translate unless field rule says so."
                ]
            }
        }

    @staticmethod
    def _compute_cache_key(model: ExtractionModel) -> str:
        """Compute deterministic cache key from model schema."""
        fields_json = json.dumps(
            [{"key": f.key, "label": f.label, "description": f.description, 
              "rules": f.rules, "type": f.type} for f in model.fields],
            sort_keys=True, ensure_ascii=False
        )
        global_rules = model.global_rules or ""
        ref_data = json.dumps(model.reference_data or {}, sort_keys=True, ensure_ascii=False)
        
        raw = f"{model.id}|{fields_json}|{global_rules}|{ref_data}"
        return hashlib.sha256(raw.encode()).hexdigest()

    # ==================================================================
    # Phase ②: Engineer LLM (Value Extraction)
    # ==================================================================

    async def _run_engineer(self, work_order: dict, tagged_text: str, model: ExtractionModel = None) -> dict:
        """
        Single-shot Engineer extraction.
        Returns raw LLM output dict with guide_extracted + _token_usage.
        """
        ref_data = (model.reference_data if model else None) or None
        system_prompt = RefinerEngine.construct_engineer_prompt(work_order, reference_data=ref_data)
        user_prompt = f"DOCUMENT DATA (Tagged Layout Format):\n{tagged_text}\n\nExtract all fields. Return valid JSON."
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        raw_result = await self.call_llm(messages, is_table_model=True)
        return raw_result

    async def _run_engineer_chunked(self, work_order: dict, tagged_text: str, chunk_size: int, model: ExtractionModel = None) -> dict:
        """
        Chunked Engineer extraction with header preservation.
        Splits tagged text, injects table headers per chunk, merges results.
        """
        chunks = self._chunk_with_headers(tagged_text, chunk_size)
        logger.info(f"[BetaPipeline] Engineer Chunked: Created {len(chunks)} chunks")
        
        if not chunks:
            return {"guide_extracted": {}}
        
        ref_data = (model.reference_data if model else None) or None
        system_prompt = RefinerEngine.construct_engineer_prompt(work_order, reference_data=ref_data)
        
        async def process_chunk(chunk_text: str, chunk_idx: int) -> dict:
            user_prompt = (
                f"DOCUMENT DATA (Tagged Layout Format — Chunk {chunk_idx + 1}/{len(chunks)}):\n"
                f"{chunk_text}\n\n"
                f"Extract all fields from this section. Return valid JSON."
            )
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            async with self.semaphore:
                try:
                    return await self.call_llm(messages, is_table_model=True)
                except Exception as e:
                    logger.error(f"[BetaPipeline] Engineer Chunk {chunk_idx} failed: {e}")
                    return {"guide_extracted": {}, "error": str(e)}
        
        # Parallel execution
        tasks = [process_chunk(chunk, idx) for idx, chunk in enumerate(chunks)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Instead of simple Python dict merge, format valid chunks for the Phase 3 Aggregator LLM
        valid_chunks: Dict[str, dict] = {}
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        any_truncated = False
        
        for idx, res in enumerate(results):
            if isinstance(res, Exception):
                logger.error(f"[BetaPipeline] Chunk {idx} gather exception: {res}")
                continue
            
            if res.get("_truncated"):
                any_truncated = True
                
            # Accumulate token usage
            usage = res.get("_token_usage", {})
            for k in total_usage:
                total_usage[k] += usage.get(k, 0)
            
            # Save valid extraction for Aggregator
            extracted_data = res.get("guide_extracted")
            if extracted_data and isinstance(extracted_data, dict):
                valid_chunks[f"chunk_{idx}"] = extracted_data

        if not valid_chunks:
            logger.warning(f"[BetaPipeline] All {len(results)} chunks returned empty results. No data extracted.")
            return {"guide_extracted": {}, "_token_usage": total_usage, "_truncated": any_truncated}

        # Always run the Aggregator to safely merge list fields via append.
        # Previously, len(valid_chunks)==1 bypassed aggregation, silently dropping
        # data from other chunks that failed or returned empty.
        logger.info(f"[BetaPipeline] Aggregating {len(valid_chunks)} valid chunks (out of {len(results)} total).")

        # If >1 chunks, run the Aggregator LLM (Phase 3)
        agg_result = await self._run_aggregator(work_order, valid_chunks)
        
        # Accumulate Aggregator token usage
        agg_usage = agg_result.get("_token_usage", {})
        for k in total_usage:
            total_usage[k] += agg_usage.get(k, 0)

        return {
            "guide_extracted": agg_result.get("guide_extracted", {}),
            "_token_usage": total_usage,
            "_truncated": any_truncated,
            "logs": agg_result.get("logs", []) # Preserve the thought_process
        }

    async def _run_aggregator(self, work_order: dict, chunks_payload: Dict[str, dict]) -> dict:
        """
        Phase ③: Aggregator.
        Takes multiple chunked Engineer outputs and merges them using Python, keeping refs intact.
        Bypasses LLM aggregation completely to prevent massive table truncation due to completion token limits.
        """
        logger.info(f"[BetaPipeline] Aggregator: Deterministically merging {len(chunks_payload)} chunks in Python.")
        return self._run_aggregator_python_fallback(chunks_payload)

    def _run_aggregator_python_fallback(self, chunks_payload: Dict[str, dict]) -> dict:
        """
        Fail-Safe Fallback: Simple deterministic exact-merge logic.
        Append rows and keep the first non-null common field.
        """
        merged_guide = {}
        seen_rows = {}  # field_key -> Set[row_hash]
        
        for _chunk_id, guide_extracted in chunks_payload.items():
            for key, val in guide_extracted.items():
                if isinstance(val, list):
                    # Table field — append rows with dedup
                    if key not in merged_guide:
                        merged_guide[key] = []
                        seen_rows[key] = set()
                    
                    for row in val:
                        if not isinstance(row, dict):
                            continue
                        row_hash = json.dumps(row, sort_keys=True, ensure_ascii=False)
                        if row_hash not in seen_rows[key]:
                            seen_rows[key].add(row_hash)
                            merged_guide[key].append(row)
                else:
                    # Common field — first-non-null: keep first real value
                    if key not in merged_guide:
                        merged_guide[key] = val
                    elif isinstance(val, dict) and val.get("value") is not None:
                        existing = merged_guide[key]
                        if isinstance(existing, dict) and existing.get("value") is None:
                            merged_guide[key] = val
                            
        return {
            "guide_extracted": merged_guide,
            "_token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "logs": [{"step": "Aggregator Analysis", "message": "FAILSAFE TRIGGERED. Used Python Deterministic Merge."}]
        }

    async def _run_engineer_per_table(self, work_order: dict, tagged_text: str, chunk_size: int, model: ExtractionModel = None) -> dict:
        """
        [Schema Split Fallback]
        If chunked extraction still hits completion token limits due to massive tables,
        we split the schema (work_order) and extract each table INDEPENDENTLY.
        """
        table_fields = work_order.get("table_fields", [])
        common_fields = work_order.get("common_fields", [])
        
        logger.warning(f"[BetaPipeline] Falling back to Schema Split (Per-Table). Found {len(table_fields)} tables.")
        
        if not table_fields:
            # If there are no tables but it still truncated, just return what we have (rare).
            return await self._run_engineer_chunked(work_order, tagged_text, chunk_size, model)
            
        merged_guide = {}
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        any_truncated = False
        all_logs = []
        
        # We need to extract common fields once, and tables separately.
        # Create sub-work orders
        sub_orders = []
        
        # 1. Common Fields Only (if any exist)
        if common_fields:
            sub_orders.append({
                **work_order,
                "table_fields": [],  # Exclude tables
                "extraction_mode": "data"
            })
            
        # 2. Each Table Separately
        for t_field in table_fields:
            sub_orders.append({
                **work_order,
                "common_fields": [], # Exclude common
                "table_fields": [t_field], # ONLY this table
                "extraction_mode": "table"
            })
            
        # Process each sub-order sequentially or via gather (gather is faster)
        # We will use Chunked extraction under the hood for EACH sub-order to handle input limits too!
        async def process_sub_order(sub_wo):
            logger.info(f"[BetaPipeline] Schema Split: Extracting {sub_wo['extraction_mode']} payload")
            return await self._run_engineer_chunked(sub_wo, tagged_text, chunk_size, model)
            
        tasks = [process_sub_order(wo) for wo in sub_orders]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for res in results:
            if isinstance(res, Exception):
                logger.error(f"[BetaPipeline] Schema Split gather exception: {res}")
                continue
            
            if res.get("_truncated"):
                # If even a single table extraction truncates, we flag it (though we can't split further)
                any_truncated = True
                
            # Accumulate token usage
            usage = res.get("_token_usage", {})
            for k in total_usage:
                total_usage[k] += usage.get(k, 0)
                
            # Accumulate logs from chunked Engineer/Aggregator
            if "logs" in res:
                all_logs.extend(res["logs"])
                
            # Merge extracted data
            for key, val in res.get("guide_extracted", {}).items():
                 merged_guide[key] = val
                 
        return {
            "guide_extracted": merged_guide,
            "_token_usage": total_usage,
            "_truncated": any_truncated,
            "logs": all_logs
        }

    @staticmethod
    def _chunk_with_headers(tagged_text: str, chunk_size: int) -> List[str]:
        """
        Split tagged text into chunks with markdown table header preservation.
        When a chunk boundary falls inside a table, the header row + separator
        are injected at the start of each new chunk.
        """
        lines = tagged_text.split("\n")
        
        # Detect markdown table headers: | ... | followed by |---|
        table_headers: Dict[int, tuple] = {}  # line_idx -> (header_row, separator_row)
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("|") and i + 1 < len(lines):
                next_stripped = lines[i + 1].strip()
                if next_stripped.startswith("|") and "---" in next_stripped:
                    table_headers[i] = (line, lines[i + 1])
        
        chunks = []
        current_chunk: List[str] = []
        current_len = 0
        active_header: Optional[tuple] = None
        
        for i, line in enumerate(lines):
            # Track table context
            if i in table_headers:
                active_header = table_headers[i]
            elif not line.strip().startswith("|"):
                active_header = None
            
            # Since we split by \n, we must add it back to accurately track length and content
            line_with_newline = line + "\n"
            line_len = len(line_with_newline)
            
            if current_len + line_len > chunk_size and current_chunk:
                # Flush current chunk
                chunks.append("".join(current_chunk))
                current_chunk = []
                current_len = 0
                
                # If inside a table, inject header
                if active_header:
                    current_chunk.append(active_header[0] + "\n")  # header row
                    current_chunk.append(active_header[1] + "\n")  # separator
                    current_len += len(active_header[0]) + len(active_header[1]) + 2
            
            current_chunk.append(line_with_newline)
            current_len += line_len
        
        if current_chunk:
            chunks.append("".join(current_chunk))
        
        return chunks

    # ==================================================================
    # Legacy Methods (Backward Compatibility)
    # ==================================================================

    async def _extract_segment(self, model: ExtractionModel, text_segment: str, ocr_data: Dict, ref_map: Dict, mode: str) -> ExtractionResult:
        """[LEGACY] Helper to run a single LLM call for a text segment with specific mode."""
        system_prompt = RefinerEngine.construct_prompt(model, language="ko", mode=mode)
        user_prompt = f"DOCUMENT DATA (Tagged Layout Format):\n{text_segment}\n\nTASK: Extract fields based on system instructions.\nReturn valid JSON."
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        raw_result = await self.call_llm(messages)
        return self._normalize_output(raw_result, ocr_data, ref_map, text_segment)

    def _merge_results(self, common: ExtractionResult, table: ExtractionResult) -> ExtractionResult:
        """[LEGACY] Merge Common and Table results into a single Dict."""
        merged = ExtractionResult()
        merged.guide_extracted.update(common.guide_extracted)
        merged.guide_extracted.update(table.guide_extracted)
        merged.token_usage.prompt_tokens = common.token_usage.prompt_tokens + table.token_usage.prompt_tokens
        merged.token_usage.completion_tokens = common.token_usage.completion_tokens + table.token_usage.completion_tokens
        merged.token_usage.total_tokens = common.token_usage.total_tokens + table.token_usage.total_tokens
        return merged

    async def _extract_table_chunked(self, model: ExtractionModel, tagged_text: str, ocr_data: Dict[str, Any], ref_map: Dict, chunk_size: int) -> ExtractionResult:
        """
        Stage 2 (Large Content): Extract TABLE data from chunks.
        Supports multi-sheet Excel files via `_excel_sheets` to prevent cross-sheet header contamination.
        """
        table_prompt = RefinerEngine.construct_prompt(model, language="ko", mode="table")
        
        # 1. Prepare Target Sheets / Texts
        target_sections = []
        if "_excel_sheets" in ocr_data and isinstance(ocr_data["_excel_sheets"], list):
            for sheet in ocr_data["_excel_sheets"]:
                target_sections.append({
                    "name": sheet.get("sheet_name", "Unknown Sheet"),
                    "content": sheet.get("content", "")
                })
        else:
            # Standard PDF/Image routing
            target_sections.append({
                "name": "Document",
                "content": tagged_text
            })

        # 2. Build Chunks Per Section
        all_chunk_tasks = []
        
        for section in target_sections:
            content = section["content"]
            if not content.strip():
                continue
                
            lines = content.split("\n")
            chunks = []
            current_chunk_lines = []
            current_chunk_len = 0
            
            for line in lines:
                line_len = len(line) + 1  # +1 for newline
                if current_chunk_len + line_len > chunk_size and current_chunk_lines:
                    chunks.append("\n".join(current_chunk_lines))
                    current_chunk_lines = []
                    current_chunk_len = 0
                
                current_chunk_lines.append(line)
                current_chunk_len += line_len
            
            if current_chunk_lines:
                chunks.append("\n".join(current_chunk_lines))
                
            # Header context STRICTLY isolated to this specific sheet/section
            header_context = content[:1500]
            
            # Create process task closure for this specific chunk
            for idx, chunk_text in enumerate(chunks):
                all_chunk_tasks.append(
                    self._process_table_chunk_task(
                        chunk_text, idx, header_context, section["name"], table_prompt, ocr_data, ref_map
                    )
                )

        if not all_chunk_tasks:
            return ExtractionResult()
            
        logger.info(f"[BetaPipeline] Table Chunking: Created {len(all_chunk_tasks)} tasks across {len(target_sections)} sections")
        
        # 3. Parallel Execution
        results = await asyncio.gather(*all_chunk_tasks, return_exceptions=True)
        
        # 4. Merge Results (Field-aware Deduplication)
        merged_result = ExtractionResult()
        merged_guide = {} # Key -> List[Row]
        seen_rows = {}    # Key -> Set(row_hash)
        
        for res in results:
            if isinstance(res, Exception):
                continue
            
            # Token Usage
            merged_result.token_usage.prompt_tokens += res.token_usage.prompt_tokens
            merged_result.token_usage.completion_tokens += res.token_usage.completion_tokens
            merged_result.token_usage.total_tokens += res.token_usage.total_tokens
                        
            # Merge Lists
            if res.guide_extracted:
                for key, val in res.guide_extracted.items():
                    if isinstance(val, list):
                        if key not in merged_guide:
                            merged_guide[key] = []
                            seen_rows[key] = set()
                        
                        for row in val:
                            if not isinstance(row, dict): continue
                            
                            row_hash = json.dumps(row, sort_keys=True, ensure_ascii=False)
                            if row_hash not in seen_rows[key]:
                                seen_rows[key].add(row_hash)
                                merged_guide[key].append(row)

        merged_result.guide_extracted = self._normalize_column_keys(merged_guide)
        return merged_result

    async def _process_table_chunk_task(self, chunk_text: str, chunk_idx: int, header_context: str, section_name: str, table_prompt: str, ocr_data: Dict, ref_map: Dict) -> ExtractionResult:
        """Helper to process a single chunk safely."""
        final_chunk = chunk_text
        if chunk_idx > 0:
            final_chunk = f"--- [SHEET/SECTION HEADER: {section_name}] ---\n{header_context}\n... [Header Context End] ...\n{chunk_text}"
        
        user_prompt = (
            f"DOCUMENT DATA (Tagged Layout Format):\n{final_chunk}\n\n"
            f"TASK: Extract table rows from this section of the document.\n"
            f"Return valid JSON."
        )
        
        messages = [
            {"role": "system", "content": table_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        async with self.semaphore:
            try:
                raw_result = await self.call_llm(messages)
                return self._normalize_output(raw_result, ocr_data, ref_map, chunk_text)
            except Exception as e:
                logger.error(f"[BetaPipeline] Table Chunk {chunk_idx} in {section_name} failed: {e}")
                res = ExtractionResult()
                res.error = str(e)
                return res

    def _normalize_column_keys(self, merged_guide: dict) -> dict:
        """
        Normalize column keys across chunks to prevent duplicates from
        case/format differences (e.g. 'Charge_Type' vs 'charge_type').
        Uses the first chunk's keys as canonical reference.
        """
        for field_key, rows in merged_guide.items():
            if not isinstance(rows, list) or not rows:
                continue
            
            # Use first row's keys as canonical
            canonical_keys = list(rows[0].keys())
            
            def _strip(s: str) -> str:
                return s.lower().replace("_", "").replace("-", "").replace(" ", "")
            
            canonical_map = {_strip(k): k for k in canonical_keys}
            
            normalized_rows = []
            for row in rows:
                if not isinstance(row, dict):
                    normalized_rows.append(row)
                    continue
                new_row = {}
                for k, v in row.items():
                    norm_k = _strip(k)
                    new_row[canonical_map.get(norm_k, k)] = v
                normalized_rows.append(new_row)
            
            merged_guide[field_key] = normalized_rows
        
        return merged_guide



    async def _execute_chunked(self, model: ExtractionModel, ocr_data: Dict[str, Any], total_pages: int) -> ExtractionResult:
        # Chunking Config
        CHUNK_SIZE = 1
        OVERLAP = 0 # No overlap needed for single page chunks unless specifically requested for cross-page tables.
        # Actually, let's keep overlap logic but default to CHUNK_SIZE=1.
        # If CHUNK_SIZE=1 and OVERLAP=1, we get [1], [2], [3]... (no overlap)?
        # Wait, if step = 1-1 = 0, steps stop.
        # Let's use CHUNK_SIZE=1, OVERLAP=0 for safety first.
        # Or better: CHUNK_SIZE=1. Overlap logic is complex with size 1.
        # [SAFE OPTIMIZATION]
        # Chunk Size = 2 + Overlap = 1: Preserves table context across pages.
        # Semaphore = 5: High parallelism.
        CHUNK_SIZE = 2
        OVERLAP = 1 
        
        chunks = []
        # Create overlapping chunks: [1,2], [2,3], [3,4]...
        # Step = Chunk - Overlap = 2 - 1 = 1
        step = CHUNK_SIZE - OVERLAP
        if step < 1: step = 1
        
        for i in range(0, total_pages, step):
            # focus_pages is 1-based
            start_page = i + 1
            end_page = min(i + CHUNK_SIZE, total_pages)
            
            # Avoid single-page tail if possible, merge into previous?
            # Actually strict sliding window is fine.
            if start_page > total_pages: break
             
            chunk_pages = list(range(start_page, end_page + 1))
            
            # Deduplicate chunks (e.g. if last step creates subset)
            if chunks and set(chunk_pages).issubset(set(chunks[-1])):
                continue
                
            chunks.append(chunk_pages)

        logger.info(f"[BetaPipeline] Created {len(chunks)} chunks with overlap: {chunks}")
        
        # Parallel Execution with Semaphore
        tasks = []
        for chunk in chunks:
            tasks.append(self._process_chunk_safe(model, ocr_data, chunk))
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Merge Results
        merged_result = ExtractionResult()
        merged_rows = []
        seen_keys = set() # For deduplication
        
        for res in results:
            if isinstance(res, Exception):
                logger.error(f"[BetaPipeline] Chunk failed: {res}")
                continue
            
            # Accumulate Tokens
            merged_result.token_usage.prompt_tokens += res.token_usage.prompt_tokens
            merged_result.token_usage.completion_tokens += res.token_usage.completion_tokens
            merged_result.token_usage.total_tokens += res.token_usage.total_tokens
            
            # Merge Rows (Deduplication Strategy needed)
            # Simple Strategy: If row content is identical, skip.
            # Robust Strategy: If Primary Key matches, skip.
            # For now: Append all, let frontend handle or use simple JSON hash.
            
            current_rows = res.table_rows or [] # Unified schema uses table_rows
            if not current_rows and res.guide_extracted:
                 # Flatten single object to list if it looks like a row
                 current_rows = [res.guide_extracted]
            
            for row in current_rows:
                row_hash = json.dumps(row, sort_keys=True)
                if row_hash not in seen_keys:
                    seen_keys.add(row_hash)
                    
                    # Patch Page Numbers
                    # (Simplified: trusting LayoutParser's relative mapping? No, we need absolute patching)
                    # For now, let's assume `_process_chunk_safe` returns patched rows?
                    # Or patch here?
                    # Let's rely on standard logic - pages might be re-indexed.
                    # We should implement patching in _process_chunk_safe ideally.
                    
                    merged_rows.append(row)
        
        merged_result.table_rows = merged_rows
        merged_result.is_table = True
        
        # Merge Metadata (Parsed Content for Debug View & RefMap)
        all_parsed_text = []
        all_ref_map = {}
        for res in results:
            if isinstance(res, Exception): continue
            if res.beta_metadata:
                text = res.beta_metadata.get("parsed_content", "")
                if text: all_parsed_text.append(text)
                ref_map = res.beta_metadata.get("ref_map", {})
                if ref_map: all_ref_map.update(ref_map)
        
        merged_result.beta_metadata = {
            "parsed_content": "\n... [Chunk Split] ...\n".join(all_parsed_text),
            "ref_map": all_ref_map
        }

        return merged_result

    async def _process_chunk_safe(self, model: ExtractionModel, ocr_data: Dict[str, Any], chunk_pages: List[int]) -> ExtractionResult:
        """Wrapper to use Semaphore and filter OCR"""
        async with self.semaphore:
            # Filter OCR
            chunk_ocr = self._filter_ocr_data(ocr_data, chunk_pages)
            
            # Execute Single Shot (LayoutParser inside sees 1..N pages)
            try:
                result = await self._execute_single_shot(model, chunk_ocr, focus_pages=None)
            except Exception as e:
                # [ADAPTIVE CHUNKING ALERT]
                # If a chunk fails (esp. JSONDecodeError via Unterminated string == Token Limit),
                # and chunk size > 1, we must SPLIT THE CHUNK and retry.
                if len(chunk_pages) > 1:
                    logger.warning(f"[BetaPipeline] Chunk {chunk_pages} failed: {e}. Splitting into sub-chunks...")
                    mid = len(chunk_pages) // 2
                    left_pages = chunk_pages[:mid]
                    right_pages = chunk_pages[mid:]
                    
                    # Recursive call
                    left_res, right_res = await asyncio.gather(
                        self._process_chunk_safe(model, ocr_data, left_pages),
                        self._process_chunk_safe(model, ocr_data, right_pages)
                    )
                    
                    # Merge Results manually (simplified merge of two ExtractionResults)
                    merged = ExtractionResult()
                    merged.table_rows = left_res.table_rows + right_res.table_rows
                    merged.is_table = True
                    merged.token_usage.prompt_tokens = left_res.token_usage.prompt_tokens + right_res.token_usage.prompt_tokens
                    merged.token_usage.completion_tokens = left_res.token_usage.completion_tokens + right_res.token_usage.completion_tokens
                    merged.token_usage.total_tokens = left_res.token_usage.total_tokens + right_res.token_usage.total_tokens
                    # Guide extracted? Take first or merge? Usually guide is global.
                    # If both have it, take whichever has higher confidence or non-empty.
                    merged.guide_extracted = left_res.guide_extracted or right_res.guide_extracted
                    
                    # Metadata merge (complex but we just need parsed content for debug)
                    merged.beta_metadata = {
                        "parsed_content": (left_res.beta_metadata.get("parsed_content", "") if left_res.beta_metadata else "") + 
                                          "\n" + 
                                          (right_res.beta_metadata.get("parsed_content", "") if right_res.beta_metadata else ""),
                        # Naive merge of ref_map: simplest way is update
                        "ref_map": {**(left_res.beta_metadata.get("ref_map", {}) if left_res.beta_metadata else {}),
                                    **(right_res.beta_metadata.get("ref_map", {}) if right_res.beta_metadata else {})}
                    }
                    
                    return merged
                else:
                    # Single page failure: Cannot split further.
                    # This happens if 1 page > 16k tokens output or critical error.
                    logger.error(f"[BetaPipeline] Single-Page Chunk {chunk_pages} FAILED irrecoverably: {e}")
                    # Return error result object instead of crashing whole pipeline
                    err_res = ExtractionResult()
                    err_res.error = str(e)
                    return err_res

            # Patch Page Numbers
            # LayoutParser relative 1..N -> Absolute chunk_pages
            self._patch_page_numbers(result, chunk_pages)
            
            return result

    def _filter_ocr_data(self, ocr_data: Dict[str, Any], focus_pages: List[int]) -> Dict[str, Any]:
        """Specific filter for Beta Pipeline (same logic as service)"""
        if not focus_pages: return ocr_data.copy()
        
        filtered = {
            "content": "",
            "pages": [],
            "paragraphs": [],
            "tables": [],
            "styles": ocr_data.get("styles", [])
        }
        
        def is_on_focus_page(item):
            regions = item.get("bounding_regions") or item.get("boundingRegions") or []
            for region in regions:
                pn = region.get("page_number") or region.get("pageNumber")
                if pn in focus_pages: return True
            return False

        filtered["pages"] = [p for p in ocr_data.get("pages", []) 
                           if (p.get("page_number") or p.get("pageNumber")) in focus_pages]
        
        filtered["paragraphs"] = [p for p in ocr_data.get("paragraphs", []) if is_on_focus_page(p)]
        filtered["tables"] = [t for t in ocr_data.get("tables", []) if is_on_focus_page(t)]
        
        filtered["content"] = "\n".join([p.get("content", "") for p in filtered["paragraphs"]])
        return filtered

    def _patch_page_numbers(self, result: ExtractionResult, chunk_pages: List[int]):
        """
        Maps relative page numbers (1-based index in chunk) to absolute page numbers.
        Example: Chunk=[5,6], Result says Page 1 -> Mapped to Page 5.
        """
        def map_page(rel_page):
            if isinstance(rel_page, int) and 1 <= rel_page <= len(chunk_pages):
                return chunk_pages[rel_page - 1]
            return rel_page # Fallback

        # 1. Standard Fields
        for key, val in result.guide_extracted.items():
            if isinstance(val, dict) and "page_number" in val:
                val["page_number"] = map_page(val["page_number"])
                
        # 2. Table Rows
        for row in result.table_rows:
            # Row-level metadata
            if "_page" in row:
                row["_page"] = map_page(row["_page"])
                
            # Cell-level metadata (if any)
            for k, v in row.items():
                if isinstance(v, dict) and "page_number" in v:
                     v["page_number"] = map_page(v["page_number"])

        # 3. Ref Map (Metadata)
        if result.beta_metadata and "ref_map" in result.beta_metadata:
             for k, v in result.beta_metadata["ref_map"].items():
                 if "page_number" in v:
                     v["page_number"] = map_page(v["page_number"])

    def _normalize_output(self, raw_llm: Dict[str, Any], ocr_data: Dict, ref_map: Dict, tagged_text: str) -> ExtractionResult:
        """Convert LLM JSON to Standard ExtractionResult (Unified Dict Format)"""
        res = ExtractionResult()
        
        extracted = raw_llm.get("guide_extracted", {})
        
        # Legacy/Fallback: "rows" key -> wrap in _table_data or first list field if possible
        # [DEPRECATED] This path is no longer triggered with unified TABLE MODE prompt.
        # Kept for backward compatibility with any external callers.
        if "rows" in raw_llm:
            rows = raw_llm["rows"]
            if isinstance(rows, dict):
                # Convert dict-of-rows to list-of-rows
                try:
                    sorted_keys = sorted(rows.keys(), key=lambda x: int(x) if str(x).isdigit() else x)
                    rows = [rows[k] for k in sorted_keys]
                except:
                    rows = list(rows.values())
            
            # If guide_extracted is empty, put rows in a generic field
            # Ideally we should know the field name, but for now specific field key is better
            extracted["_legacy_rows"] = rows

        # Clean up {value: list} wrapper (LLM sometimes wraps table fields in text-field format)
        # Also clean up {value: val} for text fields if needed, but usually we keep confidence.
        # Strict schema requires:
        # - Text Field: {value: "...", confidence: 0.9}
        # - Table Field: [{...}, {...}] (List of Rows)
        
        cleaned_extracted = {}
        for k, v in extracted.items():
            # Case 1: Already a list -> Keep it (Table Field)
            if isinstance(v, list):
                # But check if it's a list containing a single scalar object mistakenly generated by LLM
                if len(v) == 1 and isinstance(v[0], dict) and "value" in v[0] and "confidence" in v[0] and len(v[0].keys()) <= 5:
                    # Unwrap the mistakenly array-wrapped scalar
                    cleaned_extracted[k] = v[0]
                else:
                    cleaned_extracted[k] = v
                continue
                
            # Case 2: Dict wrapper
            if isinstance(v, dict):
                # Check if it wraps a list: {"value": [...]}
                if "value" in v and isinstance(v["value"], list):
                     list_val = v["value"]
                     # Unwrap mistakenly array-wrapped scalar inside 'value'
                     if len(list_val) == 1 and isinstance(list_val[0], dict) and "value" in list_val[0] and "confidence" in list_val[0] and len(list_val[0].keys()) <= 5:
                         cleaned_extracted[k] = list_val[0]
                     else:
                         cleaned_extracted[k] = list_val
                else:
                     # Text field -> Keep as is
                     cleaned_extracted[k] = v
            else:
                # Direct value -> Wrap for consistency? or Keep?
                # Service layer expects structure, but let's keep as is for legacy compat
                cleaned_extracted[k] = v
                
        res.guide_extracted = cleaned_extracted
        
        # Token Usage
        usage = raw_llm.get("_token_usage", {})
        res.token_usage = TokenUsage(**usage) if usage else TokenUsage()
        
        # Metadata
        res.beta_metadata = {
            "ref_map": ref_map,
            "parsed_content": tagged_text
        }
        
        return res

    async def call_llm(self, messages, is_table_model: bool = False):
        """Direct LLM Call with table-aware max_tokens"""
        current_model_name = get_current_model()
        # Table models need more output tokens for many rows
        raw_max = settings.LLM_TABLE_MAX_TOKENS if is_table_model else settings.LLM_DEFAULT_MAX_TOKENS
        max_tokens = min(raw_max, 32768)  # Clamp to model's actual limit
        
        try:
            response = await self.azure_client.chat.completions.create(
                model=current_model_name,
                messages=messages,
                temperature=settings.LLM_DEFAULT_TEMPERATURE,
                seed=42,
                max_completion_tokens=max_tokens,
                response_format={"type": "json_object"}
            )
        except Exception as e:
            error_msg = str(e)
            logger.error(f"[BetaPipeline] Azure API Error: {error_msg}")
            return {
                "guide_extracted": {},
                "error": f"LLM API Error: {error_msg}"
            }
        
        content = response.choices[0].message.content
        finish_reason = getattr(response.choices[0], "finish_reason", "stop")
        
        try:
            result = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"[BetaPipeline] JSON Decode Error: {e}. Content-Length: {len(content)}, finish_reason: {finish_reason}")
            result = {
                "guide_extracted": {}, 
                "error": f"LLM Output Malformed: {str(e)}", 
                "_raw_llm_content": content
            }
        
        # Detect LLM output truncation: if finish_reason is 'length', the output
        # was cut off by max_completion_tokens. Flag it so the pipeline can fall back
        # to chunked extraction or per-table extraction.
        if finish_reason == "length":
            logger.warning(f"[BetaPipeline] LLM output truncated (finish_reason='length'). Setting _truncated=True.")
            result["_truncated"] = True
        
        usage = response.usage
        if usage:
             result["_token_usage"] = {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens
            }
        return result
