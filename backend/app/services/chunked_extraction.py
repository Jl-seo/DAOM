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
MAX_TOKENS_PER_CHUNK = 2000
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
    token_estimate: int


@dataclass
class ChunkResult:
    """Result from processing a single chunk"""
    chunk_index: int
    success: bool
    extracted_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


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
            token_estimate=estimate_tokens(content)
        )]
    
    chunks: List[Chunk] = []
    current_chunk_pages: List[int] = []
    current_chunk_content = ""
    current_chunk_paragraphs: List[Dict] = []
    current_chunk_tables: List[Dict] = []
    
    for page in pages:
        page_num = page.get("pageNumber", 1)
        
        # Get content for this page
        page_paragraphs = [p for p in paragraphs 
                          if any(br.get("page_number") == page_num 
                                for br in p.get("bounding_regions", []))]
        page_tables = [t for t in tables 
                       if any(br.get("page_number") == page_num 
                             for br in t.get("bounding_regions", []))]
        
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
                token_estimate=current_tokens
            ))
            current_chunk_pages = []
            current_chunk_content = ""
            current_chunk_paragraphs = []
            current_chunk_tables = []
        
        # Add page to current chunk
        current_chunk_pages.append(page_num)
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
            # Build prompt for this chunk
            fields_str = json.dumps(model_fields, ensure_ascii=False)
            prompt = f"""다음 문서에서 필드 정보를 추출하세요.

필드 목록:
{fields_str}

문서 내용 (페이지 {chunk.page_numbers}):
{chunk.content}

JSON 형식으로만 응답하세요. 해당 페이지에 없는 필드는 null로 표시하세요.
{{"field_name": "extracted_value", ...}}"""

            response = await client.chat.completions.create(
                model=deployment,
                messages=[
                    {"role": "system", "content": "You are a document extraction assistant. Extract field values from the given document. Respond only with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=2000
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Parse JSON response
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
            
            extracted = json.loads(result_text)
            
            # Add page metadata
            extracted["_chunk_index"] = chunk.index
            extracted["_pages"] = chunk.page_numbers
            
            logger.info(f"[Chunk {chunk.index}] Successfully processed pages {chunk.page_numbers}")
            
            return ChunkResult(
                chunk_index=chunk.index,
                success=True,
                extracted_data=extracted
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
    For duplicate fields, take the first non-null value.
    Returns (merged_data, errors_list)
    """
    merged: Dict[str, Any] = {}
    field_sources: Dict[str, int] = {}  # Track which page gave us each field
    errors: List[str] = []
    
    # Sort results by chunk index to maintain order
    sorted_results = sorted(results, key=lambda r: r.chunk_index)
    
    for result in sorted_results:
        if not result.success:
            errors.append(f"Chunk {result.chunk_index} failed: {result.error}")
            continue
        
        if not result.extracted_data:
            continue
        
        chunk_data = result.extracted_data
        pages = chunk_data.get("_pages", [])
        
        for key, value in chunk_data.items():
            if key.startswith("_"):  # Skip metadata
                continue
            
            # Take first non-null value for each field
            if key not in merged or merged[key] is None:
                if value is not None:
                    merged[key] = value
                    field_sources[key] = pages[0] if pages else 0
    
    # Add metadata about merge
    merged["_merge_info"] = {
        "total_chunks": len(results),
        "successful_chunks": sum(1 for r in results if r.success),
        "field_sources": field_sources
    }
    
    success_rate = sum(1 for r in results if r.success) / len(results) if results else 0
    logger.info(f"[Merge] Merged {len(merged)} fields from {len(results)} chunks (success rate: {success_rate:.0%})")
    
    return merged, errors


async def extract_with_chunking(
    doc_intel_output: Dict[str, Any],
    model_fields: List[Dict[str, Any]],
    max_tokens_per_chunk: int = MAX_TOKENS_PER_CHUNK,
    max_concurrent: int = 3
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
