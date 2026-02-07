import asyncio
import base64
import io
import logging
import numpy as np
import cv2
import httpx
from PIL import Image
from skimage.metrics import structural_similarity as ssim

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

def align_images(img_ref: np.ndarray, img_candidate: np.ndarray, max_features: int = 500) -> np.ndarray:
    """
    Aligns the candidate image to the reference image using ORB feature matching.
    Returns the aligned candidate image.
    If alignment fails (not enough matches), returns the resized candidate image as fallback.
    """
    try:
        # Convert images to grayscale
        gray_ref = cv2.cvtColor(img_ref, cv2.COLOR_BGR2GRAY)
        gray_candidate = cv2.cvtColor(img_candidate, cv2.COLOR_BGR2GRAY)
        
        # Detect ORB features and compute descriptors
        orb = cv2.ORB_create(max_features)
        keypoints1, descriptors1 = orb.detectAndCompute(gray_ref, None)
        keypoints2, descriptors2 = orb.detectAndCompute(gray_candidate, None)
        
        # Check if descriptors are found
        if descriptors1 is None or descriptors2 is None:
             logger.warning("[PixelDiff] Alignment failed: No features detected. Falling back to resize.")
             return cv2.resize(img_candidate, (img_ref.shape[1], img_ref.shape[0]))

        # Match features using Hamming distance
        matcher = cv2.DescriptorMatcher_create(cv2.DESCRIPTOR_MATCHER_BRUTEFORCE_HAMMING)
        matches = matcher.match(descriptors1, descriptors2, None)
        
        # Sort matches by score (matches is a tuple, need to convert or use sorted)
        matches = sorted(list(matches), key=lambda x: x.distance, reverse=False)
        
        # Keep top matches (e.g. top 15%)
        num_good_matches = int(len(matches) * 0.15)
        if num_good_matches < 4: # Need at least 4 matches for Homography
             logger.warning("[PixelDiff] Alignment failed: Not enough strong matches. Falling back to resize.")
             return cv2.resize(img_candidate, (img_ref.shape[1], img_ref.shape[0]))
             
        matches = matches[:num_good_matches]
        
        # Extract location of good matches
        points1 = np.zeros((len(matches), 2), dtype=np.float32)
        points2 = np.zeros((len(matches), 2), dtype=np.float32)
        
        for i, match in enumerate(matches):
            points1[i, :] = keypoints1[match.queryIdx].pt
            points2[i, :] = keypoints2[match.trainIdx].pt
            
        # Find homography
        h, mask = cv2.findHomography(points2, points1, cv2.RANSAC)
        
        if h is None:
             logger.warning("[PixelDiff] Alignment failed: Homography could not be computed. Falling back to resize.")
             return cv2.resize(img_candidate, (img_ref.shape[1], img_ref.shape[0]))

        # Warp image
        height, width, _ = img_ref.shape
        aligned_img = cv2.warpPerspective(img_candidate, h, (width, height))
        
        logger.info(f"[PixelDiff] Image aligned successfully with {len(matches)} matches.")
        return aligned_img
        
    except Exception as e:
        logger.error(f"[PixelDiff] Alignment error: {e}. Falling back to resize.")
        # Fallback to simple resize
        return cv2.resize(img_candidate, (img_ref.shape[1], img_ref.shape[0]))


