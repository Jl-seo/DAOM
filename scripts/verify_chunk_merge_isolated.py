
import sys
from unittest.mock import MagicMock

# Mock OpenAI before import
sys.modules["openai"] = MagicMock()
sys.modules["openai.AsyncAzureOpenAI"] = MagicMock()
sys.modules["app.core.config"] = MagicMock()
sys.modules["app.core.config"].settings = MagicMock()
sys.modules["app.core.config"].settings.LLM_CHUNK_MAX_TOKENS = 8000
sys.modules["app.core.config"].settings.LLM_DEFAULT_TEMPERATURE = 0.0
sys.modules["app.core.config"].settings.LLM_DEFAULT_MAX_TOKENS = 4000
sys.modules["app.services.refiner"] = MagicMock() # Avoid refiner import if used

# Now import the logic we want to test
# We need to manually import chunked_extraction.py because it's inside app/services
import os
sys.path.append(os.getcwd())

from backend.app.services.chunked_extraction import merge_chunk_results, ChunkResult

def test_merge_logic():
    print("--- Testing List Merge Logic (Isolated) ---")
    
    # Mock Schema Fields
    model_fields = [
        {"key": "invoice_no", "type": "text"},
        {"key": "line_items", "type": "list"} 
    ]
    
    # Chunk 1: Header + 1 Item
    chunk1_data = {
        "guide_extracted": {
            "invoice_no": {"value": "INV-001", "confidence": 0.9, "bbox": None, "page_number": 1},
            "line_items": {"value": [{"id": "1", "desc": "Item A"}], "confidence": 0.9, "bbox": None, "page_number": 1}
        },
        "_pages": [1]
    }
    
    # Chunk 2: No Header + 1 Item
    chunk2_data = {
        "guide_extracted": {
            "invoice_no": {"value": None, "confidence": 0.0, "bbox": None, "page_number": 2}, 
            "line_items": {"value": [{"id": "2", "desc": "Item B"}], "confidence": 0.9, "bbox": None, "page_number": 2}
        },
        "_pages": [2]
    }
    
    results = [
        ChunkResult(chunk_index=0, success=True, extracted_data=chunk1_data),
        ChunkResult(chunk_index=1, success=True, extracted_data=chunk2_data)
    ]
    
    merged, errors = merge_chunk_results(results, model_fields)
    
    inv = merged.get("invoice_no", {}).get("value")
    items = merged.get("line_items", {}).get("value")
    
    print(f"Invoice No: {inv}")
    print(f"Items Count: {len(items) if items else 0}")
    if items:
        print(f"Items: {items}")

    if len(items) == 2:
        print("✅ SUCCESS: Items merged correctly!")
    else:
        print("❌ FAILURE: Items were NOT merged.")

if __name__ == "__main__":
    test_merge_logic()
