import json
import logging
from typing import Optional
from app.core.enums import DEFAULT_COMPARISON_CATEGORIES
from app.core.config import settings

# Import required functions from llm.py since it remains our base LLM client wrapper
from app.services.llm import get_openai_client, get_current_model

logger = logging.getLogger(__name__)

async def compare_images(image_url_1: str, image_url_2: str, custom_instructions: Optional[str] = None, comparison_settings: Optional[dict] = None) -> dict:
    """
    Compare two images using the 3-Layer Component-Based Architecture:
    1. Physical Layer: SSIM (Structural Similarity)
    2. Visual Layer: Azure AI Vision (Color, Objects)
    3. Structural/Semantic Layer: GPT-4o Synthesis
    """
    client = get_openai_client()
    model = get_current_model()

    # 설정값 기본값 (UI에서 전달되지 않으면 사용)
    conf_threshold = 0.85
    ignore_position = True
    ignore_color = False
    ignore_font = True
    ignore_compression_noise = True
    output_language = "Korean"
    use_ssim = True
    use_vision = False
    align_images = True
    custom_ignore_rules = None  # 추가 무시 규칙 (자연어)
    ssim_identity_threshold = 0.95  # Global SSIM score gate (이 이상이면 LLM 호출 생략)

    # comparison_settings에서 설정값 읽기 (UI에서 전달된 값 우선)
    if comparison_settings:
        conf_threshold = comparison_settings.get("confidence_threshold", 0.85)
        ignore_position = comparison_settings.get("ignore_position_changes", True)
        ignore_color = comparison_settings.get("ignore_color_changes", False)
        ignore_font = comparison_settings.get("ignore_font_changes", True)
        ignore_compression_noise = comparison_settings.get("ignore_compression_noise", True)
        output_language = comparison_settings.get("output_language", "Korean")
        use_ssim = comparison_settings.get("use_ssim_analysis", True)
        use_vision = comparison_settings.get("use_vision_analysis", False)
        align_images = comparison_settings.get("align_images", True)
        custom_ignore_rules = comparison_settings.get("custom_ignore_rules")
        ssim_identity_threshold = comparison_settings.get("ssim_identity_threshold", 0.95)

    # custom_instructions (global_rules)와 custom_ignore_rules 합치기
    combined_instructions = []
    if custom_instructions:
        combined_instructions.append(f"GLOBAL RULES: {custom_instructions}")
    if custom_ignore_rules:
        combined_instructions.append(f"CUSTOM IGNORE RULES (자연어): {custom_ignore_rules}")

    final_custom_instructions = "\n".join(combined_instructions) if combined_instructions else None

    logger.info(f"[LLM] Comparison {model} | SSIM={use_ssim} | Vision={use_vision}")
    logger.info(f"[LLM] Settings: ignore_position={ignore_position}, ignore_color={ignore_color}, ignore_font={ignore_font}, ignore_noise={ignore_compression_noise}")
    if final_custom_instructions:
        logger.info(f"[LLM] Custom instructions: {final_custom_instructions[:100]}...")

    # 1. Parallel Data Collection (SSIM + Vision)
    from app.services import pixel_diff
    from app.services.vision_service import VisionService
    import asyncio

    tasks = []

    # Task A: SSIM Analysis (Physical)
    if use_ssim:
        tasks.append(pixel_diff.calculate_ssim(image_url_1, image_url_2, align=align_images))
    else:
        # Dummy task returning []
        async def no_op(): return []
        tasks.append(no_op())

    # Task B: Vision Analysis (Visual Semantics)
    # Wrap sync call in thread or async wrapper
    async def analyze_vision(url):
        if not use_vision: return "Vision Analysis Disabled"
        return await asyncio.to_thread(VisionService.analyze_image, url)

    tasks.append(analyze_vision(image_url_1))
    tasks.append(analyze_vision(image_url_2))

    # Execute Parallel
    results = await asyncio.gather(*tasks, return_exceptions=True)

    ssim_result = results[0] if isinstance(results[0], dict) else {"score": 0.0, "diffs": []}
    ssim_diffs = ssim_result.get("diffs", [])
    ssim_global_score = ssim_result.get("score", 0.0)
    vision_1 = results[1] if isinstance(results[1], str) else "Error"
    vision_2 = results[2] if isinstance(results[2], str) else "Error"

    logger.info(f"[LLM] SSIM global score: {ssim_global_score:.4f}, detected {len(ssim_diffs)} diff regions")

    # Gate 1: SSIM Global Score Gate (핵심 할루시네이션 방지)
    # Global SSIM score가 threshold 이상이면 노이즈 contour 수와 관계없이 LLM 호출 건너뜀
    if use_ssim and ssim_global_score >= ssim_identity_threshold:
        logger.info(f"[LLM] SSIM score {ssim_global_score:.4f} >= threshold {ssim_identity_threshold}. Images are IDENTICAL. Skipping LLM.")
        return {
            "differences": [],
            "metadata": {
                "model": model,
                "method": "ssim_score_gate",
                "ssim_score": ssim_global_score,
                "ssim_threshold": ssim_identity_threshold,
                "ssim_noise_contours": len(ssim_diffs),
                "vision_enabled": use_vision,
                "skipped_llm": True,
                "reason": f"Images are identical (SSIM {ssim_global_score:.4f} >= {ssim_identity_threshold})"
            }
        }

    # Gate 2: Fast path - SSIM이 diff 0건이면 LLM 호출 없이 즉시 빈 결과 반환
    skip_llm_if_identical = comparison_settings.get("skip_llm_if_identical", True) if comparison_settings else True

    if not ssim_diffs and use_ssim and skip_llm_if_identical:
        logger.info("[LLM] SSIM confirms images are IDENTICAL (zero diffs). Skipping LLM call to prevent hallucination.")
        return {
            "differences": [],
            "metadata": {
                "model": model,
                "method": "ssim_fast_path",
                "ssim_score": ssim_global_score,
                "ssim_count": 0,
                "vision_enabled": use_vision,
                "skipped_llm": True,
                "reason": "Images are identical (SSIM zero diffs)"
            }
        }

    # 2. Construct Synthesis Context
    ssim_context = ""
    ssim_identical = False
    
    if use_ssim:
        if ssim_diffs:
            ssim_context = f"**PHYSICAL LAYER (SSIM)**: Detected {len(ssim_diffs)} areas with low structural similarity. These indicate POTENTIAL changes.\n"
            ssim_context += "Targeted image crops for these regions are attached at the end of the prompt sequence for your direct verification.\n"
            for i, d in enumerate(ssim_diffs[:5]):
                ssim_context += f"- Diff #{i}: score={d.get('diff_score',0)}, bbox={d['bbox']}\n"
        else:
            ssim_identical = True
            ssim_context = """**PHYSICAL LAYER (SSIM)**: Images are structurally IDENTICAL (High Similarity).
            
    ⚠️ CRITICAL: Since SSIM analysis confirms the images are IDENTICAL, you should NOT report any differences.
    If you cannot find clear, obvious, and verifiable differences, return an EMPTY differences array."""
    else:
        ssim_context = "**PHYSICAL LAYER (SSIM)**: Disabled by user. You must rely entirely on your own visual inspection."

    vision_context = f"""
    **VISUAL LAYER (Azure Vision)**:
    - Baseline Image Details:
    {vision_1}
    
    - Candidate Image Details:
    {vision_2}
    """

    # 3. GPT-4o Synthesis Prompt
    # Build dynamic category list based on user settings
    default_categories = DEFAULT_COMPARISON_CATEGORIES
    allowed_categories = comparison_settings.get("allowed_categories") if comparison_settings else None
    excluded_categories = comparison_settings.get("excluded_categories") if comparison_settings else None

    if allowed_categories:
        # Only use specified categories
        category_list = [c for c in allowed_categories if c in default_categories]
    elif excluded_categories:
        # Remove excluded categories
        category_list = [c for c in default_categories if c not in excluded_categories]
    else:
        # Use all defaults
        category_list = default_categories

    categories_str = json.dumps(category_list)

    # Build category instruction (강화된 지시)
    if allowed_categories:
        category_instruction = f"""**ABSOLUTE REQUIREMENT**: You MUST ONLY report differences in these categories: {categories_str}. 
        ANY difference not in this list MUST be completely ignored - do NOT include them in your response under any circumstances."""
    elif excluded_categories:
        category_instruction = f"""**ABSOLUTE REQUIREMENT**: You MUST COMPLETELY IGNORE and NEVER report differences in these categories: {json.dumps(excluded_categories)}. 
        Even if you detect changes in {json.dumps(excluded_categories)}, you MUST NOT include them in your response. 
        ONLY report differences in: {categories_str}."""
    else:
        category_instruction = f"You may report differences in any of these categories: {categories_str}."

    # 추가: SSIM이 동일하면 hallucination 방지 강화
    anti_hallucination_instruction = ""
    if ssim_identical:
        anti_hallucination_instruction = """
    
    ⚠️ ANTI-HALLUCINATION WARNING ⚠️
    The SSIM analysis has CONFIRMED these images are IDENTICAL at the pixel level.
    
    DO NOT invent or imagine differences that don't exist.
    DO NOT report minor variations that are likely compression artifacts.
    DO NOT report differences you are not 100% certain about.
    
    If you cannot find CLEAR, OBVIOUS, and VERIFIABLE differences, you MUST return:
    {"differences": []}
    
    Only report a difference if you can see an UNMISTAKABLE change with your own visual inspection.
    When in doubt, do NOT report it."""

    # IGNORE RULES를 설정값에 따라 동적으로 생성
    ignore_rules_list = []
    if ignore_position:
        ignore_rules_list.append("- IGNORE position shifts if text content is identical")
    if ignore_color:
        ignore_rules_list.append("- IGNORE color changes (배경 색, 글자 색 차이 무시)")
    if ignore_font:
        ignore_rules_list.append("- IGNORE font style changes (폰트 크기, 굵기 차이 무시)")
    if ignore_compression_noise:
        ignore_rules_list.append("- IGNORE compression artifacts and minor pixel noise")
    
    # 🌟 CRITICAL Logo & Layout Anti-Hallucination Rules
    ignore_rules_list.append("- IGNORE minor pixel variations, alias artifacts, or slight lighting shifts in logos, watermarks, and branding elements if the overall shape and meaning are identical.")
    ignore_rules_list.append("- ONLY report a logo difference if it is clearly a DIFFERENT logo entirely OR if the logo/banner is COMPLETELY MISSING.")
    ignore_rules_list.append("- CRITICAL: If an entire section, top banner, or large block of text/graphics is missing from the Candidate image, you MUST report it under the 'missing_element' category.")
    ignore_rules_list.append("- IGNORE anything you are not certain about, but do not ignore massive structural or layout omissions.")

    ignore_rules_text = "\n    ".join(ignore_rules_list)

    system_prompt = f"""
    You are an expert Visual QA Auditor utilizing a 3-Layer Analysis Pipeline.
    
    **INPUT DATA**:
    1. {ssim_context}
    2. {vision_context}
    3. **VISUAL INSPECTION**: You will see the two images directly.

    **GOAL**: Synthesize these signals to find verifiable differences. Do NOT hallucinate or invent differences.
    
    {category_instruction}
    {anti_hallucination_instruction}
    
    **TEXT/NUMBER ACCURACY**:
    - Read text and numbers carefully. Do not skip digits (e.g., "140" ≠ "40").
    - If both images show the same text, do NOT report it as a difference.
    
    **LOGIC CHAIN**:
    1. **Check SSIM**: If SSIM says "IDENTICAL", you should almost certainly return an empty differences array.
    2. **Check Vision**: Compare Tags/Captions. Only report if there's a CLEAR mismatch.
    3. **Visual Audit**: Look at the images yourself.
       - If SSIM highlights a region, zoom in on that region.
       - If you're not 100% sure about a difference, DO NOT REPORT IT.
    
    **IGNORE RULES** (MUST FOLLOW):
    {ignore_rules_text}
    
    {final_custom_instructions or ""}

    Return JSON:
    {{
        "differences": [
            {{
                "id": "1",
                "observation_1": "Exact visual state/text in the Baseline Image",
                "observation_2": "Exact visual state/text in the Candidate Image",
                "reasoning": "Step-by-step logic explaining why this is a valid difference based on the ignore rules",
                "description": "Brief description in {output_language} (e.g., 'The date changed from X to Y')",
                "category": "One of {categories_str} (ALWAYS English)",
                "confidence": 0.95,
                "location_1": [y1, x1, y2, x2] (0-1000 scale)
            }}
        ]
    }}
    
    IMPORTANT: 
    - You MUST fill out "observation_1", "observation_2", and "reasoning" BEFORE providing the final "description".
    - "category" MUST be one of the English keys in {categories_str}. DO NOT translate the category.
    - "description" MUST be in {output_language}.
    - If images are identical or changes are ignored by rules, return {{"differences": []}}
    - DO NOT report text differences unless you are 100% certain you read both texts correctly.
    """

    user_message = [
        {"type": "text", "text": "Compare these images using the 3-Layer Pipeline."},
        {"type": "image_url", "image_url": {"url": image_url_1}},
        {"type": "image_url", "image_url": {"url": image_url_2}}
    ]

    # Crop-Level Verification: Append targeted crops to the end of the visual inspection sequence
    if use_ssim and ssim_diffs:
        user_message.append({
            "type": "text", 
            "text": "The SSIM Physical Layer identified the following specific regions of interest. Please review these paired crops carefully. For each pair, compare the Baseline Crop to the Candidate Crop. If they are semantically identical based on the ignore rules, DO NOT report a difference."
        })
        for i, d in enumerate(ssim_diffs[:5]):
            crop1_url = d.get('crop_1')
            crop2_url = d.get('crop_2')
            if crop1_url and crop2_url:
                user_message.append({"type": "text", "text": f"\n--- Diff #{i} Context ---"})
                user_message.append({"type": "text", "text": f"Diff #{i} - Baseline Image Crop:"})
                user_message.append({"type": "image_url", "image_url": {"url": crop1_url}})
                user_message.append({"type": "text", "text": f"Diff #{i} - Candidate Image Crop:"})
                user_message.append({"type": "image_url", "image_url": {"url": crop2_url}})

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            response_format={"type": "json_object"},
            max_completion_tokens=settings.LLM_COMPARISON_MAX_TOKENS,
            temperature=0,
        )

        result_content = response.choices[0].message.content
        data = json.loads(result_content)

        # Post-process 1: Filter by confidence threshold (낮은 확신도 차이점 제거)
        if "differences" in data and isinstance(data["differences"], list):
            before_conf_count = len(data["differences"])
            data["differences"] = [
                d for d in data["differences"]
                if d.get("confidence", 0) >= conf_threshold
            ]
            after_conf_count = len(data["differences"])
            if before_conf_count != after_conf_count:
                logger.info(f"[LLM] Confidence filter: {before_conf_count} -> {after_conf_count} (threshold: {conf_threshold})")

        # Post-process 2: Filter out excluded categories (LLM 지시 무시 대비 안전장치)
        if "differences" in data and isinstance(data["differences"], list):
            original_count = len(data["differences"])

            if allowed_categories:
                # Only keep differences in allowed categories
                data["differences"] = [
                    d for d in data["differences"]
                    if d.get("category", "").lower() in [c.lower() for c in category_list]
                ]
            elif excluded_categories:
                # Remove differences in excluded categories
                excluded_lower = [c.lower() for c in excluded_categories]
                data["differences"] = [
                    d for d in data["differences"]
                    if d.get("category", "").lower() not in excluded_lower
                ]

            filtered_count = len(data["differences"])
            if original_count != filtered_count:
                logger.info(f"[LLM] Category filter: {original_count} -> {filtered_count} differences")

        # Inject metadata
        data["metadata"] = {
            "model": model,
            "method": "3_layer_component_arch",
            "ssim_score": ssim_global_score,
            "ssim_count": len(ssim_diffs),
            "vision_enabled": use_vision,
            "category_filter_applied": bool(allowed_categories or excluded_categories),
            "confidence_threshold": conf_threshold
        }
        return data

    except Exception as e:
        logger.error(f"[LLM] Comparison synthesis failed: {e}")
        return {"differences": [], "error": str(e)}
