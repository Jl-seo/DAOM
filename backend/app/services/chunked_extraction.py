"""
Chunked Extraction Service

Handles large documents by:
1. Chunking Document Intelligence output by pages
2. Parallel async processing with Azure OpenAI
3. Result aggregation
4. Retry logic for failed chunks
"""
import asyncio
import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from openai import AsyncAzureOpenAI
from app.core.config import settings

logger = logging.getLogger(__name__)

# Token estimation: ~4 chars per token for mixed content
CHARS_PER_TOKEN = 4
MAX_TOKENS_PER_CHUNK = 4000
MAX_CHARS_PER_CHUNK = MAX_TOKENS_PER_CHUNK * CHARS_PER_TOKEN  # ~8000 chars

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY_BASE = 2  # seconds, exponential backoff


@dataclass
class Chunk:
    """Represents a chunk of document data"""
    index: int
    page_numbers: List[int]
    content: str
    paragraphs: List[Dict[str, Any]]
    tables: List[Dict[str, Any]]
    pages_data: List[Dict[str, Any]] # High fidelity data including words
    token_estimate: int


@dataclass
class ChunkResult:
    """Result from processing a single chunk"""
    chunk_index: int
    success: bool
    extracted_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    debug_info: Optional[Dict[str, Any]] = None  # LLM prompt/response for debugging


def estimate_tokens(text: str) -> int:
    """Estimate token count from text length"""
    return len(text) // CHARS_PER_TOKEN


def chunk_document_data(doc_intel_output: Dict[str, Any], max_tokens: int = MAX_TOKENS_PER_CHUNK) -> List[Chunk]:
    """
    Split Document Intelligence output into chunks based on pages.
    Each chunk stays under max_tokens.
    """
    pages = doc_intel_output.get("pages", [])
    paragraphs = doc_intel_output.get("paragraphs", [])
    tables = doc_intel_output.get("tables", [])
    content = doc_intel_output.get("content", "")
    
    if not pages:
        # Single chunk for small documents
        return [Chunk(
            index=0,
            page_numbers=[1],
            content=content,
            paragraphs=paragraphs,
            tables=tables,
            pages_data=pages, # Pass all pages
            token_estimate=estimate_tokens(content)
        )]
    
    chunks: List[Chunk] = []
    current_chunk_pages: List[int] = []
    current_chunk_content = ""
    current_chunk_paragraphs: List[Dict] = []
    current_chunk_tables: List[Dict] = []
    current_chunk_pages_data: List[Dict] = []
    
    for page in pages:
        # IMPORTANT: doc_intel.py uses snake_case "page_number", not camelCase "pageNumber"
        page_num = page.get("page_number") or page.get("pageNumber", 1)
        
        # Get content for this page (handle both snake_case and camelCase keys)
        def get_regions(obj):
            return obj.get("bounding_regions") or obj.get("boundingRegions") or []
            
        def is_on_page(obj, p_num):
            regions = get_regions(obj)
            return any((br.get("page_number") or br.get("pageNumber")) == p_num for br in regions)

        page_paragraphs = [p for p in paragraphs if is_on_page(p, page_num)]
        page_tables = [t for t in tables if is_on_page(t, page_num)]
        
        page_content = "\n".join([p.get("content", "") for p in page_paragraphs])
        page_tokens = estimate_tokens(page_content)
        
        # Check if adding this page exceeds limit
        current_tokens = estimate_tokens(current_chunk_content)
        
        if current_tokens + page_tokens > max_tokens and current_chunk_pages:
            # Save current chunk and start new one
            chunks.append(Chunk(
                index=len(chunks),
                page_numbers=current_chunk_pages.copy(),
                content=current_chunk_content,
                paragraphs=current_chunk_paragraphs.copy(),
                tables=current_chunk_tables.copy(),
                pages_data=current_chunk_pages_data.copy(),
                token_estimate=current_tokens
            ))
            current_chunk_pages = []
            current_chunk_pages_data = [] # Reset pages data
            current_chunk_content = ""
            current_chunk_paragraphs = []
            current_chunk_tables = []
        
        # Add page to current chunk
        current_chunk_pages.append(page_num)
        current_chunk_pages_data.append(page.copy()) # Collect high-fidelity page data
        current_chunk_content += f"\n--- Page {page_num} ---\n{page_content}"
        current_chunk_paragraphs.extend(page_paragraphs)
        current_chunk_tables.extend(page_tables)
    
    # Don't forget the last chunk
    if current_chunk_pages:
        chunks.append(Chunk(
            index=len(chunks),
            page_numbers=current_chunk_pages,
            content=current_chunk_content,
            paragraphs=current_chunk_paragraphs,
            tables=current_chunk_tables,
            pages_data=current_chunk_pages_data,
            token_estimate=estimate_tokens(current_chunk_content)
        ))
    
    logger.info(f"[Chunking] Split document into {len(chunks)} chunks")
    for i, chunk in enumerate(chunks):
        logger.info(f"  Chunk {i}: pages {chunk.page_numbers}, ~{chunk.token_estimate} tokens")
    
    return chunks


