
import json
import logging
from typing import Dict, Any, List, Optional
import math

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("logic_test")

class MockExtractionService:
    def _snap_bbox_to_words(self, value: str, approximate_bbox: Optional[List[float]], words: List[Dict[str, Any]]) -> Optional[List[float]]:
        """
        Copied logic from ExtractionService._snap_bbox_to_words for isolated testing.
        Refines the bounding box by snapping to the exact coordinates of the matching words from OCR.
        """
        if not value:
            return None
            
        value_clean = str(value).replace(" ", "").replace(",", "").replace(".", "").replace("-", "").lower()
        if not value_clean:
            return None

        # Helper functions
        def get_bbox_center(b):
            return ((b[0]+b[2])/2, (b[1]+b[3])/2)
            
        def get_dist(b1, b2):
             c1 = get_bbox_center(b1)
             c2 = get_bbox_center(b2)
             return math.sqrt((c1[0]-c2[0])**2 + (c1[1]-c2[1])**2)

        def clean_token(t):
             return str(t).replace(" ","").replace(",","").replace(".","").replace("-","").lower()

        # 1. Exact token matches
        exact_matches = [w for w in words if clean_token(w["content"]) == value_clean]
        if exact_matches:
            # If multiple matches, find closest to approximate_bbox if provided
            if approximate_bbox and len(exact_matches) > 1:
                closest = min(exact_matches, key=lambda w: get_dist(w["polygon"], approximate_bbox))
                logger.info(f"Found {len(exact_matches)} exact matches, picked closest: {closest['content']}")
                return closest["polygon"]
            
            # Simple case: take the first one or the only one
            logger.info(f"Found exact match: {exact_matches[0]['content']}")
            return exact_matches[0]["polygon"]

        return None # Simplified for this POC, real logic handles multi-word sequences too

def run_test():
    print("=== Logic Test: Verify Highlighting with Minimized Payload ===")
    
    # 1. Mock Full ADI Output (High Definition)
    # This is what we have in the backend originally.
    full_ocr_data = {
        "pages": [
            {
                "page_number": 1,
                "width": 1000,
                "height": 1000,
                "lines": [{"content": "Invoice #12345", "polygon": [10, 10, 100, 10, 100, 20, 10, 20]}],
                "words": [
                    {"content": "Invoice", "polygon": [10, 10, 50, 10, 50, 20, 10, 20], "confidence": 0.99},
                    {"content": "#12345", "polygon": [60, 10, 100, 10, 100, 20, 60, 20], "confidence": 0.99},
                    {"content": "Total", "polygon": [10, 50, 50, 50, 50, 60, 10, 60], "confidence": 0.99},
                    {"content": "$500.00", "polygon": [60, 50, 100, 50, 100, 60, 60, 60], "confidence": 0.99},
                ]
            }
        ]
    }
    print("1. [Backend] Full OCR Data Loaded: Contains 'words' with coordinates.")
    
    # 2. Mock Payload Filtering (Optimization)
    # This is what validation/extraction_service does before sending to LLM
    ocr_data_to_send = {
        "pages": []
    }
    for p in full_ocr_data["pages"]:
        p_clean = p.copy()
        if "words" in p_clean:
            del p_clean["words"] # STRIPPING WORDS!
        ocr_data_to_send["pages"].append(p_clean)
        
    print("2. [Optimization] Stripped 'words' from payload. Sending to LLM...")
    if "words" not in ocr_data_to_send["pages"][0]:
        print("   -> verified: 'words' are missing in LLM payload.")
    
    # 3. Mock LLM Response (Blind extraction)
    # LLM sees "Invoice #12345" in lines/content but has no coordinates.
    # It returns the value and a NULL bbox (or approx if it guessed, but usually null/broad in universal mode)
    llm_extracted_item = {
        "key": "invoice_number",
        "value": "#12345", # LLM extracted this text
        "bbox": None, # LLM doesn't know the bbox
        "page_number": 1
    }
    print(f"3. [LLM] Extracted Value: '{llm_extracted_item['value']}', BBox: {llm_extracted_item['bbox']}")
    
    # 4. Backend "Snapping" Logic
    # This simulates _validate_and_format recovering the bbox
    service = MockExtractionService()
    
    # CRITICAL: service uses full_ocr_data (original), NOT ocr_data_to_send
    original_page = next(p for p in full_ocr_data["pages"] if p["page_number"] == 1)
    
    print("4. [Backend] Attempting to snap bbox using Original OCR Data...")
    snapped_bbox = service._snap_bbox_to_words(
        value=llm_extracted_item["value"],
        approximate_bbox=None,  
        words=original_page["words"] # We access the original words here!
    )
    
    if snapped_bbox:
        print(f"✅ SUCCESS! Recovered BBox: {snapped_bbox}")
        # Verify it matches the original word's polygon
        expected = [60, 10, 100, 10, 100, 20, 60, 20]
        if snapped_bbox == expected:
             print("   -> BBox matches exact coordinate of word '#12345'")
        else:
             print("   -> BBox recovered but differs slightly (acceptable for multi-word)")
    else:
        print("❌ FAILED: Could not recover BBox.")

if __name__ == "__main__":
    run_test()
