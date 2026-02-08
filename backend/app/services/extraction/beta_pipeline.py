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
        # Semaphore for Rate Limiting (Max 3 concurrent LLM calls)
        self.semaphore = asyncio.Semaphore(3)

    async def execute(self, model: ExtractionModel, ocr_data: Dict[str, Any], focus_pages: Optional[List[int]] = None) -> ExtractionResult:
        """
        Main Execution Entry Point
        """
        start_time = datetime.utcnow()
        
        # 1. Decide Strategy (Single Shot vs Chunked)
        page_count = len(ocr_data.get("pages", []))
        json_payload_len = len(json.dumps(ocr_data))
        
        CHUNK_PAGE_LIMIT = 3
        CHUNK_CHAR_LIMIT = 10000 
        
        should_chunk = (page_count > CHUNK_PAGE_LIMIT or json_payload_len > CHUNK_CHAR_LIMIT)
        
        if should_chunk:
            logger.info(f"[BetaPipeline] Triggering Chunked Execution: {page_count} pages, {json_payload_len} chars")
            result = await self._execute_chunked(model, ocr_data, page_count)
        else:
            logger.info(f"[BetaPipeline] Triggering Single-Shot Execution")
            result = await self._execute_single_shot(model, ocr_data, focus_pages)
            
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

    async def _execute_chunked(self, model: ExtractionModel, ocr_data: Dict[str, Any], total_pages: int) -> ExtractionResult:
        # Chunking Config
        CHUNK_SIZE = 2
        OVERLAP = 1 # Overlap 1 page to preserve context
        
        chunks = []
        # Create overlapping chunks: [1,2], [2,3], [3,4]...
        # If total_pages=5: [1,2], [2,3], [3,4], [4,5]
        # This is expensive but safer for context.
        # Alternatively, [1,2,3], [3,4,5] (overlap 1)
        
        # Simple Sliding Window: Step = Chunk - Overlap
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
        return merged_result

    async def _process_chunk_safe(self, model: ExtractionModel, ocr_data: Dict[str, Any], chunk_pages: List[int]) -> ExtractionResult:
        """Wrapper to use Semaphore and filter OCR"""
        async with self.semaphore:
            # Filter OCR
            chunk_ocr = self._filter_ocr_data(ocr_data, chunk_pages)
            
            # Execute Single Shot (LayoutParser inside sees 1..N pages)
            result = await self._execute_single_shot(model, chunk_ocr, focus_pages=None)
            
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
        if "rows" in raw_llm:
            res.table_rows = raw_llm["rows"]
            res.is_table = True
        else:
            res.guide_extracted = raw_llm.get("guide_extracted", {})
        
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
