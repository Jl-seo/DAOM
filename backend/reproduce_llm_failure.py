
import asyncio
import os
import json
import logging
from dotenv import load_dotenv

# Load env vars
load_dotenv(override=True)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add backend to path
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import the target function
# We need to ensure dependencies are satisfied.
# app.services.chunked_extraction imports openai, simplejson, logging, etc.
# ensuring app.core.config is loaded.

from app.services.chunked_extraction import extract_with_chunking

# Define Mock Fields for "유니드" (based on screenshot)
MODEL_FIELDS = [
    {"key": "document_type", "type": "string", "description": "Type of the document"},
    {"key": "contract_number", "type": "string", "description": "Contract number (e.g., UDG10202000035)"},
    {"key": "contract_name", "type": "string", "description": "Name of the construction info"},
    {"key": "contract_date", "type": "string", "description": "Date of contract"},
    {"key": "total_amount", "type": "string", "description": "Total amount of the contract"},
    {"key": "vendor_name", "type": "string", "description": "Name of the vendor/supplier"}
]

# Create Mock OCR Output (Large enough to trigger chunking if we force it, or just pass to function)
# The screenshot shows:
# UNID (주)유니드 공사도급계약서
# 계약번호 : UDG10202000035
# 도급공사명 : 울산공장 No.3 Membrane Filter ...
# ...
# 6. 도급 금액 : ... (W 26,000,000 )
# ...
# Pages of terms...

def create_mock_doc_intel():
    content = """
    UNID (주)유니드
    공사도급계약서
    계약번호 : UDG10202000035
    아래 공사를 도급함에 있어 발주자(이하 갑)와 수급자(이하 을)간에...
    1. 공사 번호 : 7077062
    2. 도급공사명 : 울산공장 No.3 Membrane Filter 상부 Cover 제작 및 설치 작업
    3. 공사내역 유첨내역서
    4. 인도 장소 : (주)유니드 울산공장
    5. 공사 기간 : 착공 2020-03-24, 완공 2020-04-30
    6. 도급 금액 : 일금 이천육백만 원정 (W 26,000,000 ), 부가세 제외 금액임
    """
    
    # Repeat content to make it "large"
    full_content = content * 50 
    
    # Mock Tables
    tables = [
        {
            "rowCount": 2, "columnCount": 2,
            "cells": [
                {"rowIndex": 0, "columnIndex": 0, "content": "계약금액", "boundingRegions": [{"pageNumber": 1, "polygon": [0,0,0,0,0,0,0,0]}]},
                {"rowIndex": 0, "columnIndex": 1, "content": "26,000,000", "boundingRegions": [{"pageNumber": 1, "polygon": [0,0,0,0,0,0,0,0]}]}
            ]
        }
    ]
    
    
    # Mock Pages
    pages = [{"pageNumber": i+1, "words": []} for i in range(5)]
    
    # Mock Paragraphs (CRITICAL for chunking)
    paragraphs = []
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if not line.strip(): continue
        # Distribute across pages
        page_idx = (i % 5) + 1
        paragraphs.append({
            "content": line,
            "bounding_regions": [{"page_number": page_idx, "polygon": [0,0,0,0,0,0,0,0]}]
        })
    
    return {
        "content": full_content,
        "tables": tables,
        "pages": pages,
        "paragraphs": paragraphs,
        "styles": []
    }

async def run_test():
    print("--- Starting Local Extraction Test ---")
    doc_data = create_mock_doc_intel()
    
    print(f"Content Length: {len(doc_data['content'])}")
    
    try:
        # Override token limit to force chunking if needed, but default is 8000
        # Our content is ~500 chars * 50 = 25000 chars. Should trigger chunking?
        # 25000 chars / 4 = 6250 tokens. Maybe one chunk.
        # Let's make it bigger.
        doc_data['content'] = doc_data['content'] * 10
        print(f"Adjusted Content Length: {len(doc_data['content'])}")
        
        merged, errors = await extract_with_chunking(
            doc_intel_output=doc_data,
            model_fields=MODEL_FIELDS,
            max_tokens_per_chunk=4000, # Force smaller chunks
            max_concurrent=5
        )
        
        print("\n--- Extraction Result ---")
        print(json.dumps(merged, indent=2, ensure_ascii=False))
        
        print("\n--- Errors ---")
        print(errors)
        
        # Check if debug info is present (it's in _merge_info in the returned dict)
        if "_merge_info" in merged:
            print("\n--- Debug Info Found ---")
            print(json.dumps(merged["_merge_info"], indent=2, ensure_ascii=False))
        else:
            print("\n--- NO Debug Info Found in merged result ---")

    except Exception as e:
        logger.exception("Test failed")

if __name__ == "__main__":
    asyncio.run(run_test())
