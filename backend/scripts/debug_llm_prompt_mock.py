import asyncio
import json

# --- Mock Data Structures ---

class FieldDefinition:
    def __init__(self, key, type, description, label=None, rules=None):
        self.key = key
        self.type = type
        self.description = description
        self.label = label or key
        self.rules = rules

class ExtractionModel:
    def __init__(self, id, name, document_type, fields, system_prompt=None, description=None, global_rules=None, reference_data=None, data_structure="data"):
        self.id = id
        self.name = name
        self.document_type = document_type
        self.fields = fields
        self.system_prompt = system_prompt
        self.description = description
        self.global_rules = global_rules
        self.reference_data = reference_data
        self.data_structure = data_structure

# --- LOGIC UNDER TEST (Copied from refiner.py & llm.py) ---

def construct_prompt(model_info, language="en"):
    # 1. Base Context
    prompt = f"""You are an advanced document intelligence AI.
Target Domain: {model_info.name}
Context: {model_info.description or 'General Document'}
"""

    # 2. Global Rules
    if model_info.global_rules:
        prompt += f"\nGLOBAL REFINEMENT RULES:\n{model_info.global_rules}\n"

    # 3. Reference Data
    if model_info.reference_data:
        ref_json = json.dumps(model_info.reference_data, ensure_ascii=False, indent=2)
        prompt += f"""
REFERENCE DATA (Use for value mapping, validation, and context):
{ref_json}

INSTRUCTIONS FOR REFERENCE DATA:
- Use codes/mappings from reference_data for value transformation (e.g., customer code → name)
- Apply validation rules specified in reference_data
- If extracted value doesn't match reference_data patterns, flag with lower confidence
- Reference data takes precedence over guessing
"""

    # 3. Field Instructions
    prompt += "\nREQUIRED EXTRACTION FIELDS:\n"
    for field in model_info.fields:
        prompt += f"- {field.key} ({field.label}):\n"
        prompt += f"  Description: {field.description}\n"
        if field.rules:
            prompt += f"  Refinement Rule: {field.rules}\n"
        prompt += f"  Type: {field.type}\n"

    # 4. Output Formatting
    is_table = model_info.data_structure == 'table' or any(
        getattr(f, 'type', '') == 'table' for f in model_info.fields
    )

    if is_table:
        prompt += f"""
OUTPUT INSTRUCTIONS (TABLE MODE):
You must extract ALL rows from the document. Do NOT truncate or sample.

Return a JSON object where the output key is "rows" (list of objects).
Each object in the list must represent a row.
**CRITICAL**: Use the exact keys defined in the 'REQUIRED EXTRACTION FIELDS' section above.
Do NOT wrap each cell in {{"value": ..., "confidence": ...}} — output flat values directly.

Example format:
{{
  "rows": [
    {{"field_key_1": "value1", "field_key_2": "value2"}},
    ...
  ]
}}

CRITICAL: Extract EVERY row. Missing rows is unacceptable.

LANGUAGE: Translate values to {language} unless the field rule says otherwise.
"""
    else:
        prompt += f"""
OUTPUT INSTRUCTIONS:
User will provide the extraction schema. You must strictly follow it.
Extract ALL valid data rows/fields found in the document.

LANGUAGE: Translate values to {language} unless the field rule says otherwise.
"""
    
    if model_info.system_prompt:
        prompt += f"\nADDITIONAL USER INSTRUCTIONS:\n{model_info.system_prompt}\n"

    return prompt

def build_user_prompt(doc_content):
    return f"""
DOCUMENT CONTENT:
{doc_content}
"""

def _map_field_type(field_type: str) -> dict:
    type_map = {
        "string": {"type": ["string", "null"]},
        "number": {"type": ["number", "null"]},
        "integer": {"type": ["integer", "null"]},
        "boolean": {"type": ["boolean", "null"]},
        "date": {"type": ["string", "null"]},
        "array": {"type": ["array", "null"], "items": {"type": "string"}},
        "table": {"type": ["array", "null"], "items": {"type": "object"}},
    }
    return type_map.get(field_type, {"type": ["string", "null"]})

def build_extraction_schema(model_info):
    field_properties = {}
    field_keys = []

    for field in model_info.fields:
        key = field.key
        field_keys.append(key)
        value_type = _map_field_type(field.type)

        field_properties[key] = {
            "type": "object",
            "properties": {
                "value": value_type,
                "confidence": {"type": "number"},
                "source_text": {"type": ["string", "null"]},
            },
            "required": ["value", "confidence", "source_text"],
            "additionalProperties": False,
        }

    schema = {
        "type": "object",
        "properties": field_properties,
        "required": field_keys,
        "additionalProperties": False,
    }
    return schema

# --- TEST EXECUTION ---

def run_test():
    print("--- Testing Prompt Logic (Stand-alone) ---")

    # 1. Mock Data
    fields = [
        FieldDefinition(key="invoice_number", type="string", description="The invoice number", label="Inv #"),
        FieldDefinition(key="total_amount", type="number", description="Total amount due", rules="Exclude currency symbol"),
        FieldDefinition(key="items", type="table", description="Line items")
    ]
    
    model = ExtractionModel(
        id="test", name="Invoice Model", document_type="Invoice", fields=fields,
        system_prompt="Be precise.", description="Extracts invoice data",
        data_structure="data" 
    )

    ocr_content = "Invoice #12345\nTotal: $500.00"

    # 2. Generate
    sys_prompt = construct_prompt(model)
    user_prompt = build_user_prompt(ocr_content)
    schema = build_extraction_schema(model)

    # 3. Validation
    print("\n[SYSTEM PROMPT CHECK]")
    if "invoice_number" in sys_prompt and "Exclude currency symbol" in sys_prompt:
        print("PASS: Fields and rules included.")
    else:
        print("FAIL: Missing fields in system prompt.")
        print(sys_prompt)

    print("\n[USER PROMPT CHECK]")
    if "Invoice #12345" in user_prompt:
        print("PASS: OCR content included.")
    else:
        print("FAIL: OCR content missing.")
    
    print("\n[SCHEMA CHECK]")
    if "invoice_number" in schema["properties"] and schema["properties"]["invoice_number"]["required"] == ["value", "confidence", "source_text"]:
        print("PASS: Schema structure correct (value, confidence, source_text).")
    else:
        print("FAIL: Schema malformed.")
        print(json.dumps(schema, indent=2))

if __name__ == "__main__":
    run_test()
