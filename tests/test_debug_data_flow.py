import asyncio
import unittest
import sys
import os
from unittest.mock import MagicMock, patch

# --- MOCK DEPENDENCIES BEFORE IMPORT ---
# Mock everything that might be missing or complex to load
sys.modules["pydantic"] = MagicMock()
sys.modules["pydantic"].BaseModel = MagicMock
sys.modules["app.db.cosmos"] = MagicMock()
sys.modules["app.services.audit"] = MagicMock()
sys.modules["app.core.enums"] = MagicMock()
# Mock enums specifically as they are accessed as values
mock_enums = MagicMock()
mock_enums.ExtractionStatus.PENDING.value = "pending"
mock_enums.ExtractionType.JOB.value = "extraction_job"
sys.modules["app.core.enums"] = mock_enums

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

from app.services import extraction_jobs

class TestDebugDataFlow(unittest.TestCase):
    
    @patch("app.services.extraction_jobs.get_extractions_container")
    def test_update_job_saves_debug_data(self, mock_get_container):
        # Setup Mock Container
        mock_container = MagicMock()
        mock_get_container.return_value = mock_container
        
        job_id = "test-job-id"
        original_job_data = {
            "id": job_id,
            "type": "extraction_job",
            "status": "pending",
            "model_id": "test-model",
            "user_id": "test-user",
            "filename": "test.pdf",
            "file_url": "http://fake.url/test.pdf",
            "created_at": "2023-01-01T00:00:00",
            "updated_at": "2023-01-01T00:00:00"
        }
        
        # When querying logic calls query_items, return the original job
        mock_container.query_items.return_value = [original_job_data]
        
        # Action: Update job with debug_data
        debug_info = {
            "doc_intel": {"pages": 5, "model": "prebuilt-layout"}, 
            "llm_prompt": "Extract content..."
        }
        updated_job = extraction_jobs.update_job(job_id, debug_data=debug_info)
        
        # Assertions
        self.assertIsNotNone(updated_job)
        self.assertEqual(updated_job.debug_data, debug_info)
        
        # Verify upsert_item was called with debug_data in the body
        args, kwargs = mock_container.upsert_item.call_args
        saved_body = kwargs['body']
        
        self.assertEqual(saved_body["id"], job_id)
        self.assertEqual(saved_body["debug_data"], debug_info)
        print("\nSuccess! debug_data passed to Cosmos DB upsert.")

if __name__ == '__main__':
    unittest.main()
