import asyncio
import json
from app.api.endpoints.extraction_preview import process_extraction_job

async def test_comparison():
    # Provide dummy URLs that we know bypass downloading but trigger LLM
    print("Running fake comparison job...")
    job_id = "fake_job_123"
    try:
        from app.services.comparison_service import compare_images
        # Just call compare_images directly to see if it crashes before Cosmos DB
        res = await compare_images(
            image_url_1="https://sjltest03.blob.core.windows.net/documents/fake1.jpg", 
            image_url_2="https://sjltest03.blob.core.windows.net/documents/fake2.jpg"
        )
        print("RESULT:")
        print(json.dumps(res, indent=2))
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_comparison())
