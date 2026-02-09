import asyncio
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

class BetaPipeline(ExtractionPipeline):
    """
    Implements the Beta Extraction Strategy:
    1. LayoutParser (Structure-Aware Tagging)
    2. RefinerEngine (Dynamic Prompting)
    3. Smart Chunking (Overlap + Rate Limiting)
    """
    
    def __init__(self, azure_client: AsyncAzureOpenAI):
        self.azure_client = azure_client
        # Semaphore for Rate Limiting (Increased parallelism to 5 for speed)
        self.semaphore = asyncio.Semaphore(5)

    async def execute(self, model: ExtractionModel, ocr_data: Dict[str, Any], focus_pages: Optional[List[int]] = None) -> ExtractionResult:
        """
        Main Execution Entry Point.
        
        Refactored 2-Stage Strategy:
        1. Layout Analysis (Run Once)
        2. Scenario Routing:
           - CASE A: General Model (No table fields) -> Single-Shot (mode="all")
           - CASE B: Table Model (Has table fields) -> 2-Stage Pipeline
             - Stage 1: Extract Common Fields (mode="common") from Header Context
             - Stage 2: Extract Table Fields (mode="table") from Full Content (Single vs Chunked)
             - Merge: Combine Common + Table results into one Dict
        """
        start_time = datetime.utcnow()
        
        # --- 1. Layout Parsing (Once for all stages) ---
        parser = LayoutParser(ocr_data)
        tagged_text, ref_map = parser.parse(focus_pages=focus_pages)
        
        content_len = len(tagged_text)
        page_count = len(ocr_data.get("pages", []))
        
        # Thresholds
        SINGLE_SHOT_CHAR_LIMIT = 6000
        TEXT_CHUNK_SIZE = 4000
        
        logger.info(f"[BetaPipeline] Analysis: pages={page_count}, content_len={content_len} chars")

        # --- 2. Determine Strategy ---
        # Check if model has any table/list fields
        table_fields = [f for f in model.fields if f.type in ('list', 'table', 'array')]
        has_table = len(table_fields) > 0
        
        final_result = None
        
        if not has_table:
            # CASE A: General Model -> Single Shot (All fields)
            logger.info("[BetaPipeline] Route: General Mode (Single-Shot)")
            final_result = await self._extract_segment(model, tagged_text, ocr_data, ref_map, mode="all")
        else:
            # CASE B: Table Model -> 2-Stage Pipeline
            logger.info("[BetaPipeline] Route: Table Mode (2-Stage)")
            
            # Stage 1: Common Fields (Header Context up to 3000 chars)
            header_context = tagged_text[:3000]
            logger.info("[BetaPipeline] Stage 1: Extracting Common Fields...")
            common_result = await self._extract_segment(model, header_context, ocr_data, ref_map, mode="common")
            
            # Stage 2: Table Fields
            logger.info("[BetaPipeline] Stage 2: Extracting Table Fields...")
            if content_len <= SINGLE_SHOT_CHAR_LIMIT:
                # Small Table -> Single Shot
                table_result = await self._extract_segment(model, tagged_text, ocr_data, ref_map, mode="table")
            else:
                # Large Table -> Chunked
                table_result = await self._extract_table_chunked(model, tagged_text, ocr_data, ref_map, TEXT_CHUNK_SIZE)
                
            # Merge Results
            final_result = self._merge_results(common_result, table_result)

        final_result.duration_seconds = (datetime.utcnow() - start_time).total_seconds()
        final_result.model_name = model.name
        
        # Add metadata
        final_result.beta_metadata = {
            "parsed_content": tagged_text,
            "ref_map": ref_map,
            "pipeline_mode": "2-stage" if has_table else "general"
        }
        
        return final_result

    async def _extract_segment(self, model: ExtractionModel, text_segment: str, ocr_data: Dict, ref_map: Dict, mode: str) -> ExtractionResult:
        """Helper to run a single LLM call for a text segment with specific mode."""
        system_prompt = RefinerEngine.construct_prompt(model, language="ko", mode=mode)
        user_prompt = f"DOCUMENT DATA (Tagged Layout Format):\n{text_segment}\n\nTASK: Extract fields based on system instructions.\nReturn valid JSON."
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        raw_result = await self.call_llm(messages)
        return self._normalize_output(raw_result, ocr_data, ref_map, text_segment)

    def _merge_results(self, common: ExtractionResult, table: ExtractionResult) -> ExtractionResult:
        """Merge Common and Table results into a single Dict."""
        merged = ExtractionResult()
        
        # 1. Start with Common fields
        merged.guide_extracted.update(common.guide_extracted)
        
        # 2. Update with Table fields
        # Note: If key collision exists (unlikely with mode separation), Table wins? 
        # No, they should be disjoint sets of keys.
        merged.guide_extracted.update(table.guide_extracted)
        
        # 3. Sum tokens
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
        
        merged_result.guide_extracted = merged_guide
        logger.info(f"[BetaPipeline] Table Merge: Extracted fields {list(merged_guide.keys())}")
        
        return merged_result


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
