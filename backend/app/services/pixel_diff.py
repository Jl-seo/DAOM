import asyncio
import base64
import io
import logging
import numpy as np
import cv2
import httpx
from PIL import Image

logger = logging.getLogger(__name__)

async def download_image_as_cv2(url: str) -> np.ndarray:
    """Download image from URL and convert to OpenCV format (BGR)."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=30.0)
        resp.raise_for_status()
        image_bytes = resp.content
        
        # Convert bytes to numpy array
        nparr = np.frombuffer(image_bytes, np.uint8)
        # Decode image
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return img

def encode_cv2_image_to_base64(img: np.ndarray) -> str:
    """Convert OpenCV image to base64 string."""
    _, buffer = cv2.imencode('.jpg', img)
    return f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('utf-8')}"

async def detect_pixel_differences(
    image_url_1: str, 
    image_url_2: str,
    threshold: int = 25,
    min_area: int = 50
) -> list[dict]:
    """
    Detect differences between two images.
    
    Args:
        image_url_1: Baseline image URL
        image_url_2: Candidate image URL
        threshold: Pixel difference threshold (0-255). Lower = more sensitive to color changes.
        min_area: Minimum bbox area (in pixels) to consider as a valid difference.
    
    Returns:
        List of diff dicts:
        [
            {
                "bbox": [x1, y1, x2, y2],  # Normalized coordinates (0-1)
                "crop_1": "data:image/...",
                "crop_2": "data:image/...",
                "diff_score": float
            }
        ]
    """
    try:
        # Download images
        img1, img2 = await asyncio.gather(
            download_image_as_cv2(image_url_1),
            download_image_as_cv2(image_url_2)
        )
        
        if img1 is None or img2 is None:
            raise ValueError("Failed to download or decode images")

        # Resize img2 to match img1 if dimensions differ
        h1, w1 = img1.shape[:2]
        h2, w2 = img2.shape[:2]
        
        if (h1, w1) != (h2, w2):
            logger.info(f"[PixelDiff] Resizing image 2 ({w2}x{h2}) to match image 1 ({w1}x{h1})")
            img2 = cv2.resize(img2, (w1, h1))

        # Compute absolute difference
        diff = cv2.absdiff(img1, img2)
        
        # Convert to grayscale
        gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        
        # Thresholding
        _, thresh = cv2.threshold(gray_diff, threshold, 255, cv2.THRESH_BINARY)
        
        # Morphological operations to merge nearby pixels (fill gaps)
        kernel = np.ones((5,5), np.uint8)
        dilated = cv2.dilate(thresh, kernel, iterations=2)
        processed_diff = cv2.erode(dilated, kernel, iterations=1)
        
        # Find contours
        contours, _ = cv2.findContours(processed_diff, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        diffs = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < min_area:
                continue
                
            x, y, w, h = cv2.boundingRect(contour)
            
            # Add padding to crop (optional)
            pad = 10
            x_pad = max(0, x - pad)
            y_pad = max(0, y - pad)
            w_pad = min(w1 - x_pad, w + 2*pad)
            h_pad = min(h1 - y_pad, h + 2*pad)
            
            # Crop images
            crop1 = img1[y_pad:y_pad+h_pad, x_pad:x_pad+w_pad]
            crop2 = img2[y_pad:y_pad+h_pad, x_pad:x_pad+w_pad]
            
            # Normalize bbox coordinates (0-1)
            # Standard: [x, y, x+w, y+h] where (0,0) is top-left
            # Usually frontend expects [x1, y1, x2, y2] relative to page width/height based on previous context (1000 base or 0-1?)
            # Let's verify standard in llm.py or frontend. Assuming 1000-based int or 0-1 float.
            # ComparisonWorkspace uses `location_1`: number[] | null.
            # Usually PDF viewers use 0-100 or 0-1. Let's return 0-1 floats to be safe and versatile.
            
            norm_bbox = [
                x / w1,      # x1
                y / h1,      # y1
                (x + w) / w1, # x2
                (y + h) / h1  # y2
            ]
            
            diffs.append({
                "bbox": norm_bbox,
                "crop_1": encode_cv2_image_to_base64(crop1),
                "crop_2": encode_cv2_image_to_base64(crop2),
                "diff_score": area
            })
            
        # Sort by area (largest diff first)
        diffs.sort(key=lambda x: x["diff_score"], reverse=True)
        
        # Limit to top N diffs to avoid token explosion
        MAX_DIFFS = 10
        return diffs[:MAX_DIFFS]
        
    except Exception as e:
        logger.error(f"[PixelDiff] Error detecting differences: {e}")
        return []
