"""
Beta Chunking Service

Intelligent chunking for the beta extraction path (LayoutParser + RefinerEngine).
Handles large documents by:
1. Splitting OCR data into page groups
2. Running LayoutParser per chunk for tagged content + ref_map
3. Parallel LLM calls with RefinerEngine prompts
4. Merging results with best-confidence field selection
"""
import asyncio
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from app.core.config import settings

logger = logging.getLogger(__name__)

# Sizing constants
CHARS_PER_TOKEN = 4
# Target max chars per chunk for LLM prompt (content + tables).
# GPT-4o: 128K tokens context. System prompt ~2K tokens, response ~4K tokens.
# Leaves ~122K tokens for user prompt ≈ 488K chars.
# But we want headroom, so target ~80K tokens = 320K chars.
MAX_PROMPT_CHARS = settings.CHUNK_MAX_PROMPT_CHARS
# Threshold to trigger chunking: if total content exceeds this, chunk.
CHUNKING_THRESHOLD_CHARS = settings.CHUNK_THRESHOLD_CHARS  # ~25K tokens — conservative

# Known wrapper keys that LLMs might use
_WRAPPER_KEYS = {"result", "results", "data", "extraction", "extracted", "output", "response", "fields", "guide_extracted"}


def normalize_llm_response(llm_json: Dict[str, Any], model_info) -> Dict[str, Any]:
    """
    Normalize LLM response to the expected flat structure:
        {field_key: {value: ..., confidence: ..., source_text: ...}}
    
    For TABLE mode models (data_structure == 'table'), the LLM returns:
        {"rows": [{col1: val1, col2: val2, ...}, ...]}
    This is passed through as:
        {"_table_rows": [...], "_is_table": True}
    
    Handles common LLM response anomalies:
    1. Nested wrappers: {"result": {"field_key": {...}}}
    2. Flat values: {"field_key": "some_value"} instead of {"field_key": {"value": ...}}
    3. Array-wrapped: [{"field_key": {...}}]
    4. Missing confidence/source_text
    """
    if not llm_json:
        logger.warning("[Normalize] Empty LLM response")
        return {}

    # Get expected field keys from model
    expected_keys = {f.key for f in model_info.fields} if hasattr(model_info, 'fields') else set()
    is_table = getattr(model_info, 'data_structure', 'data') == 'table'

    # Log raw structure for diagnostics
    top_keys = list(llm_json.keys()) if isinstance(llm_json, dict) else ["(array)"]
    logger.info(f"[Normalize] Raw LLM response keys: {top_keys}, expected: {list(expected_keys)[:5]}..., table_mode={is_table}")

    # TABLE MODE: detect and pass through row arrays
    if is_table:
        rows = None
        if isinstance(llm_json, dict) and "rows" in llm_json:
            rows = llm_json["rows"]
        elif isinstance(llm_json, list):
            rows = llm_json

        if isinstance(rows, list):
            logger.info(f"[Normalize] TABLE MODE: {len(rows)} rows extracted")
            # Clean each row: ensure consistent structure
            cleaned_rows = []
            for i, row in enumerate(rows):
                if not isinstance(row, dict):
                    logger.warning(f"[Normalize] Row {i} is not a dict, skipping: {type(row)}")
                    continue
                cleaned_row = {}
                for fkey in expected_keys:
                    cleaned_row[fkey] = row.get(fkey)
                cleaned_row["_confidence"] = row.get("_confidence", 0.8)
                cleaned_row["_source_text"] = row.get("_source_text", "")
                cleaned_rows.append(cleaned_row)

            return {
                "_table_rows": cleaned_rows,
                "_is_table": True,
            }
        else:
            logger.warning("[Normalize] TABLE MODE but no 'rows' array found, falling back to standard mode")

    result = llm_json

    # Step 1: Unwrap if response is array
    if isinstance(result, list):
        logger.warning(f"[Normalize] Response is array with {len(result)} items, using first")
        result = result[0] if result else {}

    # Step 2: Unwrap nested containers
    # If top-level keys don't match expected fields, look for a wrapper
    if expected_keys and not (expected_keys & set(result.keys())):
        # No overlap with expected keys — look for a wrapper
        for wrapper_key in _WRAPPER_KEYS:
            if wrapper_key in result:
                inner = result[wrapper_key]
                if isinstance(inner, dict):
                    logger.info(f"[Normalize] Unwrapped from '{wrapper_key}' container")
                    result = inner
                    break
                elif isinstance(inner, list) and inner:
                    logger.info(f"[Normalize] Unwrapped from '{wrapper_key}' array")
                    result = inner[0] if isinstance(inner[0], dict) else {}
                    break

    # Step 3: Normalize each field value
    normalized = {}
    for key, item in result.items():
        if isinstance(item, dict) and "value" in item:
            # Already correct structure
            normalized[key] = {
                "value": item.get("value"),
                "confidence": item.get("confidence", 0.8),
                "source_text": item.get("source_text", ""),
            }
        elif isinstance(item, dict):
            # Dict but no "value" key — try to extract
            # Could be {"answer": "...", "score": 0.9}
            val = item.get("answer") or item.get("text") or item.get("result") or item.get("extracted_value")
            if val is not None:
                normalized[key] = {
                    "value": val,
                    "confidence": item.get("confidence") or item.get("score", 0.7),
                    "source_text": item.get("source_text") or item.get("source", ""),
                }
                logger.info(f"[Normalize] Field '{key}': recovered from non-standard dict")
            else:
                # Keep as-is, post_process_result will handle
                normalized[key] = item
        else:
            # Flat value (string, number, etc.) — wrap it
            logger.info(f"[Normalize] Field '{key}': flat value '{str(item)[:50]}', wrapping")
            normalized[key] = {
                "value": item,
                "confidence": 0.7,
                "source_text": str(item) if item is not None else "",
            }

    # Step 4: Report coverage
    found_fields = expected_keys & set(normalized.keys())
    missing_fields = expected_keys - set(normalized.keys())
    if missing_fields:
        logger.warning(f"[Normalize] Missing {len(missing_fields)} fields: {list(missing_fields)[:5]}")
    logger.info(f"[Normalize] Coverage: {len(found_fields)}/{len(expected_keys)} fields found")

    return normalized


