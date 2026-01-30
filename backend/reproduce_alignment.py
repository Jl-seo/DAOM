import asyncio
import cv2
import numpy as np
from app.services.pixel_diff import calculate_ssim, align_images

async def test_alignment():
    print("Alignment Test Starting...")
    
    # 1. Create a synthetic image (White background with a black square)
    img1 = np.ones((500, 500, 3), dtype=np.uint8) * 255
    cv2.rectangle(img1, (100, 100), (300, 300), (0, 0, 0), -1)
    
    # 2. Create a shifted version (Shifted by 20px)
    # Define affine transform matrix
    M = np.float32([[1, 0, 20], [0, 1, 20]])
    img2_shifted = cv2.warpAffine(img1, M, (500, 500), borderValue=(255, 255, 255))
    
    # Save manually to test logic (simulate download)
    # But since pixel_diff expects URLs, we need to mock download OR test the logic directly.
    # We will test `align_images` directly first.
    
    print("Testing align_images logic...")
    aligned_img = align_images(img1, img2_shifted)
    
    # Check if alignment improved similarity
    # Simple diff check
    diff_original = cv2.absdiff(img1, img2_shifted)
    score_original = np.mean(diff_original)
    
    diff_aligned = cv2.absdiff(img1, aligned_img)
    score_aligned = np.mean(diff_aligned)
    
    print(f"Original Difference Score (Lower is better): {score_original:.2f}")
    print(f"Aligned Difference Score (Lower is better): {score_aligned:.2f}")
    
    if score_aligned < score_original:
        print("✅ SUCCESS: Alignment reduced difference score.")
    else:
        print("❌ FAILURE: Alignment did not improve score.")

if __name__ == "__main__":
    asyncio.run(test_alignment())
