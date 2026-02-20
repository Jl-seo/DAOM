import json
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
import base64
from typing import Optional
from app.services import llm

router = APIRouter()

@router.post("/analyze")
async def analyze_comparison(
    baseline: UploadFile = File(...),
    candidate: UploadFile = File(...),
    comparison_settings_json: Optional[str] = Form(None)
):
    """
    Compare two images using the configured LLM.
    Returns a list of differences with bounding boxes.
    """
    try:
        # Parse comparison settings if provided
        comparison_settings = None
        if comparison_settings_json:
            try:
                comparison_settings = json.loads(comparison_settings_json)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid comparison_settings_json format: {e}")

        # Read files
        baseline_bytes = await baseline.read()
        candidate_bytes = await candidate.read()

        # Convert to base64
        baseline_b64 = base64.b64encode(baseline_bytes).decode('utf-8')
        candidate_b64 = base64.b64encode(candidate_bytes).decode('utf-8')

        # Prepare data URI
        baseline_url = f"data:{baseline.content_type};base64,{baseline_b64}"
        candidate_url = f"data:{candidate.content_type};base64,{candidate_b64}"

        # Call LLM
        result = await llm.compare_images(
            image_url_1=baseline_url,
            image_url_2=candidate_url,
            comparison_settings=comparison_settings
        )

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