@dataclass
class BetaChunk:
    """A chunk of OCR data for one or more pages."""
    index: int
    page_numbers: List[int]          # Global page numbers in this chunk
    ocr_subset: Dict[str, Any]       # OCR data subset (pages, paragraphs, tables, content)
    estimated_chars: int


@dataclass
class BetaChunkResult:
    """Result from processing a single beta chunk."""
    chunk_index: int
    page_numbers: List[int]
    success: bool
    guide_extracted: Dict[str, Any] = field(default_factory=dict)
    ref_map: Dict[str, Any] = field(default_factory=dict)
    content_text: str = ""
    token_usage: Optional[Dict[str, int]] = None
    error: Optional[str] = None


def _get_page_number(page: Dict) -> int:
    """Get page number handling both snake_case and camelCase."""
    return page.get("page_number") or page.get("pageNumber", 1)


def _is_on_page(obj: Dict, page_num: int) -> bool:
    """Check if a paragraph/table belongs to a specific page."""
    regions = obj.get("bounding_regions") or obj.get("boundingRegions") or []
    return any(
        (br.get("page_number") or br.get("pageNumber")) == page_num
        for br in regions
    )


def _estimate_page_chars(page: Dict, paragraphs: List[Dict], tables: List[Dict]) -> int:
    """Estimate character count for a page including its paragraphs and tables."""
    page_num = _get_page_number(page)
    chars = 0
    for p in paragraphs:
        if _is_on_page(p, page_num):
            chars += len(p.get("content", ""))
    for t in tables:
        if _is_on_page(t, page_num):
            for cell in t.get("cells", []):
                chars += len(cell.get("content", ""))
    return chars


