"""
Vision Extraction Pipeline (V1)

Extracts structured data from images using GPT-4.1 Vision API directly,
bypassing Azure Document Intelligence OCR.

Use cases:
- 3D objects (test tubes, product labels)
- Curved surfaces, handwritten text
- Photos where OCR fails due to perspective/reflection
"""
import base64
import json
import logging
import mimetypes
from datetime import datetime
from typing import Dict, Any, Optional, List

from app.schemas.model import ExtractionModel
from app.services.extraction.core import ExtractionResult, TokenUsage
from app.services.llm import get_current_model
from app.core.config import settings
from openai import AsyncAzureOpenAI

logger = logging.getLogger(__name__)


class VisionExtractionPipeline:
    """
    Vision-first extraction: sends image directly to GPT-4.1 Vision API
    for text recognition and field extraction in a single call.
    """

    def __init__(self, azure_client: AsyncAzureOpenAI):
        self.azure_client = azure_client

    async def execute(
        self,
        model: ExtractionModel,
        file_content: bytes,
        filename: str = "",
        mime_type: str = "",
    ) -> ExtractionResult:
        """
        Main entry point for Vision extraction.
        1. Encode image as base64 data URL
        2. Build extraction prompt from model schema
        3. Call GPT-4.1 Vision API
        4. Parse and return ExtractionResult
        """
        start_time = datetime.utcnow()

        # --- 1. Encode Image ---
        if not mime_type:
            mime_type = self._guess_mime(filename)
        base64_image = base64.b64encode(file_content).decode("utf-8")
        data_url = f"data:{mime_type};base64,{base64_image}"

        image_size_kb = len(file_content) / 1024
        logger.info(
            f"[VisionPipeline] Image: {filename} ({image_size_kb:.0f}KB, {mime_type})"
        )

        # --- 2. Build Prompt ---
        system_prompt = self._build_system_prompt(model)

        # --- 3. Call GPT-4.1 Vision ---
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "이 이미지에서 모든 필드를 추출하세요. Return valid JSON.",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url, "detail": "high"},
                    },
                ],
            },
        ]

        llm_result = await self._call_vision_llm(messages)

        # --- 4. Build Result ---
        guide_extracted = llm_result.get("guide_extracted", {})
        # If the LLM returned fields at the top level (no guide_extracted wrapper),
        # wrap them
        if not guide_extracted and not llm_result.get("error"):
            # Check if the result looks like field data
            possible_fields = {
                f.key for f in model.fields
            }
            if any(k in llm_result for k in possible_fields):
                guide_extracted = {
                    k: v
                    for k, v in llm_result.items()
                    if k not in ("_token_usage", "error")
                }

        total_usage = llm_result.get("_token_usage", {})

        result = ExtractionResult(
            guide_extracted=guide_extracted,
            raw_content=f"[Vision Extraction] {filename}",
            raw_tables=[],
            token_usage=TokenUsage(**total_usage) if total_usage else TokenUsage(),
            error=llm_result.get("error"),
            beta_metadata={
                "pipeline_mode": "vision-extraction",
                "image_size_kb": image_size_kb,
                "mime_type": mime_type,
            },
            model_name=model.name,
            duration_seconds=(datetime.utcnow() - start_time).total_seconds(),
        )

        logger.info(
            f"[VisionPipeline] Complete: {len(guide_extracted)} fields extracted "
            f"in {result.duration_seconds:.1f}s"
        )
        return result

    def _build_system_prompt(self, model: ExtractionModel) -> str:
        """Build a Vision extraction prompt from model schema."""
        fields_desc = []
        for f in model.fields:
            parts = [f"- **{f.key}** ({f.label})"]
            if f.description:
                parts.append(f"  설명: {f.description}")
            if f.rules:
                parts.append(f"  규칙: {f.rules}")
            parts.append(f"  타입: {f.type}")
            fields_desc.append("\n".join(parts))

        fields_text = "\n".join(fields_desc)

        global_rules = model.global_rules or ""
        global_rules_section = (
            f"\n\n## 전체 규칙\n{global_rules}" if global_rules else ""
        )

        prompt = f"""You are a Vision AI Field Extractor.
You receive an image (photo of a physical object, label, document, etc.) and must extract data into structured JSON.

## TASK
1. LOOK at the image carefully — read ALL visible text (printed AND handwritten).
2. MAP the text to the fields defined below.
3. Return a JSON object with the key "guide_extracted" containing each field.

## OUTPUT FORMAT
For EACH field, return:
{{
  "guide_extracted": {{
    "<field_key>": {{
      "value": "<extracted value or null>",
      "confidence": <0.0-1.0>,
      "source_text": "<exact text seen in image>"
    }}
  }}
}}

## FIELDS TO EXTRACT
{fields_text}
{global_rules_section}

## RULES
- If a field's value is not visible in the image, set value to null and confidence to 0.0.
- For handwritten text, do your best to interpret it and set confidence accordingly (0.3-0.7).
- For clearly printed text, set confidence to 1.0.
- Read text in ALL languages (Korean, English, etc.).
- Read numbers, dates, and codes carefully — do NOT skip digits.
- Return ONLY valid JSON. No markdown, no explanation.
"""
        return prompt

    async def _call_vision_llm(self, messages: list) -> dict:
        """Call GPT-4.1 Vision API with error handling."""
        current_model = get_current_model()
        max_tokens = min(settings.LLM_DEFAULT_MAX_TOKENS, 32768)

        try:
            response = await self.azure_client.chat.completions.create(
                model=current_model,
                messages=messages,
                temperature=0.0,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
        except Exception as e:
            error_msg = str(e)
            logger.error(f"[VisionPipeline] Azure API Error: {error_msg}")
            return {"guide_extracted": {}, "error": f"Vision API Error: {error_msg}"}

        content = response.choices[0].message.content
        try:
            result = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(
                f"[VisionPipeline] JSON Decode Error: {e}. "
                f"Content-Length: {len(content)}"
            )
            return {
                "guide_extracted": {},
                "error": f"Vision output malformed: {str(e)}",
            }

        # Attach token usage
        usage = response.usage
        if usage:
            result["_token_usage"] = {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
            }

        return result

    @staticmethod
    def _guess_mime(filename: str) -> str:
        """Guess MIME type from filename, default to image/jpeg."""
        if not filename:
            return "image/jpeg"
        mime, _ = mimetypes.guess_type(filename)
        if mime and mime.startswith("image/"):
            return mime
        # Common image extensions
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        ext_map = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "bmp": "image/bmp",
            "gif": "image/gif",
            "webp": "image/webp",
            "tiff": "image/tiff",
            "tif": "image/tiff",
        }
        return ext_map.get(ext, "image/jpeg")
