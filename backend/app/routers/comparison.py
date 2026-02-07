from fastapi import APIRouter, UploadFile, File, HTTPException
import base64
from app.services import llm

router = APIRouter()

@router.post("/analyze")
async def analyze_comparison(
    baseline: UploadFile = File(...),
    candidate: UploadFile = File(...),
):
    """
    Compare two images using the configured LLM.
    Returns a list of differences with bounding boxes.
    """
    try:
        # Read files
        baseline_bytes = await baseline.read()
        candidate_bytes = await candidate.read()

        # Convert to base64
        baseline_b64 = base64.b64encode(baseline_bytes).decode('utf-8')
        candidate_b64 = base64.b64encode(candidate_bytes).decode('utf-8')

        # Prepare data URI
        # Assuming images. For production, check mime_type
        baseline_url = f"data:{baseline.content_type};base64,{baseline_b64}"
        candidate_url = f"data:{candidate.content_type};base64,{candidate_b64}"

        # Call LLM
        result = await llm.compare_images(baseline_url, candidate_url)

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