def split_ocr_into_chunks(
    ocr_data: Dict[str, Any],
    max_chars: int = MAX_PROMPT_CHARS,
) -> List[BetaChunk]:
    """
    Split OCR data into page-group chunks.
    Each chunk stays under max_chars estimated size.
    Groups consecutive pages to maintain context.
    """
    pages = ocr_data.get("pages", [])
    paragraphs = ocr_data.get("paragraphs", [])
    tables = ocr_data.get("tables", [])
    content = ocr_data.get("content", "") or ""

    if not pages:
        # No page structure — single chunk
        return [BetaChunk(
            index=0,
            page_numbers=[1],
            ocr_subset=ocr_data,
            estimated_chars=len(content)
        )]

    # Estimate per-page sizes
    page_sizes = []
    for page in pages:
        pn = _get_page_number(page)
        size = _estimate_page_chars(page, paragraphs, tables)
        page_sizes.append((pn, page, size))

    # Group pages into chunks
    chunks: List[BetaChunk] = []
    current_pages: List[int] = []
    current_page_objs: List[Dict] = []
    current_chars = 0

    for pn, page_obj, size in page_sizes:
        # Would adding this page exceed the limit?
        if current_chars + size > max_chars and current_pages:
            # Finalize current chunk
            new_chunk = _build_chunk(
                index=len(chunks),
                page_numbers=current_pages,
                page_objs=current_page_objs,
                paragraphs=paragraphs,
                tables=tables,
                content=content,
                estimated_chars=current_chars,
            )
            # Propagate bypass flag
            if ocr_data.get("_layout_parser_bypass"):
                new_chunk.ocr_subset["_layout_parser_bypass"] = True

            chunks.append(new_chunk)

            current_pages = []
            current_page_objs = []
            current_chars = 0

        current_pages.append(pn)
        current_page_objs.append(page_obj)
        current_chars += size

    # Final chunk
    if current_pages:
        new_chunk = _build_chunk(
            index=len(chunks),
            page_numbers=current_pages,
            page_objs=current_page_objs,
            paragraphs=paragraphs,
            tables=tables,
            content=content,
            estimated_chars=current_chars,
        )
        if ocr_data.get("_layout_parser_bypass"):
            new_chunk.ocr_subset["_layout_parser_bypass"] = True
        chunks.append(new_chunk)

    logger.info(f"[BetaChunk] Split {len(pages)} pages into {len(chunks)} chunks")
    for c in chunks:
        logger.info(f"  Chunk {c.index}: pages {c.page_numbers}, ~{c.estimated_chars} chars")

    return chunks


def _build_chunk(
    index: int,
    page_numbers: List[int],
    page_objs: List[Dict],
    paragraphs: List[Dict],
    tables: List[Dict],
    content: str,
    estimated_chars: int,
) -> BetaChunk:
    """Build a BetaChunk with OCR subset for the given pages."""
    page_set = set(page_numbers)

    # Filter paragraphs by page; include those without bounding_regions
    chunk_paragraphs = []
    for p in paragraphs:
        regions = p.get("bounding_regions") or p.get("boundingRegions") or []
        if regions:
            if any(_is_on_page(p, pn) for pn in page_set):
                chunk_paragraphs.append(p)
        else:
            # No bounding_regions — include conservatively
            chunk_paragraphs.append(p)

    # Fallback to lines if paragraphs are empty (e.g. ExcelMapper output)
    chunk_lines = []
    if not chunk_paragraphs and page_objs:
        for page in page_objs:
            if _get_page_number(page) in page_set:
                 chunk_lines.extend(page.get("lines", []))

    # Filter tables by page; include those without bounding_regions
    chunk_tables = []
    for t in tables:
        regions = t.get("bounding_regions") or t.get("boundingRegions") or []
        if regions:
            if any(_is_on_page(t, pn) for pn in page_set):
                chunk_tables.append(t)
        else:
            # No bounding_regions — include conservatively
            chunk_tables.append(t)

    # Build content subset from paragraphs > lines > tables > full content
    if chunk_paragraphs:
        chunk_content = "\n".join(p.get("content", "") for p in chunk_paragraphs)
    elif chunk_lines:
        chunk_content = "\n".join(l.get("content", "") for l in chunk_lines)
    elif chunk_tables:
        # Reconstruct from table cells
        cell_contents = []
        for t in chunk_tables:
            for cell in t.get("cells", []):
                cell_contents.append(cell.get("content", ""))
        chunk_content = "\n".join(cell_contents)
    else:
        chunk_content = ""

    # FINAL FALLBACK: If chunk_content is still empty, use the full OCR content.
    # This ensures Excel/CSV files that lack page-level structure still get processed.
    if not chunk_content.strip() and content:
        chunk_content = content
        logger.info(f"[_build_chunk] Chunk {index}: Using full OCR content as fallback ({len(content)} chars)")

    ocr_subset = {
        "pages": page_objs,
        "paragraphs": chunk_paragraphs,
        "tables": chunk_tables,
        "content": chunk_content,
    }

    return BetaChunk(
        index=index,
        page_numbers=page_numbers,
        ocr_subset=ocr_subset,
        estimated_chars=estimated_chars,
    )


