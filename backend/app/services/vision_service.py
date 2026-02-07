import logging
from typing import Optional
from azure.ai.vision.imageanalysis import ImageAnalysisClient
from azure.ai.vision.imageanalysis.models import VisualFeatures
from azure.core.credentials import AzureKeyCredential
from app.core.config import settings

logger = logging.getLogger(__name__)

class VisionService:
    @staticmethod
    def get_client() -> Optional[ImageAnalysisClient]:
        endpoint = settings.AZURE_AIPROJECT_ENDPOINT or settings.AZURE_Form_ENDPOINT # Use shared endpoint if possible or specific one
        # Note: Vision Image Analysis creates a separate endpoint usually.
        # But if the user said "Foundry", it might be the unified endpoint.
        # Let's try to use the AZURE_AIPROJECT_ENDPOINT first.

        key = settings.AZURE_OPENAI_API_KEY or settings.AZURE_FORM_KEY # Try to reuse keys

        # Typically Vision needs its own Endpoint/Key if it's the "Computer Vision" resource.
        # But let's assume standard Config or Fallback.
        # For now, I'll rely on settings.AZURE_AIPROJECT_ENDPOINT and AZURE_OPENAI_API_KEY as 'Foundry' config.

        if not endpoint or not key:
            logger.warning("[VisionService] Missing configuration")
            return None

        try:
            return ImageAnalysisClient(
                endpoint=endpoint,
                credential=AzureKeyCredential(key)
            )
        except Exception as e:
            logger.error(f"[VisionService] Failed to create client: {e}")
            return None

    @staticmethod
    def analyze_image(image_url: str):
        """
        Analyze image for Tags, Objects, and Dense Captions using Vision 4.0
        """
        client = VisionService.get_client()
        if not client:
            return None

        try:
            result = client.analyze_from_url(
                image_url=image_url,
                visual_features=[
                    VisualFeatures.TAGS,
                    VisualFeatures.OBJECTS,
                    VisualFeatures.DENSE_CAPTIONS,
                    # VisualFeatures.COLOR # Not in v4.0 standard SDK enum sometimes? Let's check.
                    # If not available, Tags often cover colors "red shirt".
                    # Let's stick to Safe features.
                    VisualFeatures.CAPTION
                ]
            )

            # Simplify Output for LLM Consumption
            description = []
            if result.caption:
                description.append(f"Caption: {result.caption.text}")

            if result.dense_captions:
                for dc in result.dense_captions[:5]: # Top 5 details
                    description.append(f"Detail at {dc.bounding_box}: {dc.text}")

            if result.tags:
                tags = [t.name for t in result.tags if t.confidence > 0.8]
                description.append(f"Tags: {', '.join(tags)}")

            if result.objects:
                 objs = [f"{o.tags[0].name} at {o.bounding_box}" for o in result.objects]
                 description.append(f"Objects: {', '.join(objs)}")

            return "\n".join(description)

        except Exception as e:
            logger.error(f"[VisionService] Analysis failed: {e}")
            return f"Vision Analysis Failed: {e}"
