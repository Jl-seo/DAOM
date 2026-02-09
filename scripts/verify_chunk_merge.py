
import logging
from typing import List, Dict, Any
from app.services.chunked_extraction import merge_chunk_results, ChunkResult

# Mock Logger to see output
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_merge_logic():
    print("--- Testing Key-Value List Merge Logic ---")
    
    # Mock Schema Fields
    model_fields = [
        {"key": "invoice_no", "type": "text"},
        {"key": "line_items", "type": "list"} # Table field
    ]
    
    # Scenario 1: Good Merge
    # Chunk 1: Header + 1 Item
    # Chunk 2: No Header + 1 Item
    
    chunk1_data = {
        "guide_extracted": {
            "invoice_no": {"value": "INV-001", "confidence": 0.9, "bbox": None, "page_number": 1},
            "line_items": {"value": [{"id": "1", "desc": "Item A"}], "confidence": 0.9, "bbox": None, "page_number": 1}
        },
        "_pages": [1]
    }
    
    chunk2_data = {
        "guide_extracted": {
            "invoice_no": {"value": None, "confidence": 0.0, "bbox": None, "page_number": 2}, # Header missing/null
            "line_items": {"value": [{"id": "2", "desc": "Item B"}], "confidence": 0.9, "bbox": None, "page_number": 2}
        },
        "_pages": [2]
    }
    
    results = [
        ChunkResult(chunk_index=0, success=True, extracted_data=chunk1_data),
        ChunkResult(chunk_index=1, success=True, extracted_data=chunk2_data)
    ]
    
    merged, errors = merge_chunk_results(results, model_fields)
    
    print(f"Merged Result Keys: {merged.keys()}")
    
    # Check Invoice No
    inv = merged.get("invoice_no", {}).get("value")
    print(f"Invoice No: {inv} (Expected: INV-001)")
    
    # Check Line Items
    items = merged.get("line_items", {}).get("value")
    print(f"Line Items Count: {len(items) if items else 0} (Expected: 2)")
    if items:
        print(f"Items: {items}")
        
    assert inv == "INV-001", "Invoice Number Validation Failed"
    assert len(items) == 2, "Line Items Count Validation Failed"
    print("✅ TEST PASSED: List Extension Logic Works")

if __name__ == "__main__":
    test_merge_logic()
