"""
Document Splitter Service
Responsible for detecting and splitting a single file into multiple logical documents.
Strategy:
1. Azure Native: Check `doc_intel_result.documents` for pre-detected splits.
2. GPT Fallback: If 1 doc but multiple pages, ask GPT to analyze page boundaries.
"""
from typing import List, Dict, Any
import json
import logging
from app.core.config import settings
from openai import AsyncAzureOpenAI

logger = logging.getLogger(__name__)

class DocumentSplit(Dict[str, Any]):
    """Represents a logical sub-document within a file"""
    # Type definition for clarity (runtime is dict)
    # {
    #   "index": 1,
    #   "page_ranges": [1, 2],
    #   "confidence": 0.9,
    #   "type": "invoice"
    # }
    pass

async def detect_and_split(doc_intel_result: Dict[str, Any], file_url: str) -> List[Dict[str, Any]]:
    """
    Main entry point. Analyzes extraction result and returns list of sub-documents.
    Always returns at least one document (the whole file).
    """

    # 1. Check Azure's Native Detection
    azure_splits = _split_by_azure(doc_intel_result)
    if len(azure_splits) > 1:
        logger.info(f"[Splitter] Azure detected {len(azure_splits)} documents.")
        return azure_splits

    # 2. Check Page Count
    total_pages = len(doc_intel_result.get("pages", []))
    if total_pages <= 2:
        # If 1-2 pages and Azure didn't split, assume it's single doc.
        # (Cost optimization: Don't call GPT for everything)
        logger.info("[Splitter] Single document assummed (pages <= 2).")
        return [_create_single_split(total_pages)]

    # 3. GPT Fallback for Multi-page Single-doc result
    logger.info(f"[Splitter] Azure found 1 doc, but file has {total_pages} pages. Attempting GPT split.")
    gpt_splits = await _split_by_gpt(doc_intel_result)

    if gpt_splits and len(gpt_splits) > 1:
        logger.info(f"[Splitter] GPT detected {len(gpt_splits)} documents.")
        return gpt_splits

    logger.info("[Splitter] GPT confirmed single document.")
    return [_create_single_split(total_pages)]


def _split_by_azure(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract splits from Azure 'documents' field"""
    documents = result.get("documents", [])
    if not documents:
        return []

    # Check if we have meaningful splits
    # Azure Layout often returns 1 doc covering all pages.
    if len(documents) <= 1:
        return []

    splits = []
    for idx, doc in enumerate(documents):
        page_numbers = doc.get("page_numbers", [])
        if not page_numbers:
            continue

        splits.append({
            "index": idx + 1,
            "page_ranges": page_numbers,
            "type": doc.get("doc_type", "document"),
            "confidence": doc.get("confidence", 1.0)
        })

    # Validation: Ensure splits cover meaningful pages?
    # For now, trust Azure if it returns > 1 docs.
    return splits

async def _split_by_gpt(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Use configured LLM to analyze page content and suggest splits"""
    try:
        pages = result.get("pages", [])
        content = result.get("content", "")

        # Construct lightweight page summaries for prompt context
        page_summaries = []
        for p in pages:
            p_num = p.get("page_number", 0)
            # Extract first 300 characters of text for this page
            # This is an approximation since 'content' is global.
            # Ideally we iterate words filter by page, but that's expensive.
            # Alternative: doc_intel.py pages already have words.
            words = p.get("words", [])
            page_text = " ".join([w["content"] for w in words])[:500] # First 500 chars
            page_summaries.append(f"Page {p_num}: {page_text}...")

        prompt = f"""
        Analyze these {len(pages)} pages of document text. 
        Determine if they represent a SINGLE logical document (like a multi-page agreement) 
        or MULTIPLE separate documents merged together (like 3 different invoices).
        
        Page Summaries:
        {chr(10).join(page_summaries)}
        
        Return JSON Object:
        {{
            "is_multiple": boolean,
            "documents": [
                {{ "index": 1, "start_page": 1, "end_page": 1, "type": "invoice" }},
                {{ "index": 2, "start_page": 2, "end_page": 4, "type": "contract" }}
            ]
        }}
        
        Rules:
        - If uncertain, default to is_multiple: false.
        - Ensure all pages are covered.
        """

        client = AsyncAzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT
        )

        from app.services.llm import get_current_model

        response = await client.chat.completions.create(
            model=get_current_model(),
            messages=[
                {"role": "system", "content": "You are a document splitting expert. Return valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            temperature=settings.LLM_DEFAULT_TEMPERATURE
        )

        res_json = json.loads(response.choices[0].message.content)

        if not res_json.get("is_multiple"):
            return []

        # Convert to standard format
        splits = []
        for d in res_json.get("documents", []):
            start = d.get("start_page")
            end = d.get("end_page")
            splits.append({
                "index": d.get("index"),
                "page_ranges": list(range(start, end + 1)),
                "type": d.get("type", "document")
            })

        return splits

    except Exception as e:
        logger.error(f"[Splitter] GPT failed: {e}")
        return []

def _create_single_split(total_pages: int) -> Dict[str, Any]:
    return {
        "index": 1,
        "page_ranges": list(range(1, total_pages + 1)),
        "type": "document"
    }
