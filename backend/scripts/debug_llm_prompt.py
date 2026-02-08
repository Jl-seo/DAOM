import asyncio
import sys
import os
import json
from unittest.mock import MagicMock

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.refiner import RefinerEngine
from app.services import llm
from app.schemas.model import ExtractionModel, FieldDefinition

async def debug_prompt_generation():
    print("--- Debugging LLM Prompt Generation ---")

    # 1. Mock Data
    parsed_content = {
        "content": "Invoice #12345\nTotal: $500.00\nDate: 2023-10-27",
        "tables": []
    }
    
    fields = [
        FieldDefinition(key="invoice_number", type="string", description="The invoice number"),
        FieldDefinition(key="total_amount", type="number", description="Total amount due"),
        FieldDefinition(key="invoice_date", type="date", description="Date of issue")
    ]
    
    mock_model = ExtractionModel(
        id="test-model",
        name="Test Model",
        document_type="Invoice",
        fields=fields,
        system_prompt="Extract invoice details." # User-defined prompt
    )

    # 2. Test Prompt Construction
    print("\n[ACTION] Calling RefinerEngine.construct_prompt...")
    try:
        # Check signature of construct_prompt in refiner.py
        # Assuming it takes (model, parsed_content)
        system_prompt, user_prompt = RefinerEngine.construct_prompt(mock_model, parsed_content)
        
        print("\n=== SYSTEM PROMPT ===")
        print(system_prompt)
        print("\n=== USER PROMPT ===")
        print(user_prompt)
        
        # Check if OCR content is in user prompt
        if "Invoice #12345" in user_prompt:
            print("\n[SUCCESS] OCR content found in User Prompt.")
        else:
            print("\n[FAILURE] OCR content MISSING in User Prompt!")

        # Check if fields are in system prompt (or schema)
        if "invoice_number" in system_prompt or "invoice_number" in user_prompt:
             print("[INFO] Field keys found in prompts (might be handled by Structured Outputs schema).")
        
    except Exception as e:
        print(f"\n[ERROR] Prompt generation failed: {e}")

    # 3. Test Schema Generation
    print("\n[ACTION] Testing Schema Generation (llm.py)...")
    try:
        schema = llm.build_extraction_schema(mock_model)
        print(json.dumps(schema, indent=2))
        
        if "invoice_number" in schema["properties"]:
             print("\n[SUCCESS] Schema correctly includes 'invoice_number'.")
        else:
             print("\n[FAILURE] Schema MISSING field definitions!")

    except Exception as e:
        print(f"\n[ERROR] Schema generation failed: {e}")

if __name__ == "__main__":
    asyncio.run(debug_prompt_generation())
