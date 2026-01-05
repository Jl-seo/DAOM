import os
import sys
import asyncio
from dotenv import load_dotenv

# Add backend to path
# Assuming script is in scratch/daom/scripts
# backend is in scratch/daom/backend
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
backend_path = os.path.join(project_root, 'backend')
sys.path.append(backend_path)

# Load Env
load_dotenv(os.path.join(backend_path, '.env'))

# Now import app modules
# We need to bypass some imports if they fail due to missing dependencies not needed for this test
try:
    from app.core.config import settings
    from app.services import doc_intel
    from app.services import llm
except ImportError as e:
    print(f"Import Error: {e}")
    # Try to install dependencies? No, report error.
    sys.exit(1)

async def main():
    print("--- 1. Testing Configuration ---")
    print(f"Doc Intel Endpoint: {settings.AZURE_FORM_ENDPOINT}")
    print(f"OpenAI Endpoint: {settings.AZURE_OPENAI_ENDPOINT}")
    print(f"OpenAI Deployment: {settings.AZURE_OPENAI_DEPLOYMENT_NAME}")
    
    # 2. Test Doc Intel
    print("\n--- 2. Testing Document Intelligence (OCR) ---")
    image_path = "/Users/seojeonglee/.gemini/antigravity/brain/5e1a41ac-f1c0-4ad9-8000-865c00569d00/uploaded_image_1767575938973.png"
    
    if not os.path.exists(image_path):
        print(f"Image not found at {image_path}, checking common locations...")
        # Fallback to any file in current dir if specific image missing, but we assume it exists
        # Or just create a dummy text file? No, Doc Intel needs real file.
        # We rely on the uploaded image.
        pass

    try:
        with open(image_path, "rb") as f:
            file_bytes = f.read()
            
        print(f"Read file: {image_path}, size: {len(file_bytes)} bytes")
        
        # Call Doc Intel
        # Note: If this fails with azure-core version mismatch, we know it's a dept issue.
        ocr_result = doc_intel.extract_with_strategy(file_bytes, "prebuilt-layout")
        print("✅ OCR Success!")
        print(f"Extracted content length: {len(ocr_result.get('content', ''))}")
        
    except Exception as e:
        print(f"❌ OCR Failed: {e}")
        # Proceed to OpenAI test anyway to check credential
    
    # 3. Test OpenAI
    print("\n--- 3. Testing Azure OpenAI (GPT) ---")
    try:
        # Simulate simple extraction
        client = llm.get_openai_client()
        model_name = settings.AZURE_OPENAI_DEPLOYMENT_NAME
        
        print(f"Sending request to model: {model_name} ...")
        
        # Test call
        response = await client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a test assistant. Respond with JSON."},
                {"role": "user", "content": "Hello, are you working?"}
            ],
            response_format={"type": "json_object"}
        )
        
        print("✅ OpenAI Success!")
        content = response.choices[0].message.content
        print(f"Response: {content}")
        
    except Exception as e:
        print(f"❌ OpenAI Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
