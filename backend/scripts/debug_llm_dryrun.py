import asyncio
import sys
import os
from unittest.mock import MagicMock, patch

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock key dependencies BEFORE importing app modules
sys.modules['app.db.cosmos'] = MagicMock()
sys.modules['app.core.config'] = MagicMock()
sys.modules['app.services.audit'] = MagicMock()

# Now import target modules
from app.services import llm
from app.schemas.model import ExtractionModel, FieldDefinition

async def dry_run_extraction():
    print("--- Dry Run LLM Extraction ---")

    # 1. Setup Data
    model = ExtractionModel(
        id="dry-run", 
        name="Dry Run Model", 
        document_type="Invoice",
        fields=[
            FieldDefinition(key="invoice_no", type="string", description="Invoice Number"),
            FieldDefinition(key="total", type="number", description="Total Amount")
        ]
    )
    
    # Simulate OCR output (parsed_content)
    parsed_content = {
        "content": "Invoice #9999\nTotal: $1,234.56",
        "tables": []
    }

    # 2. Mock OpenAI Client & Response
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content='{"invoice_no": {"value": "9999"}}'))
    ]
    
    # 3. Intercept the call
    print("Intercepting llm.call_llm_single...")
    
    # We want to see what 'user_prompt' and 'system_prompt' are passed to call_llm_single
    original_call = llm.call_llm_single
    
    async def intercept_call(system_prompt, user_prompt, model_info=None):
        print("\n[INTERCEPTED] System Prompt:")
        print(system_prompt[:500] + "..." if len(system_prompt) > 500 else system_prompt)
        print("\n[INTERCEPTED] User Prompt:")
        print(user_prompt[:500] + "..." if len(user_prompt) > 500 else user_prompt)
        
        if "Invoice #9999" in user_prompt:
             print("\n[PASS] OCR Content is present in User Prompt.")
        else:
             print("\n[FAIL] OCR Content is MISSING in User Prompt.")
             
        if "invoice_no" in system_prompt or (model_info and "invoice_no" in str(model_info.fields)):
             print("[PASS] Schema/Fields are present.")

        return {"result": {"invoice_no": {"value": "9999"}}, "_token_usage": {}}

    # Verify logic
    with patch('app.services.llm.call_llm_single', side_effect=intercept_call):
        await llm.extract_with_llm(model, parsed_content)

if __name__ == "__main__":
    asyncio.run(dry_run_extraction())
