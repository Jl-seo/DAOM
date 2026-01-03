from typing import List, Dict, Any, Optional
from enum import Enum
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeResult
from azure.core.credentials import AzureKeyCredential
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class AzureModelType(str, Enum):
    """
    Supported Azure Document Intelligence Models
    """
    LAYOUT = "prebuilt-layout"
    READ = "prebuilt-read"
    INVOICE = "prebuilt-invoice"
    RECEIPT = "prebuilt-receipt"
    ID_DOCUMENT = "prebuilt-idDocument"

def get_supported_models() -> List[Dict[str, str]]:
    """Return list of supported models for frontend"""
    return [
        {"id": m.value, "name": f"{m.name} ({m.value})"} 
        for m in AzureModelType
    ]

def get_document_client() -> DocumentIntelligenceClient:
    return DocumentIntelligenceClient(
        endpoint=settings.AZURE_FORM_ENDPOINT,
        credential=AzureKeyCredential(settings.AZURE_FORM_KEY)
    )

def extract_with_strategy(file_source: Any, model_type: str = "prebuilt-layout") -> Dict[str, Any]:
    """
    Universal extraction, strategy determined by model_type.
    file_source: str (URL) or bytes/stream
    """
    client = get_document_client()
    
    logger.info(f"[DocIntel] Analyzing document using model {model_type}")
    
    try:
        # Check if file_source is a string (URL)
        if isinstance(file_source, str):
            poller = client.begin_analyze_document(
                model_id=model_type,
                body={"urlSource": file_source}
            )
        else:
            # Assume bytes/stream
            # Azure SDK v1.0.0b1 uses 'body' for binary content
            poller = client.begin_analyze_document(
                model_id=model_type,
                body=file_source,
                content_type="application/octet-stream"
            )
            
        result: AnalyzeResult = poller.result()
        
        # Base extraction (Always available)
        output = {
            "content": result.content,
            "pages": _process_pages(result.pages),
            "tables": _process_tables(result.tables),
            "key_value_pairs": _process_kv_pairs(result.key_value_pairs, result.pages),
            "documents": _process_documents(result.documents, result.pages) # Pass pages for normalization
        }

        # Strategy-Specific Enrichment (e.g., if Invoice, map specific fields to top level)
        if model_type == AzureModelType.INVOICE:
             output["invoice_metadata"] = _map_invoice_fields(result.documents)
             
        return output

    except Exception as e:
        logger.error(f"[DocIntel] Error: {e}")
        raise e

def _process_pages(pages):
    if not pages: return []
    processed = []
    for page in pages:
        processed.append({
            "page_number": page.page_number,
            "width": page.width,
            "height": page.height,
            "unit": page.unit,
            "words": [{"content": w.content, "polygon": w.polygon, "confidence": w.confidence} for w in (page.words or [])],
             # Helpful for detecting checkboxes in forms
            "selection_marks": [{"state": m.state, "polygon": m.polygon} for m in (page.selection_marks or [])]
        })
    return processed

def _process_tables(tables):
    if not tables: return []
    processed = []
    for table in tables:
        cells = [{
            "row_index": c.row_index, "column_index": c.column_index, 
            "content": c.content, "kind": getattr(c, "kind", "content")
        } for c in table.cells]
        processed.append({"row_count": table.row_count, "column_count": table.column_count, "cells": cells})
    return processed

def _process_kv_pairs(kv_pairs, pages=None):
    if not kv_pairs: return []
    
    # Create page map for dimension lookup
    page_map = {p.page_number: p for p in (pages or [])}
    
    processed = []
    for k in kv_pairs:
        if not k.key: continue
        
        item = {
            "key": k.key.content,
            "value": k.value.content if k.value else "",
            "confidence": k.confidence
        }
        
        # Extract bbox from value (preferred) or key
        target_region = None
        if k.value and k.value.bounding_regions:
            target_region = k.value.bounding_regions[0]
        elif k.key.bounding_regions:
            target_region = k.key.bounding_regions[0]
            
        if target_region:
            p_num = target_region.page_number
            if p_num in page_map:
                page = page_map[p_num]
                # Normalize polygon to percentages - DISABLED: Retain RAW coordinates for consistent processing
                if poly and len(poly) >= 4:
                    xs = poly[0::2]
                    ys = poly[1::2]
                    min_x, max_x = min(xs), max(xs)
                    min_y, max_y = min(ys), max(ys)
                    
                    item["bbox"] = [min_x, min_y, max_x, max_y]
                    item["page_number"] = p_num

        processed.append(item)
    return processed

def _process_documents(documents, pages=None):
    """
    Extracts high-level fields from prebuilt models with normalized BBox.
    """
    if not documents: return []
    
    # Create page map for quick lookup {page_number: page_obj}
    page_map = {p.page_number: p for p in (pages or [])}

    processed = []
    for doc in documents:
        fields = {}
        if doc.fields:
            for key, field in doc.fields.items():
                field_data = {
                    "value": field.value_string or field.value_number or field.value_date or field.content,
                    "type": field.type,
                    "confidence": field.confidence
                }
                
                # Extract and normalize bounding box
                try:
                    if field.bounding_regions:
                        # Use first region
                        region = field.bounding_regions[0]
                        p_num = region.page_number
                        
                        if p_num in page_map:
                            page = page_map[p_num]
                            p_w = page.width
                            p_h = page.height
                            
                            # Polygon: [x1, y1, x2, y2, x3, y3, x4, y4] (Inches/Pixels)
                            poly = region.polygon
                            if poly and len(poly) >= 4:
                                xs = poly[0::2]
                                ys = poly[1::2]
                                min_x, max_x = min(xs), max(xs)
                                min_y, max_y = min(ys), max(ys)
                                
                                # Use Raw Coordinates
                                field_data["bbox"] = [min_x, min_y, max_x, max_y]
                                field_data["page_number"] = p_num
                except Exception as e:
                    logger.warning(f"Failed to extract bbox for field {key}: {e}")

                fields[key] = field_data
        
        # Extract page numbers from bounding regions
        page_numbers = []
        if doc.bounding_regions:
            # Azure page numbers are 1-based
            page_numbers = sorted(list(set(r.page_number for r in doc.bounding_regions)))
            
        processed.append({
            "doc_type": doc.doc_type,
            "fields": fields,
            "page_numbers": page_numbers, 
            "confidence": doc.confidence
        })
    return processed

def _map_invoice_fields(documents):
    """
    Helper to flatten specific Invoice fields for easier consumption
    """
    if not documents: return {}
    doc = documents[0] # Assume single invoice per file for now
    fields = doc.fields
    if not fields: return {}
    
    return {
        "vendor_name": fields.get("VendorName", {}).get("content"),
        "customer_name": fields.get("CustomerName", {}).get("content"),
        "invoice_total": fields.get("InvoiceTotal", {}).get("content"),
        "invoice_date": fields.get("InvoiceDate", {}).get("content"),
        "invoice_id": fields.get("InvoiceId", {}).get("content"),
    }

# --- Backward Compatibility Maps ---
def extract_content_from_url(file_url: str):
    return extract_with_strategy(file_url, AzureModelType.LAYOUT)

def extract_full_preview(file_url: str):
    return extract_with_strategy(file_url, AzureModelType.LAYOUT)
