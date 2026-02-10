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
        
        # --- 1. Layout Parsing ---
        parser = LayoutParser(ocr_data)
        tagged_text, ref_map = parser.parse(focus_pages=focus_pages)
        
        content_len = len(tagged_text)
        page_count = len(ocr_data.get("pages", []))
        logger.info(f"[BetaPipeline] Analysis: pages={page_count}, content_len={content_len} chars")

        # --- 2. Designer LLM (Work Order — Cached) ---
        work_order = await self._run_designer(model)
        
        # --- 3. Engineer LLM (Extraction) ---
        SINGLE_SHOT_CHAR_LIMIT = 6000
        TEXT_CHUNK_SIZE = 4000
        
        if content_len <= SINGLE_SHOT_CHAR_LIMIT:
            logger.info("[BetaPipeline] Route: Single-Shot Engineer")
            engineer_output = await self._run_engineer(work_order, tagged_text, model)
        else:
            logger.info("[BetaPipeline] Route: Chunked Engineer with Header Preservation")
            engineer_output = await self._run_engineer_chunked(work_order, tagged_text, TEXT_CHUNK_SIZE, model)
        
        # --- 4. Post-Process (ref → bbox) ---
        final_guide = RefinerEngine.post_process_with_ref(
            engineer_output, ref_map
        )
        
        # --- 4b. Extract unmapped_critical_info → other_data ---
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
                "expected_format": f.type
            }
            if f.description:
                entry["instruction"] += f" {f.description}"
            if f.rules:
                entry["instruction"] += f" Rule: {f.rules}"
            
            if f.type in TABLE_FIELD_TYPES:
                entry["columns"] = {}
                entry["rules"] = ["Extract ALL rows."]
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
        
        raw_result = await self.call_llm(messages)
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
                    return await self.call_llm(messages)
                except Exception as e:
                    logger.error(f"[BetaPipeline] Engineer Chunk {chunk_idx} failed: {e}")
                    return {"guide_extracted": {}, "error": str(e)}
        
        # Parallel execution
        tasks = [process_chunk(chunk, idx) for idx, chunk in enumerate(chunks)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Merge results
        merged_guide = {}
        seen_rows = {}  # field_key -> Set[row_hash]
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        
        for res in results:
            if isinstance(res, Exception):
                logger.error(f"[BetaPipeline] Chunk gather exception: {res}")
                continue
            
            # Accumulate token usage
            usage = res.get("_token_usage", {})
            for k in total_usage:
                total_usage[k] += usage.get(k, 0)
            
            # Merge guide_extracted
            for key, val in res.get("guide_extracted", {}).items():
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
                    # Common field — first wins (should be same across chunks)
                    if key not in merged_guide:
                        merged_guide[key] = val
        
        return {
            "guide_extracted": merged_guide,
            "_token_usage": total_usage
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
            
            line_len = len(line) + 1  # +1 for newline
            
            if current_len + line_len > chunk_size and current_chunk:
                # Flush current chunk
                chunks.append("\n".join(current_chunk))
                current_chunk = []
                current_len = 0
                
                # If inside a table, inject header
                if active_header:
                    current_chunk.append(active_header[0])  # header row
                    current_chunk.append(active_header[1])  # separator
                    current_len += len(active_header[0]) + len(active_header[1]) + 2
            
            current_chunk.append(line)
            current_len += line_len
        
        if current_chunk:
            chunks.append("\n".join(current_chunk))
        
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
        Stage 2 (Large Content): Extract TABLE data from chunks (lines).
        """
        # --- Step 1: Split TAGGED text into chunks by line boundaries ---
        lines = tagged_text.split("\n")
        
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
        
        logger.info(f"[BetaPipeline] Table Chunking: Created {len(chunks)} text chunks")
        
        if not chunks:
            return ExtractionResult()
        
        # Header context for every chunk (so LLM knows table structure)
        header_context = tagged_text[:1500]
        
        # --- Run Parallel Extraction (Table Mode) ---
        table_prompt = RefinerEngine.construct_prompt(model, language="ko", mode="table")
        
        async def process_text_chunk(chunk_text: str, chunk_idx: int) -> ExtractionResult:
            """Send a tagged text chunk to LLM for TABLE field extraction only."""
            
            # Prepend header context to non-first chunks
            final_chunk = chunk_text
            if chunk_idx > 0:
                final_chunk = header_context + "\n... [Header Context End] ...\n" + chunk_text
            
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
                    logger.error(f"[BetaPipeline] Table Chunk {chunk_idx} failed: {e}")
                    # Return empty result with error
                    res = ExtractionResult()
                    res.error = str(e)
                    return res
        
        # Parallel execution
        tasks = [process_text_chunk(chunk, idx) for idx, chunk in enumerate(chunks)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # --- Merge Results (Field-aware Deduplication) ---
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
        logger.info(f"[BetaPipeline] Table Merge: Extracted fields {list(merged_guide.keys())}")
        
        return merged_result

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
                cleaned_extracted[k] = v
                continue
                
            # Case 2: Dict wrapper
            if isinstance(v, dict):
                # Check if it wraps a list: {"value": [...]}
                if "value" in v and isinstance(v["value"], list):
                     cleaned_extracted[k] = v["value"]
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

    async def call_llm(self, messages):
        """Direct LLM Call"""
        current_model_name = get_current_model()
        response = await self.azure_client.chat.completions.create(
            model=current_model_name,
            messages=messages,
            temperature=settings.LLM_DEFAULT_TEMPERATURE,
            max_tokens=settings.LLM_DEFAULT_MAX_TOKENS,
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content
        try:
            result = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"[BetaPipeline] JSON Decode Error: {e}. Content-Length: {len(content)}")
            # Return error structure that mimics successful response but with error flag
            result = {
                "guide_extracted": {}, 
                "error": f"LLM Output Malformed: {str(e)}", 
                "_raw_llm_content": content
            }
        
        usage = response.usage
        if usage:
             result["_token_usage"] = {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens
            }
        return result