async def process_chunk_with_retry(
    client: AsyncAzureOpenAI,
    chunk: Chunk,
    model_fields: List[Dict[str, Any]],
    deployment: str,
    max_retries: int = MAX_RETRIES
) -> ChunkResult:
    """
    Process a single chunk with retry logic and exponential backoff.
    """
    last_error = None
    
    for attempt in range(max_retries):
        try:
            # Build prompt for this chunk - USES HIGH FIDELITY ENGLISH PROMPT
            # Converted fields to list of descriptions
            field_descriptions = []
            for field in model_fields:
                desc = f"- {field.get('key')}: {field.get('label')}"
                if field.get('description'):
                    desc += f" ({field.get('description')})"
                field_descriptions.append(desc)

            fields_block = "\n".join(field_descriptions)

            # Prepare Lean Data for Prompt
            # Use text content + tables (with cell bboxes) - NOT full pages_data (too heavy)
            doc_context = chunk.content
            
            # DEBUG: Log table data being sent
            tables_to_use = chunk.tables if chunk.tables else []
            logger.info(f"[Chunk {chunk.index}] Tables count: {len(tables_to_use)}, Content length: {len(chunk.content)}")
            
            if tables_to_use:
                doc_context += f"\n\n--- TABLES DATA ---\n{json.dumps(tables_to_use, ensure_ascii=False)}"
            else:
                logger.warning(f"[Chunk {chunk.index}] No tables in chunk! This may cause null extractions.")

            prompt = f"""You are a document data extractor capable of processing Korean and English documents.

Given this document data extracted from pages {chunk.page_numbers}:
{doc_context}

Extract values for these specific fields:
{fields_block}

INSTRUCTIONS:
1. Analyze the document context. Content may be in Korean.
2. For specific fields like 'Item' (품목) or 'Amount' (금액), look for corresponding headers in the table or text.
3. If a field represents a list of items (e.g. line items in a table), extract it as a JSON Array.
4. Distinguish between 'Item' (product code/name) and 'Description' (spec/details).
5. **Key-Value Tables**: If a table has a structure like [Field Name | Value], map the 'Value' column to the corresponding requested field.
6. **CRITICAL**: Extract values EXACTLY as they appear in the text.
7. **CRITICAL**: You MUST include the 'bbox' (bounding box) for every extracted value. Copy it exactly from source (ocr data) if available.
8. **CRITICAL**: You MUST include the 'page_number' (1-based index) for every extracted value.

Return a JSON object with:
1. "guide_extracted": Object with each field key containing:
   - "value": The extracted value exactly as in text
   - "confidence": Your confidence level from 0.0 to 1.0
   - "bbox": [x1, y1, x2, y2] or null
   - "page_number": The page number
2. "other_data": Array of other noteworthy data found.

IMPORTANT:
- Use exact field keys.
- If value is not found, set value to null.
- Return ONLY valid JSON."""

            response = await client.chat.completions.create(
                model=deployment,
                messages=[
                    {"role": "system", "content": "You are a precise document data extractor. The user needs to verify your work, so you must return bounding boxes and page numbers if available. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # DEBUG: Log prompt size and response
            logger.info(f"[Chunk {chunk.index}] Prompt size: {len(prompt)} chars, Response size: {len(result_text)} chars")
            logger.info(f"[Chunk {chunk.index}] LLM Response preview: {result_text[:500]}...")
            
            # Parse JSON response
            extracted = json.loads(result_text)
            
            # Normalize structure if LLM responds weirdly (sometimes returns list)
            if "guide_extracted" not in extracted:
                 # Try to see if it's the old flat format or something else
                 # If it looks like flat key-values, wrap it
                 if not any(k in ["guide_extracted", "other_data"] for k in extracted.keys()):
                     extracted = {"guide_extracted": extracted}

            guide = extracted.get("guide_extracted", {})
            
            # Ensure every field in guide is an object
            for k, v in guide.items():
                if not isinstance(v, dict):
                    guide[k] = {
                        "value": v,
                        "confidence": 0.5,
                        "bbox": None,
                        "page_number": chunk.page_numbers[0] if chunk.page_numbers else 1
                    }
            
            extracted["guide_extracted"] = guide
            
            # Add page metadata
            extracted["_chunk_index"] = chunk.index
            extracted["_pages"] = chunk.page_numbers
            
            logger.info(f"[Chunk {chunk.index}] Successfully processed pages {chunk.page_numbers}")
            
            return ChunkResult(
                chunk_index=chunk.index,
                success=True,
                extracted_data=extracted,
                debug_info={
                    "prompt_size": len(prompt),
                    "response_size": len(result_text),
                    "response_preview": result_text[:1000],
                    "doc_context_preview": doc_context[:500] if doc_context else "",
                    "tables_count": len(tables_to_use)
                }
            )
            
        except Exception as e:
            last_error = str(e)
            logger.warning(f"[Chunk {chunk.index}] Attempt {attempt + 1} failed: {last_error}")
            
            if "429" in str(e) or "rate" in str(e).lower():
                # Rate limit - wait longer
                wait_time = RETRY_DELAY_BASE * (2 ** attempt) * 2
                logger.info(f"[Chunk {chunk.index}] Rate limited, waiting {wait_time}s")
                await asyncio.sleep(wait_time)
            elif attempt < max_retries - 1:
                # Other error - standard backoff
                wait_time = RETRY_DELAY_BASE * (2 ** attempt)
                await asyncio.sleep(wait_time)
    
    return ChunkResult(
        chunk_index=chunk.index,
        success=False,
        error=f"Failed after {max_retries} attempts: {last_error}"
    )


async def process_chunks_parallel(
    chunks: List[Chunk],
    model_fields: List[Dict[str, Any]],
    max_concurrent: int = 3
) -> List[ChunkResult]:
    """
    Process multiple chunks in parallel with concurrency limit.
    """
    client = AsyncAzureOpenAI(
        api_key=settings.AZURE_OPENAI_API_KEY,
        api_version=settings.AZURE_OPENAI_API_VERSION,
        azure_endpoint=settings.AZURE_OPENAI_ENDPOINT
    )
    
    # Use dynamic model from admin settings
    from app.services.llm import get_current_model
    deployment = get_current_model()
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def process_with_semaphore(chunk: Chunk) -> ChunkResult:
        async with semaphore:
            return await process_chunk_with_retry(client, chunk, model_fields, deployment)
    
    logger.info(f"[Parallel] Processing {len(chunks)} chunks with max {max_concurrent} concurrent")
    
    tasks = [process_with_semaphore(chunk) for chunk in chunks]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Handle any unexpected exceptions
    processed_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            processed_results.append(ChunkResult(
                chunk_index=i,
                success=False,
                error=str(result)
            ))
        else:
            processed_results.append(result)
    
    return processed_results


def merge_chunk_results(
    results: List[ChunkResult],
    model_fields: List[Dict[str, Any]]
) -> Tuple[Dict[str, Any], List[str]]:
    """
    Merge results from multiple chunks into a single coherent result.
    For duplicate fields, take the best value (highest confidence or first non-null).
    Returns (merged_flat_data, errors_list) - Note: returning flat data with structure!
    
    Wait, the caller (extraction_service) expects:
    { "field_key": "value" ... } ? 
    NO, extraction_service._unwrap_llm_extraction fallback returns:
    {
        "guide_extracted": {k: {"value": v ...}},
        "other_data": ...
    }
    
    So we should return a dictionary suitable for that structure.
    """
    merged_guide: Dict[str, Any] = {}
    merged_other: List[Any] = []
    field_sources: Dict[str, int] = {}  # Track which page gave us each field
    errors: List[str] = []
    
    # Sort results by chunk index
    sorted_results = sorted(results, key=lambda r: r.chunk_index)
    
    for result in sorted_results:
        if not result.success:
            errors.append(f"Chunk {result.chunk_index} failed: {result.error}")
            continue
        
        if not result.extracted_data:
            continue
        
        chunk_data = result.extracted_data
        guide = chunk_data.get("guide_extracted", {})
        other = chunk_data.get("other_data", [])
        
        if isinstance(other, list):
            merged_other.extend(other)
            
        pages = chunk_data.get("_pages", [])
        
        for key, item in guide.items():
            # item is expected to be {value, confidence, bbox, page}
            if not isinstance(item, dict): continue
            
            val = item.get("value")
            
            # Strategy: If field not present, take it.
            # If present, only replace if current is null.
            # Actually, we should take non-null over null.
            if key not in merged_guide:
                 merged_guide[key] = item
                 field_sources[key] = item.get("page_number") or (pages[0] if pages else 0)
            else:
                current_val = merged_guide[key].get("value")
                if current_val is None and val is not None:
                    merged_guide[key] = item
                    field_sources[key] = item.get("page_number") or (pages[0] if pages else 0)

    # Add metadata about merge
    # We return the dictionary that will be put INTO 'guide_extracted' by the caller ??
    # Actually extraction_service._unwrap... fallback puts the result of this function:
    # "guide_extracted": {k: {"value": v ...} for k, v in merged_result.items()}
    # Wait, the caller loop in extraction_service needs update too if we change return type.
    # checking extraction_service line 623:
    # "guide_extracted": {k: {"value": v, "confidence": 0.8} for k, v in merged_result.items() if not k.startswith("_")},
    
    # WE MUST CHANGE extraction_service TO ACCEPT THIS RICHER RETURN or CHANGE THIS TO MATCH.
    # The plan says "Update merge_chunk_results Logic to merge the richer object structure".
    # I should change this to return the dictionary of Objects.
    # And I need to update extraction_service to use it directly instead of wrapping it again.
    
    # Collect debug info from chunks
    chunk_debug = []
    for r in sorted_results:
        if r.debug_info:
            chunk_debug.append({
                "chunk_index": r.chunk_index,
                "success": r.success,
                "error": r.error,
                **r.debug_info
            })
    
    merged_guide["_merge_info"] = {
        "total_chunks": len(results),
        "successful_chunks": sum(1 for r in results if r.success),
        "field_sources": field_sources,
        "chunk_debug": chunk_debug  # LLM prompt/response info for each chunk
    }
    
    success_rate = sum(1 for r in results if r.success) / len(results) if results else 0
    logger.info(f"[Merge] Merged {len(merged_guide)} fields from {len(results)} chunks (success rate: {success_rate:.0%})")
    
    return merged_guide, errors


async def extract_with_chunking(
    doc_intel_output: Dict[str, Any],
    model_fields: List[Dict[str, Any]],
    max_tokens_per_chunk: int = 8000, # Increased default
    max_concurrent: int = 8 # Increased default
) -> Tuple[Dict[str, Any], List[str]]:
    """
    Main entry point: Extract data from large document using chunking.
    
    Args:
        doc_intel_output: Raw Document Intelligence output
        model_fields: List of fields to extract
        max_tokens_per_chunk: Target size for each chunk
        max_concurrent: Maximum parallel API calls
    
    Returns:
        Tuple of (merged_results, errors)
    """
    # Step 1: Chunk the document
    chunks = chunk_document_data(doc_intel_output, max_tokens_per_chunk)
    
    if len(chunks) == 1:
        logger.info("[Extract] Small document, processing without chunking")
    else:
        logger.info(f"[Extract] Large document, processing in {len(chunks)} chunks")
    
    # Step 2: Process chunks in parallel
    results = await process_chunks_parallel(chunks, model_fields, max_concurrent)
    
    # Step 3: Merge results
    merged, errors = merge_chunk_results(results, model_fields)
    
    return merged, errors
