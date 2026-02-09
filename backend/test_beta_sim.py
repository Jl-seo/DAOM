
import sys
import os
import asyncio
import json
import logging

# Setup Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mock settings
os.environ["AZURE_OPENAI_API_KEY"] = "fake"
os.environ["AZURE_OPENAI_ENDPOINT"] = "https://fake.openai.azure.com"
os.environ["AZURE_OPENAI_API_VERSION"] = "2023-12-01-preview"

# Add path
sys.path.insert(0, os.path.dirname(__file__))

async def run_test():
    print("--- 1. Dependency Check ---")
    try:
        import rapidfuzz
        print(f"✅ rapidfuzz: {rapidfuzz.__version__}")
    except ImportError:
        print("❌ rapidfuzz MISSING")
    
    try:
        from app.services.layout_parser import LayoutParser
        print("✅ LayoutParser imported")
    except Exception as e:
        print(f"❌ LayoutParser import failed: {e}")
        return

    print("\n--- 2. Mocking Data ---")
    ocr_data = {
        "pages": [
            {"page_number": 1, "width": 1000, "height": 1000, "words": [
                {"content": "ITEM", "polygon": [10,10, 50,10, 50,20, 10,20]},
                {"content": "12345", "polygon": [10,30, 50,30, 50,40, 10,40]}
            ]},
            {"page_number": 2, "width": 1000, "height": 1000, "words": []}
        ],
        "tables": [
            {"row_count": 2, "cells": [
                {"content": "ITEM", "row_index": 0, "column_index": 0},
                {"content": "12345", "row_index": 1, "column_index": 0}
            ], "bounding_regions": [{"page_number": 1, "polygon": [10,10, 100,10, 100,100, 10,100]}]}
        ],
        "paragraphs": [
            {"content": "ITEM 12345", "bounding_regions": [{"page_number": 1, "polygon": [10,10, 50,40]}]}
        ],
        "content": "ITEM\n12345"
    }

    try:
        print("\n--- 3. Testing LayoutParser ---")
        parser = LayoutParser(ocr_data)
        tagged, ref_map = parser.parse()
        print(f"✅ Parser Output Length: {len(tagged)}")
        print(f"✅ Ref Map Keys: {list(ref_map.keys())[:5]}")
    except Exception as e:
        print(f"❌ LayoutParser Failed: {e}")
        import traceback
        traceback.print_exc()
        return

    try:
        print("\n--- 4. Testing Refiner Prompt Construction ---")
        from app.services.refiner import RefinerEngine
        class MockModel:
            name = "Test Model"
            description = "Test Desc"
            global_rules = None
            reference_data = None
            fields = []
            beta_features = {"use_optimized_prompt": True}
        
        prompt = RefinerEngine.construct_prompt(MockModel())
        print(f"✅ Prompt Constructed ({len(prompt)} chars)")
    except Exception as e:
        print(f"❌ prompt construction failed: {e}")
        traceback.print_exc()
        return

    try:
        print("\n--- 5. Testing Response Mapping (The likely crash point) ---")
        # Simulate LLM response
        llm_response = {
            "rows": [
                {"line": "001", "qty": "14.000 PCS", "item": "SPP2596000"}
            ]
        }
        
        # Simulate lines 254-283 of extraction_service.py
        guide_extracted = {}
        first_row = llm_response["rows"][0]
        
        converted_guide = {}
        for key, val in first_row.items():
            bbox = None
            page = 1
            confidence = 0.9

            # logic check
            found_result = parser.find_coordinate_by_text(str(val))
            if found_result:
                bbox, page = found_result
                print(f"Found {key}: {val} -> {bbox}")
            else:
                print(f"Not Found {key}: {val}")

            converted_guide[key] = {
                "value": val,
                "confidence": confidence,
                "bbox": bbox,
                "page_number": page
            }
        
        print(f"✅ Mapping Success: {len(converted_guide)} fields")
        print(json.dumps(converted_guide, indent=2))

    except Exception as e:
        print(f"❌ Mapping Logic Failed: {e}")
        import traceback
        traceback.print_exc()

    print("\n--- TEST COMPLETE ---")

if __name__ == "__main__":
    asyncio.run(run_test())
