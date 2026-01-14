
import sys
import os
import asyncio
from unittest.mock import MagicMock

# Add backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Mock dependencies before import
sys.modules["app.core.config"] = MagicMock()
sys.modules["app.services.llm"] = MagicMock()
sys.modules["app.core.enums"] = MagicMock()
sys.modules["app.services.doc_intel"] = MagicMock()
sys.modules["app.services.models"] = MagicMock()
sys.modules["app.services.extraction_jobs"] = MagicMock()
sys.modules["app.services.extraction_logs"] = MagicMock()
sys.modules["app.schemas.model"] = MagicMock()
sys.modules["openai"] = MagicMock()

from app.services.extraction_service import ExtractionService

# Patch the snapper to work without real data
def mock_snap(self, value, bbox, words):
    # Mock snapper: just checks if value exists in words
    if not value: return None
    for w in words:
        if w["content"] == value:
            return w["polygon"]
    return None

ExtractionService._snap_bbox_to_words = mock_snap

# Helper for normalize so it doesn't crash on us
def mock_normalize(self, bbox, page_width=0, page_height=0):
    return bbox # Pass through

ExtractionService._normalize_bbox = mock_normalize

# Test Setup
async def run_repro():
    print("=== Reproduction: Page Mismatch Bug ===")
    
    # scenario: Total Amount is on Page 2
    mock_pages = [
        {
            "page_number": 1, 
            "width": 100, "height": 100, 
            "words": [{"content": "Invoice", "polygon": [10,10,20,20]}] # content on page 1
        },
        {
            "page_number": 2, 
            "width": 100, "height": 100, 
            "words": [{"content": "Total", "polygon": [50,50,60,60]}] # content on page 2
        }
    ]

    # LLM returns value "Total" but NO page_number
    # Constraints: LLM hallucinates bbox or gives approx one.
    raw_data = {
        "guide_extracted": {
            "total_amount": {
                "value": "Total",
                "bbox": [50,50,60,60], # Coordinates match Page 2 position
                "page_number": None    # MISSING!
            }
        }
    }

    # Instantiate real service (init mocked by MagicMock above)
    service = ExtractionService()
    # Mock init manually if needed, but MagicMock on openai should handle it
    service.azure_openai = MagicMock()
    
    # Mock model with fields
    mock_model = MagicMock()
    mock_field = MagicMock()
    mock_field.key = "total_amount"
    mock_field.type = "string"
    mock_model.fields = [mock_field]
    
    # Mimic calling from a split starting at Page 1
    result = service._validate_and_format(
        raw_data, 
        model=mock_model, 
        pages_info=mock_pages, 
        default_page=1
    )

    item = result["guide_extracted"]["total_amount"]
    print(f"Input: Value='Total', Page=None, Actual Location=Page 2")
    print(f"Output Page: {item['page_number']}")
    
    if item['page_number'] == 1:
        print("❌ BUG REPRODUCED: Defaulted to Page 1 incorrectly.")
    elif item['page_number'] == 2:
        print("✅ FIXED: Correctly identified Page 2.")
    else:
        print("? Unknown outcome")

if __name__ == "__main__":
    asyncio.run(run_repro())
