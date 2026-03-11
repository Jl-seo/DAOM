import asyncio
import os
import json
from dotenv import load_dotenv

load_dotenv(".env")
from app.services.comparison_service import compare_images
from app.services.llm import get_openai_client, get_current_model
import logging

logging.basicConfig(level=logging.INFO)

async def main():
    img1 = "https://picsum.photos/seed/img1/600/400"
    img2 = "https://picsum.photos/seed/img2/600/400"

    comp_settings = {
        "confidence_threshold": 0.85,
        "ignore_position_changes": True,
        "ignore_color_changes": False,
        "ignore_font_changes": True,
        "ignore_compression_noise": True,
        "custom_ignore_rules": None,
        "output_language": "Korean",
        "use_ssim_analysis": True,  # Will be mocked
        "use_vision_analysis": False,
        "align_images": True,
        "allowed_categories": None,
        "excluded_categories": ["missing_element", "layout", "style", "added_element"],
        "ssim_identity_threshold": 0.95
    }

    import app.services.comparison_service as comp_svc
    
    # Mock pixel diff to force LLM call
    import app.services.pixel_diff as pd
    async def mock_ssim(url1, url2, align):
        return {
            "score": 0.33,
            "diffs": [{"bbox": [0,0,10,10], "diff_score": 0.5}],
            "align_success": True
        }
    pd.calculate_ssim = mock_ssim
    
    # Mock vision service to not fail
    import app.services.vision_service as vs
    def mock_vision(url):
        return "Image with random visual features"
    vs.VisionService.analyze_image = mock_vision

    original_create = None
    
    class HookedClient:
        def __init__(self, real_client):
            self.real_client = real_client
            self.chat = self.Chat(self.real_client.chat)
            
        class Chat:
            def __init__(self, real_chat):
                self.completions = self.Completions(real_chat.completions)
                
            class Completions:
                def __init__(self, real_comp):
                    self.real_comp = real_comp
                    
                async def create(self, **kwargs):
                    print("--- LLM PROMPT ---")
                    print(json.dumps(kwargs.get('messages', [])[0]['content'], indent=2, ensure_ascii=False)[:3000])
                    print("------------------")
                    resp = await self.real_comp.create(**kwargs)
                    print("--- LLM RAW RESPONSE ---")
                    print(resp.choices[0].message.content)
                    print("------------------------")
                    return resp

    orig_get_client = comp_svc.get_openai_client
    def hooked_get_client():
        return HookedClient(orig_get_client())
    comp_svc.get_openai_client = hooked_get_client

    result = await compare_images(
        image_url_1=img1,
        image_url_2=img2,
        comparison_settings=comp_settings
    )
    
    print("FINAL RESULT:", json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())