async def detect_pixel_differences(
    image_url_1: str, 
    image_url_2: str,
    threshold: int = 25,
    min_area: int = 50,
    align: bool = True
) -> list[dict]:
    """
    Detect differences between two images with optional alignment.
    Offloads CV operations to thread pool to prevent blocking event loop.
    """
    # 1. Async IO Phase (Download)
    try:
        img1, img2 = await asyncio.gather(
            download_image_as_cv2(image_url_1),
            download_image_as_cv2(image_url_2)
        )
        if img1 is None or img2 is None:
            raise ValueError("Failed to download or decode images")
    except Exception as e:
        logger.error(f"[PixelDiff] Download failed: {e}")
        return []

    # 2. CPU Bound Phase (Processing) - Run in Thread
    def _process_sync():
        try:
            # Use local variables to avoid closure issues if possible, but img1/img2 are captured
            h1, w1 = img1.shape[:2]
            
            nonlocal img2 # Explicitly refer to the downloaded image
            
            if align:
                 img2 = align_images(img1, img2)
            else:
                 h2, w2 = img2.shape[:2]
                 if (h1, w1) != (h2, w2):
                     logger.info(f"[PixelDiff] Resizing image 2 ({w2}x{h2}) to match image 1 ({w1}x{h1}) [No Alignment]")
                     img2 = cv2.resize(img2, (w1, h1))

            diff = cv2.absdiff(img1, img2)
            gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray_diff, threshold, 255, cv2.THRESH_BINARY)
            
            kernel = np.ones((5,5), np.uint8)
            dilated = cv2.dilate(thresh, kernel, iterations=2)
            processed_diff = cv2.erode(dilated, kernel, iterations=1)
            
            contours, _ = cv2.findContours(processed_diff, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            diffs = []
            for contour in contours:
                area = cv2.contourArea(contour)
                if area < min_area:
                    continue
                    
                x, y, w, h = cv2.boundingRect(contour)
                
                pad = 10
                x_pad = max(0, x - pad)
                y_pad = max(0, y - pad)
                w_pad = min(w1 - x_pad, w + 2*pad)
                h_pad = min(h1 - y_pad, h + 2*pad)
                
                crop1 = img1[y_pad:y_pad+h_pad, x_pad:x_pad+w_pad]
                crop2 = img2[y_pad:y_pad+h_pad, x_pad:x_pad+w_pad]
                
                norm_bbox = [
                    x / w1,
                    y / h1,
                    (x + w) / w1,
                    (y + h) / h1
                ]
                
                diffs.append({
                    "bbox": norm_bbox,
                    "crop_1": encode_cv2_image_to_base64(crop1),
                    "crop_2": encode_cv2_image_to_base64(crop2),
                    "diff_score": area
                })
                
            diffs.sort(key=lambda x: x["diff_score"], reverse=True)
            return diffs[:10]
        except Exception as e:
            logger.error(f"[PixelDiff] CV Processing Error: {e}")
            return []

    return await asyncio.to_thread(_process_sync)


async def calculate_ssim(
    image_url_1: str, 
    image_url_2: str,
    min_area: int = 50,
    align: bool = True
) -> list[dict]:
    """
    Detect structural differences using SSIM.
    Run in thread pool.
    """
    # 1. Async IO Phase
    try:
        img1, img2 = await asyncio.gather(
            download_image_as_cv2(image_url_1),
            download_image_as_cv2(image_url_2)
        )
        if img1 is None or img2 is None:
            raise ValueError("Failed to download or decode images")
    except Exception as e:
        logger.error(f"[PixelDiff] SSIM Download failed: {e}")
        return []

    # 2. CPU Bound Phase
    def _process_ssim_sync():
        try:
            h1, w1 = img1.shape[:2]
            nonlocal img2

            if align:
                 img2 = align_images(img1, img2)
            else:
                 h2, w2 = img2.shape[:2]
                 if (h1, w1) != (h2, w2):
                     img2 = cv2.resize(img2, (w1, h1))

            gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
            gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)

            score, diff_map = ssim(gray1, gray2, full=True)
            diff_u8 = ((1 - diff_map) * 255).astype("uint8")
            _, thresh = cv2.threshold(diff_u8, 50, 255, cv2.THRESH_BINARY)
            
            kernel = np.ones((5,5), np.uint8)
            processed_diff = cv2.dilate(thresh, kernel, iterations=2)
            processed_diff = cv2.erode(processed_diff, kernel, iterations=1)
            
            contours, _ = cv2.findContours(processed_diff, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            diffs = []
            for contour in contours:
                area = cv2.contourArea(contour)
                if area < min_area:
                    continue
                    
                x, y, w, h = cv2.boundingRect(contour)
                
                pad = 10
                x_pad = max(0, x - pad)
                y_pad = max(0, y - pad)
                w_pad = min(w1 - x_pad, w + 2*pad)
                h_pad = min(h1 - y_pad, h + 2*pad)
                
                crop1 = img1[y_pad:y_pad+h_pad, x_pad:x_pad+w_pad]
                crop2 = img2[y_pad:y_pad+h_pad, x_pad:x_pad+w_pad]
                
                norm_bbox = [
                    x / w1,
                    y / h1,
                    (x + w) / w1,
                    (y + h) / h1
                ]
                
                diffs.append({
                    "bbox": norm_bbox,
                    "crop_1": encode_cv2_image_to_base64(crop1),
                    "crop_2": encode_cv2_image_to_base64(crop2),
                    "diff_score": area,
                    "ssim_score": score
                })
                
            diffs.sort(key=lambda x: x["diff_score"], reverse=True)
            return diffs[:15]
        except Exception as e:
            logger.error(f"[PixelDiff] SSIM Processing Error: {e}")
            return []

    return await asyncio.to_thread(_process_ssim_sync)
