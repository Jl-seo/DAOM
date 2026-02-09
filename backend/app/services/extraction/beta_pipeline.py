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
        
        Simplified 2-Tier Strategy (Format-Agnostic):
        1. Small content (≤ threshold) → Single-Shot (PDF, Excel, DOCX 모두 동일)
        2. Large content (> threshold)  → Text-Based Chunking + Merge
        
        Note: has_real_pages is NOT used for routing.
        Azure DI returns pages with words for BOTH PDF and Excel,
        so it cannot distinguish file types. content_len is the only
        reliable signal for deciding single-shot vs chunked.
        """
        start_time = datetime.utcnow()
        
        # --- 1. Document Info ---
        pages = ocr_data.get("pages", [])
        page_count = len(pages)
        content = ocr_data.get("content", "") or ""
        content_len = len(content)
        
        # Thresholds
        # ~6,000 chars ≈ ~2,000 tokens input ≈ ~40 rows (safe for LLM output limit)
        SINGLE_SHOT_CHAR_LIMIT = 6000
        # For text-based chunking: 4,000 chars ≈ 1,300 tokens ≈ ~25 rows per chunk
        TEXT_CHUNK_SIZE = 4000
        
        logger.info(
            f"[BetaPipeline] Document Analysis: "
            f"pages={page_count}, content_len={content_len}"
        )
        
        # --- 2. Route by content size only (format-agnostic) ---
        if content_len <= SINGLE_SHOT_CHAR_LIMIT:
            logger.info(f"[BetaPipeline] Single-Shot ({content_len} chars, {page_count} pages)")
            result = await self._execute_single_shot(model, ocr_data, focus_pages)
        else:
            logger.info(f"[BetaPipeline] Text-Chunked ({content_len} chars, {page_count} pages)")
            result = await self._execute_text_chunked(model, ocr_data, TEXT_CHUNK_SIZE)
            
        result.duration_seconds = (datetime.utcnow() - start_time).total_seconds()
        result.model_name = model.name
        return result

    async def _execute_single_shot(self, model: ExtractionModel, ocr_data: Dict[str, Any], focus_pages: Optional[List[int]] = None) -> ExtractionResult:
        # 1. Layout Parsing
        parser = LayoutParser(ocr_data)
        tagged_text, ref_map = parser.parse(focus_pages=focus_pages)
        
        # 2. Refiner Prompt
        system_prompt = RefinerEngine.construct_prompt(model, language="ko")
        user_prompt = f"DOCUMENT DATA (Tagged Layout Format):\n{tagged_text}\n\nTASK: Extract fields based on system instructions.\nReturn valid JSON."
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # 3. LLM Call
        raw_result = await self.call_llm(messages)
        
        # 4. Normalize Result
        return self._normalize_output(raw_result, ocr_data, ref_map, tagged_text)

    async def _execute_text_chunked(self, model: ExtractionModel, ocr_data: Dict[str, Any], chunk_size: int) -> ExtractionResult:
        """
        TIER 3: Text-Based Line Chunking for Large Digital Documents.
        
        Architecture:
        1. LayoutParser runs ONCE on full OCR data (Python = cheap, handle all data)
        2. Tagged text is split into chunks by line boundaries
        3. Each chunk is sent to LLM with Refiner prompt (LLM = expensive, split here only)
        
        Previous broken approach: split text FIRST, then gave LayoutParser empty OCR per chunk.
        """
        # --- Step 1: Run LayoutParser on FULL OCR data (Python is cheap) ---
        parser = LayoutParser(ocr_data)
        tagged_text, ref_map = parser.parse()
        
        logger.info(f"[BetaPipeline] TIER 3: LayoutParser produced {len(tagged_text)} chars "
                     f"with {len(ref_map)} refs from full OCR")
        
        # --- Step 2: Split TAGGED text into chunks by line boundaries ---
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
        
        logger.info(f"[BetaPipeline] TIER 3: Created {len(chunks)} text chunks "
                     f"(sizes: {[len(c) for c in chunks]})")
        
        if not chunks:
            logger.warning("[BetaPipeline] TIER 3: No content to chunk. Returning empty.")
            return ExtractionResult()
        
        # Header context: first 1200 chars of tagged text (includes table headers with tags)
        header_context = tagged_text[:1200]
        
        # --- Step 3: Build Refiner prompt ONCE (same for all chunks) ---
        system_prompt = RefinerEngine.construct_prompt(model, language="ko")
        
        # --- Step 4: Send each chunk to LLM directly (LLM = expensive, split here) ---
        async def process_text_chunk(chunk_text: str, chunk_idx: int) -> ExtractionResult:
            """Send a tagged text chunk directly to LLM."""
            
            # Prepend header context to non-first chunks so LLM knows table structure
            final_chunk = chunk_text
            if chunk_idx > 0:
                final_chunk = header_context + "\n... [Header Context End] ...\n" + chunk_text
            
            user_prompt = (
                f"DOCUMENT DATA (Tagged Layout Format):\n{final_chunk}\n\n"
                f"TASK: Extract fields based on system instructions.\n"
                f"Return valid JSON."
            )
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            async with self.semaphore:
                try:
                    raw_result = await self.call_llm(messages)
                    return self._normalize_output(raw_result, ocr_data, ref_map, chunk_text)
                except Exception as e:
                    logger.error(f"[BetaPipeline] TIER 3: Chunk {chunk_idx} failed: {e}")
                    err_result = ExtractionResult()
                    err_result.error = str(e)
                    return err_result
        
        # Parallel execution
        tasks = [process_text_chunk(chunk, idx) for idx, chunk in enumerate(chunks)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # --- Step 5: Merge Results ---
        merged_result = ExtractionResult()
        merged_rows = []
        seen_keys = set()
        
        for res in results:
            if isinstance(res, Exception):
                logger.error(f"[BetaPipeline] TIER 3: Chunk exception: {res}")
                continue
            
            merged_result.token_usage.prompt_tokens += res.token_usage.prompt_tokens
            merged_result.token_usage.completion_tokens += res.token_usage.completion_tokens
            merged_result.token_usage.total_tokens += res.token_usage.total_tokens
            
            current_rows = res.table_rows or []
            if not current_rows and res.guide_extracted:
                current_rows = [res.guide_extracted]
            
            for row in current_rows:
                row_hash = json.dumps(row, sort_keys=True, ensure_ascii=False)
                if row_hash not in seen_keys:
                    seen_keys.add(row_hash)
                    merged_rows.append(row)
        
        merged_result.table_rows = merged_rows
        merged_result.is_table = bool(merged_rows)
        
        if not merged_rows:
            for res in results:
                if isinstance(res, Exception): continue
                if res.guide_extracted:
                    merged_result.guide_extracted = res.guide_extracted
                    merged_result.is_table = False
                    break
        
        merged_result.beta_metadata = {
            "parsed_content": tagged_text,  # Full tagged text for debug view
            "ref_map": ref_map
        }
        
        logger.info(f"[BetaPipeline] TIER 3: Merged {len(merged_rows)} unique rows from {len(chunks)} chunks")
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
        """Convert LLM JSON to Standard ExtractionResult"""
        res = ExtractionResult()
        
        # Mapping logic
        # Mapping logic
        # [Refactor Phase 7] Nested Table structure
        # LLM now returns {"guide_extracted": {"some_table_field": [{...}, {...}]}}
        # We must find the list field and populate table_rows for backward compat.
        
        extracted = raw_llm.get("guide_extracted", {})
        res.guide_extracted = extracted
        
        # Check if any field in guide_extracted is a list of dicts (Candidate for Table)
        # Or if "rows" still exists (fallback)
        if "rows" in raw_llm:
             rows = raw_llm["rows"]
             # [Fix] Sanitize Dict->List
             if isinstance(rows, dict):
                try:
                    sorted_keys = sorted(rows.keys(), key=lambda x: int(x) if str(x).isdigit() else x)
                    rows = [rows[k] for k in sorted_keys]
                except:
                    rows = list(rows.values())
             res.table_rows = rows
             res.is_table = True
        else:
            # Look for table field in guide_extracted
            found_table = False
            for k, v in extracted.items():
                if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                    # Found a potential table!
                    # We promote this to res.table_rows for consistency with chunk merging logic
                    # But we also keep it in guide_extracted.
                    res.table_rows = v
                    res.is_table = True
                    found_table = True
                    # Break or continue? Assuming one main table for Beta Mode usually.
                    # If multiple, chunk merging logic might need robust handling.
                    # For now, take the first valid table.
                    break
            
            if not found_table and extracted:
                # Fallback: maybe it's just a form
                pass
        
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
        result = json.loads(content)
        
        usage = response.usage
        if usage:
             result["_token_usage"] = {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens
            }
        return result
