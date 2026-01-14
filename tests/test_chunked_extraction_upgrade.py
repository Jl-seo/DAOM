import asyncio
import unittest
import sys
import os
import json
from unittest.mock import MagicMock, AsyncMock, patch

# --- MOCK DEPENDENCIES BEFORE IMPORT ---
# We need to mock 'openai' and 'app.core.config' because they might not work in this test env

# Mock openai
mock_openai = MagicMock()
mock_openai.AsyncAzureOpenAI = MagicMock()
sys.modules["openai"] = mock_openai

# Mock app.core.config
mock_config = MagicMock()
mock_config.settings = MagicMock()
mock_config.settings.AZURE_OPENAI_API_KEY = "fake_key"
mock_config.settings.AZURE_OPENAI_API_VERSION = "2023-05-15"
mock_config.settings.AZURE_OPENAI_ENDPOINT = "https://fake.openai.azure.com"
sys.modules["app.core.config"] = mock_config

# Mock app.services.llm
mock_llm = MagicMock()
mock_llm.get_current_model.return_value = "gpt-4"
sys.modules["app.services.llm"] = mock_llm

# Add backend directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

from app.services import chunked_extraction

class TestChunkedExtractionUpgrade(unittest.TestCase):
    def setUp(self):
        self.mock_doc_intel = {
            "content": "Page 1 Content\nPage 2 Content",
            "pages": [
                {"pageNumber": 1, "content": "Page 1 Content", "width": 100, "height": 100},
                {"pageNumber": 2, "content": "Page 2 Content", "width": 100, "height": 100}
            ],
            "paragraphs": [],
            "tables": []
        }
        self.model_fields = [{"key": "test_field", "label": "Test Field"}]

    def test_extract_with_chunking_returns_rich_data(self):
        # We don't need @patch for AsyncAzureOpenAI since we mocked the module
        # But we need to mock the client instance returned by the constructor
        
        mock_client = AsyncMock()
        # when AsyncAzureOpenAI() is called, return mock_client
        mock_openai.AsyncAzureOpenAI.return_value = mock_client
        
        # Mock Response for Chunk 1
        mock_response_1 = MagicMock()
        mock_response_1.choices[0].message.content = json.dumps({
            "guide_extracted": {
                "test_field": {
                    "value": "Value Page 1", 
                    "confidence": 0.9, 
                    "bbox": [10, 10, 20, 20], 
                    "page_number": 1
                }
            },
            "other_data": []
        })
        
        # Mock Response for Chunk 2
        mock_response_2 = MagicMock()
        mock_response_2.choices[0].message.content = json.dumps({
            "guide_extracted": {
                "test_field": None 
            },
            "other_data": []
        })

        mock_client.chat.completions.create.side_effect = [mock_response_1, mock_response_2]

        # Run extraction
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        merged, errors = loop.run_until_complete(
            chunked_extraction.extract_with_chunking(
                self.mock_doc_intel, 
                self.model_fields,
                max_tokens_per_chunk=1, # Force split
                max_concurrent=1
            )
        )
        loop.close()

        print("\nMerged Result:", json.dumps(merged, indent=2))
        
        # Verify Structure
        self.assertIn("test_field", merged)
        field_data = merged["test_field"]
        
        self.assertIsInstance(field_data, dict)
        self.assertEqual(field_data["value"], "Value Page 1")
        self.assertEqual(field_data["bbox"], [10, 10, 20, 20])
        self.assertEqual(field_data["page_number"], 1)
        
        print("Success! Rich data extracted correctly.")
if __name__ == '__main__':
    unittest.main()
