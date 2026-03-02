import asyncio
import os
import time
import sys

from dotenv import load_dotenv
load_dotenv("/Users/seojeonglee/.gemini/antigravity/scratch/daom/backend/.env")

# Append path to import app modules
sys.path.append("/Users/seojeonglee/.gemini/antigravity/scratch/daom/backend")

from app.services.doc_intel import analyze_document_layout
from app.core.config import settings

async def main():
    pdf_path = "/Users/seojeonglee/.gemini/antigravity/scratch/daom/backend/scripts/SQC36KJO1.PDF"
    if not os.path.exists(pdf_path):
        print(f"File not found: {pdf_path}")
        return
        
    with open(pdf_path, 'rb') as f:
        content = f.read()
        
    print(f"Testing Azure DI with PDF: {pdf_path} ({len(content)} bytes)")
    
    start = time.time()
    try:
        # We need to pass it as bytes or a stream. analyze_document_layout takes file_content and mime_type
        result = await analyze_document_layout(content, mime_type="application/pdf")
        
        print(f"DONE in {time.time() - start:.2f}s")
        print(f"Extracted content len: {len(result.get('content', ''))}")
        print("SUCCESS")
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(main())