async def process_beta_chunk(
    chunk: BetaChunk,
    model_info: Any,
    language: str = "ko",
    max_retries: int = 3,
    retry_delay_base: float = 2.0,
) -> BetaChunkResult:
    """
    Process a single beta chunk with retry and exponential backoff.
    
    1. Run LayoutParser on chunk's OCR subset
    2. Build prompt with RefinerEngine
    3. Call LLM (with retry on transient errors)
    4. Post-process with RefinerEngine
    """
    from app.services.layout_parser import LayoutParser
    from app.services.refiner import RefinerEngine
    from app.services.llm import call_llm_single

    chunk_label = f"BetaChunk-{chunk.index}"

    # 1. LayoutParser (no retry — deterministic, won't change on retry)
    # OPTIMIZATION: Check for bypass specific to Excel/CSV
    if chunk.ocr_subset.get("_layout_parser_bypass"):
         logger.info(f"[{chunk_label}] LayoutParser bypassed (Excel/CSV optimization)")
         content_text = chunk.ocr_subset.get("content", "")
         ref_map = {}
    else:
        try:
            parser = LayoutParser(chunk.ocr_subset)
            content_text, ref_map = parser.parse()
            logger.info(
                f"[{chunk_label}] Parsed: {len(content_text)} chars, "
                f"{len(ref_map)} refs, pages {chunk.page_numbers}"
            )
        except Exception as e:
            logger.error(f"[{chunk_label}] LayoutParser failed: {e}", exc_info=True)
            # Fall back to raw content
            content_text = chunk.ocr_subset.get("content", "")
            ref_map = {}
            logger.info(f"[{chunk_label}] Falling back to raw content: {len(content_text)} chars")

    # Guard: If content is empty even after fallback, skip LLM
    if not content_text or not content_text.strip():
        logger.warning(f"[{chunk_label}] No content text available. Skipping LLM.")
        return BetaChunkResult(
            chunk_index=chunk.index,
            page_numbers=chunk.page_numbers,
            success=False,
            error="No content text extracted from chunk"
        )

    # 2. Build prompts (deterministic — prepare once)
    system_prompt = RefinerEngine.construct_prompt(model_info, language)

    # OPTIMIZATION: If LayoutParser was bypassed (Excel), content_text IS the table.
    # No need to append _build_tables_context which would duplicate the data.
    if chunk.ocr_subset.get("_layout_parser_bypass"):
        tables_context = ""
    else:
        tables_context = _build_tables_context(chunk.ocr_subset.get("tables", []))

    user_prompt = f"Document Text (Pages {chunk.page_numbers}):\n{content_text}\n{tables_context}"

    prompt_size = len(user_prompt)
    logger.info(f"[{chunk_label}] Prompt size: {prompt_size} chars ({prompt_size // CHARS_PER_TOKEN} est. tokens)")

    # TOKEN AUDIT: Accurate token counting for optimization
    try:
        from app.services.token_audit import audit_prompt
        audit = audit_prompt(system_prompt, user_prompt)
        logger.info(f"[{chunk_label}] TOKEN AUDIT:\n{audit['summary']}")
    except Exception:
        pass  # Non-fatal: audit is diagnostic only

    # 3. LLM call with retry
    last_error = None
    for attempt in range(max_retries):
        try:
            llm_response = await call_llm_single(system_prompt, user_prompt, model_info=model_info)

            if "error" in llm_response:
                error_msg = llm_response["error"]
                last_error = error_msg
                logger.warning(f"[{chunk_label}] LLM returned error (attempt {attempt + 1}): {error_msg}")

                # Check if retryable
                error_lower = error_msg.lower()
                is_rate_limit = "429" in error_msg or "rate" in error_lower
                is_token_error = "token" in error_lower or "context_length" in error_lower

                if is_token_error:
                    # Token overflow — truncate and retry
                    current_len = len(user_prompt)
                    user_prompt = user_prompt[:current_len * 2 // 3] + \
                        "\n\n[... CONTENT TRUNCATED DUE TO TOKEN LIMIT ...]"
                    logger.warning(
                        f"[{chunk_label}] Token overflow, truncating: "
                        f"{current_len} → {len(user_prompt)} chars"
                    )
                    if attempt < max_retries - 1:
                        continue
                elif is_rate_limit and attempt < max_retries - 1:
                    wait_time = retry_delay_base * (2 ** attempt) * 2
                    logger.info(f"[{chunk_label}] Rate limited, waiting {wait_time}s")
                    await asyncio.sleep(wait_time)
                    continue
                elif attempt < max_retries - 1:
                    wait_time = retry_delay_base * (2 ** attempt)
                    await asyncio.sleep(wait_time)
                    continue

                # Final attempt failed
                return BetaChunkResult(
                    chunk_index=chunk.index,
                    page_numbers=chunk.page_numbers,
                    success=False,
                    content_text=content_text,
                    ref_map=ref_map,
                    error=f"LLM error after {attempt + 1} attempts: {error_msg}",
                    token_usage=llm_response.get("_token_usage"),
                )

            # Success — normalize and post-process
            llm_json = llm_response.get("result", {})
            logger.info(
                f"[{chunk_label}] LLM success (attempt {attempt + 1}), "
                f"raw keys: {list(llm_json.keys())[:10]}, "
                f"sample: {str(llm_json)[:300]}"
            )

            # Normalize: handle wrapped/flat/non-standard structures
            llm_json = normalize_llm_response(llm_json, model_info)

            processed = RefinerEngine.post_process_result(llm_json, chunk.ocr_subset)

            return BetaChunkResult(
                chunk_index=chunk.index,
                page_numbers=chunk.page_numbers,
                success=True,
                guide_extracted=processed,
                ref_map=ref_map,
                content_text=content_text,
                token_usage=llm_response.get("_token_usage"),
            )

        except Exception as e:
            last_error = str(e)
            logger.warning(f"[{chunk_label}] Attempt {attempt + 1} exception: {last_error}")

            error_lower = last_error.lower()
            is_rate_limit = "429" in last_error or "rate" in error_lower

            if is_rate_limit and attempt < max_retries - 1:
                wait_time = retry_delay_base * (2 ** attempt) * 2
                logger.info(f"[{chunk_label}] Rate limited (exception), waiting {wait_time}s")
                await asyncio.sleep(wait_time)
            elif attempt < max_retries - 1:
                wait_time = retry_delay_base * (2 ** attempt)
                await asyncio.sleep(wait_time)

    # All retries exhausted
    return BetaChunkResult(
        chunk_index=chunk.index,
        page_numbers=chunk.page_numbers,
        success=False,
        content_text=content_text,
        ref_map=ref_map,
        error=f"Failed after {max_retries} attempts: {last_error}",
    )


def _build_tables_context(tables: List[Dict]) -> str:
    """Build a text representation of tables for the LLM prompt."""
    if not tables:
        return ""

    context = "\n\n=== DETECTED TABLES (Structure Reference) ===\n"
    for idx, table in enumerate(tables):
        cells = table.get("cells", [])
        row_count = table.get("rowCount", 0)
        col_count = table.get("columnCount", 0)
        # Auto-calculate col_count from cells if metadata is missing/zero
        if not col_count and cells:
            col_count = max((c.get("columnIndex", 0) for c in cells), default=0) + 1

        context += f"\nTable {idx + 1} ({row_count}x{col_count}):\n"

        grid: Dict[int, Dict[int, str]] = {}
        for cell in cells:
            r = cell.get("rowIndex", 0)
            c = cell.get("columnIndex", 0)
            cell_content = cell.get("content", "").replace("\n", " ")
            if r < 20:  # Limit rows
                if r not in grid:
                    grid[r] = {}
                grid[r][c] = cell_content

        for r in sorted(grid.keys()):
            row_cells = grid[r]
            row_str = " | ".join(row_cells.get(c, "") for c in range(col_count))
            context += f"| {row_str} |\n"

        if row_count > 20:
            context += f"... ({row_count - 20} more rows) ...\n"

    return context


def merge_beta_results(
    results: List[BetaChunkResult],
    model_fields: List[Any],
) -> Dict[str, Any]:
    """
    Merge results from multiple beta chunks.
    
    Strategy:
    - For each field: take the highest-confidence non-null value
    - Merge ref_maps from all chunks
    - Concatenate content_text segments
    - Aggregate token usage
    """
    merged_guide: Dict[str, Any] = {}
    merged_ref_map: Dict[str, Any] = {}
    merged_content_parts: List[str] = []
    total_token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    errors: List[str] = []
    field_sources: Dict[str, Dict] = {}  # Track which chunk gave each field

    sorted_results = sorted(results, key=lambda r: r.chunk_index)

    for result in sorted_results:
        # Collect content regardless of success
        if result.content_text:
            merged_content_parts.append(
                f"--- Pages {result.page_numbers} ---\n{result.content_text}"
            )

        # Merge ref_map
        if result.ref_map:
            # Prefix ref_map keys with chunk index to avoid collisions
            for key, val in result.ref_map.items():
                prefixed_key = f"ch{result.chunk_index}_{key}"
                merged_ref_map[prefixed_key] = val

        # Aggregate token usage
        if result.token_usage:
            for k in total_token_usage:
                total_token_usage[k] += result.token_usage.get(k, 0)

        if not result.success:
            errors.append(f"Chunk {result.chunk_index} (pages {result.page_numbers}): {result.error}")
            continue

        # Merge guide_extracted: best confidence wins
        for key, item in result.guide_extracted.items():
            if not isinstance(item, dict):
                continue

            value = item.get("value")
            confidence = item.get("confidence", 0)

            if key not in merged_guide:
                merged_guide[key] = item
                field_sources[key] = {
                    "chunk": result.chunk_index,
                    "pages": result.page_numbers,
                }
            else:
                current = merged_guide[key]
                current_val = current.get("value")
                current_conf = current.get("confidence", 0)

                # Replace if: current is null and new is not, or new has higher confidence
                if (current_val is None and value is not None) or \
                   (value is not None and confidence > current_conf):
                    merged_guide[key] = item
                    field_sources[key] = {
                        "chunk": result.chunk_index,
                        "pages": result.page_numbers,
                    }

    # Build final result
    merged_content = "\n\n".join(merged_content_parts)

    success_count = sum(1 for r in results if r.success)
    logger.info(
        f"[BetaMerge] Merged {len(merged_guide)} fields from "
        f"{len(results)} chunks ({success_count} successful)"
    )

    return {
        "guide_extracted": merged_guide,
        "other_data": [],
        "_beta_parsed_content": merged_content,
        "_beta_ref_map": merged_ref_map,
        "_token_usage": total_token_usage if total_token_usage["total_tokens"] > 0 else None,
        "_beta_chunking_info": {
            "total_chunks": len(results),
            "successful_chunks": success_count,
            "field_sources": field_sources,
            "errors": errors,
        },
        "raw_content": "",  # Will be filled by caller
    }


def needs_chunking(ocr_data: Dict[str, Any]) -> bool:
    """Determine if OCR data is large enough to require chunking."""
    content = ocr_data.get("content", "") or ""
    pages = ocr_data.get("pages", [])
    tables = ocr_data.get("tables", [])

    # Estimate total chars including table content
    total_chars = len(content)
    for t in tables:
        for cell in t.get("cells", []):
            total_chars += len(cell.get("content", ""))

    needs = total_chars > CHUNKING_THRESHOLD_CHARS
    if needs:
        logger.info(
            f"[BetaChunk] Chunking needed: {total_chars} chars "
            f"(threshold: {CHUNKING_THRESHOLD_CHARS}), "
            f"{len(pages)} pages, {len(tables)} tables"
        )
    return needs


async def extract_beta_with_chunking(
    ocr_data: Dict[str, Any],
    model_info: Any,
    language: str = "ko",
    max_concurrent: int = 4,  # Increased after resource scale-up
) -> Dict[str, Any]:
    """
    Main entry point for beta extraction with chunking support.
    
    If document is small enough, runs single-call (no chunking).
    If large, splits into page chunks and processes in parallel.
    
    Returns dict with:
        - guide_extracted: merged field data
        - _beta_parsed_content: concatenated LayoutParser output
        - _beta_ref_map: merged ref_map from all chunks
        - _token_usage: aggregated token usage
        - _beta_chunking_info: chunking metadata for debug
    """
    # UNIFIED PATH: Always use chunking logic.
    # Small documents will naturally result in 1 chunk.
    # This ensures consistent behavior (Excel bypass, Prompt Opt) for all files.
    chunks = split_ocr_into_chunks(ocr_data)
    logger.info(f"[BetaChunk] Processing {len(chunks)} chunks with max {max_concurrent} concurrent")

    semaphore = asyncio.Semaphore(max_concurrent)

    async def _process_with_limit(chunk: BetaChunk) -> BetaChunkResult:
        async with semaphore:
            try:
                result = await process_beta_chunk(chunk, model_info, language)
                return result
            finally:
                # Aggressive cleanup to prevent OOM
                import gc
                gc.collect()

    tasks = [_process_with_limit(c) for c in chunks]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Handle gather exceptions
    processed_results: List[BetaChunkResult] = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            processed_results.append(BetaChunkResult(
                chunk_index=i,
                page_numbers=chunks[i].page_numbers if i < len(chunks) else [],
                success=False,
                error=str(r),
            ))
        else:
            processed_results.append(r)

    # Merge results
    merged = merge_beta_results(processed_results, model_info.fields)

    # Attach raw content from original OCR
    merged["raw_content"] = ocr_data.get("content", "")
    merged["raw_tables"] = ocr_data.get("tables", [])

    return merged


async def _single_call_extraction(
    ocr_data: Dict[str, Any],
    model_info: Any,
    language: str,
) -> Dict[str, Any]:
    """Single-call beta extraction (no chunking). Uses LayoutParser + RefinerEngine."""
    from app.services.layout_parser import LayoutParser
    from app.services.refiner import RefinerEngine
    from app.services.llm import call_llm_single

    # Stage diagnostics — will be surfaced in debug panel
    stages = {}

    try:
        # Stage 1: LayoutParser
        # OPTIMIZATION: Check for bypass (Excel/CSV)
        if ocr_data.get("_layout_parser_bypass"):
            logger.info("[BetaSingle] LayoutParser bypassed (Excel/CSV optimization)")
            content_text = ocr_data.get("content", "")
            ref_map = {}
            stages["1_layout_parser"] = {
                "status": "bypassed",
                "content_chars": len(content_text),
                "info": "Excel/CSV Optimized Prop"
            }
        else:
            parser = LayoutParser(ocr_data)
            content_text, ref_map = parser.parse()
            stages["1_layout_parser"] = {
                "status": "ok",
                "content_chars": len(content_text),
                "ref_map_count": len(ref_map),
                "content_preview": content_text[:200] if content_text else "(empty)",
            }
            logger.info(f"[BetaSingle] Stage 1 OK: {len(content_text)} chars, {len(ref_map)} refs")

        # Guard: If content is empty
        if not content_text or not content_text.strip():
             return {
                "guide_extracted": {},
                "error": "No content text available (Empty Document)",
                "_beta_parsed_content": "",
                "raw_content": ocr_data.get("content", ""),
            }

        # Stage 2: Prompt construction
        system_prompt = RefinerEngine.construct_prompt(model_info, language)

        # OPTIMIZATION: Skip redundant table context for Excel
        if ocr_data.get("_layout_parser_bypass"):
            tables_context = ""
        else:
            tables_context = _build_tables_context(ocr_data.get("tables", []))

        user_prompt = f"Document Text:\n{content_text}\n{tables_context}"
        stages["2_prompt"] = {
            "status": "ok",
            "system_prompt_chars": len(system_prompt),
            "user_prompt_chars": len(user_prompt),
            "field_count": len(model_info.fields) if hasattr(model_info, 'fields') else 0,
            "field_keys": [f.key for f in model_info.fields][:10] if hasattr(model_info, 'fields') else [],
        }
        logger.info(f"[BetaSingle] Stage 2 OK: sys={len(system_prompt)}, user={len(user_prompt)} chars")

        # TOKEN AUDIT: Accurate token counting for optimization
        try:
            from app.services.token_audit import audit_prompt
            audit = audit_prompt(system_prompt, user_prompt)
            stages["2_token_audit"] = {
                "system_tokens": audit["system_tokens"],
                "user_tokens": audit["user_tokens"],
                "total_est": audit["total"],
                "tab_waste": audit["tab_count"],
                "recommendations": audit["recommendations"][:3],
            }
            logger.info(f"[BetaSingle] TOKEN AUDIT:\n{audit['summary']}")
        except Exception:
            pass  # Non-fatal

        # Stage 3: LLM call
        llm_response = await call_llm_single(system_prompt, user_prompt, model_info=model_info)

        if "error" in llm_response:
            stages["3_llm_call"] = {
                "status": "error",
                "error": llm_response["error"][:500],
            }
            logger.error(f"[BetaSingle] Stage 3 FAILED: {llm_response['error'][:200]}")
            return {
                "guide_extracted": {},
                "error": llm_response["error"],
                "_beta_parsed_content": content_text,
                "_beta_ref_map": ref_map or {},
                "_token_usage": llm_response.get("_token_usage"),
                "_beta_pipeline_stages": stages,
                "raw_content": ocr_data.get("content", ""),
                "raw_tables": ocr_data.get("tables", []),
            }

        llm_json = llm_response.get("result", {})
        stages["3_llm_call"] = {
            "status": "ok",
            "raw_keys": list(llm_json.keys())[:15],
            "raw_key_count": len(llm_json.keys()),
            "response_preview": str(llm_json)[:500],
            "token_usage": llm_response.get("_token_usage"),
        }
        logger.info(f"[BetaSingle] Stage 3 OK: {len(llm_json)} keys, preview: {str(llm_json)[:200]}")

        # Stage 4: Normalize
        normalized = normalize_llm_response(llm_json, model_info)
        stages["4_normalize"] = {
            "status": "ok",
            "input_keys": list(llm_json.keys())[:10],
            "output_keys": list(normalized.keys())[:10],
            "fields_recovered": len(normalized),
            "is_table": normalized.get("_is_table", False),
        }
        logger.info(f"[BetaSingle] Stage 4 OK: {len(llm_json)} raw → {len(normalized)} normalized")

        # TABLE MODE: skip bbox post-processing, pass rows directly
        if normalized.get("_is_table"):
            table_rows = normalized.get("_table_rows", [])
            stages["5_post_process"] = {
                "status": "skipped (table mode)",
                "row_count": len(table_rows),
            }
            logger.info(f"[BetaSingle] Stage 5 SKIPPED (table mode): {len(table_rows)} rows")

            return {
                "guide_extracted": table_rows,
                "_is_table": True,
                "other_data": [],
                "_beta_parsed_content": f"{content_text}\n{tables_context}" if tables_context else content_text,
                "_beta_ref_map": ref_map or {},
                "_token_usage": llm_response.get("_token_usage"),
                "_beta_pipeline_stages": stages,
                "raw_content": ocr_data.get("content", ""),
                "raw_tables": ocr_data.get("tables", []),
            }

        # Stage 5: Post-process (bbox matching) — standard mode only
        processed = RefinerEngine.post_process_result(normalized, ocr_data)
        stages["5_post_process"] = {
            "status": "ok",
            "output_keys": list(processed.keys())[:10],
            "fields_with_values": sum(1 for v in processed.values() if isinstance(v, dict) and v.get("value") is not None),
            "fields_null": sum(1 for v in processed.values() if isinstance(v, dict) and v.get("value") is None),
        }
        logger.info(
            f"[BetaSingle] Stage 5 OK: {stages['5_post_process']['fields_with_values']} with values, "
            f"{stages['5_post_process']['fields_null']} null"
        )

        return {
            "guide_extracted": processed,
            "other_data": [],
            "_beta_parsed_content": f"{content_text}\n{tables_context}" if tables_context else content_text,
            "_beta_ref_map": ref_map or {},
            "_token_usage": llm_response.get("_token_usage"),
            "_beta_pipeline_stages": stages,
            "raw_content": ocr_data.get("content", ""),
            "raw_tables": ocr_data.get("tables", []),
        }

    except Exception as e:
        logger.error(f"[BetaSingle] Failed: {e}", exc_info=True)
        stages["exception"] = {"error": str(e)[:500]}
        return {
            "guide_extracted": {},
            "error": str(e),
            "_beta_parsed_content": "",  # Safe empty string
            "_beta_ref_map": {},
            "_beta_pipeline_stages": stages,
            "raw_content": ocr_data.get("content", ""),
            "raw_tables": ocr_data.get("tables", []),
        }

