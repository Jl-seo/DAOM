import asyncio
import os
import time
import sys

# Append path to import app modules
sys.path.append("/Users/seojeonglee/.gemini/antigravity/scratch/daom/backend")

from dotenv import load_dotenv
load_dotenv("/Users/seojeonglee/.gemini/antigravity/scratch/daom/backend/.env")

from app.services.doc_intel import analyze_document_layout
from app.core.config import settings

async def main():
    print(f"Endpoint: {settings.AZURE_FORM_ENDPOINT}")
    print(f"Key exists: {bool(settings.AZURE_FORM_KEY)}")
    print("Testing Azure DI connection...")
    
    # Create a dummy tiny text file to analyze
    dummy_text = b"Hello World! This is a test document."
    
    start = time.time()
    try:
        # We need to pass it as bytes or a stream. analyze_document_layout takes file_content and mime_type
        # Let's use application/pdf or something standard, or just text/plain
        result = await analyze_document_layout(dummy_text, mime_type="text/plain")
        
        print(f"DONE in {time.time() - start:.2f}s")
        print(f"Extracted content length: {len(result.get('content', ''))}")
        print("SUCCESS")
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(main())
