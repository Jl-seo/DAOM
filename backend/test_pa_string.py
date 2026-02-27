import json
import base64
import re

def test_pa_stringification():
    # 1. Real PDF base64 string
    real_b64 = "JVBERi0xLjQKJcOkw7zDtsO5CjEgMCBvYmoKPDwvV" + "=" * 5
    
    # 2. How Power Automate actually structure a single file upload JSON natively
    single_file_payload = {
        "name": "test.pdf",
        "contentBytes": {
            "$content-type": "application/pdf",
            "$content": real_b64
        }
    }
    
    # 3. How Power Automate serializes an array when passed as a string variable
    array_payload = [single_file_payload]
    stringified_array = json.dumps(array_payload)
    
    print("Stringified Array:", stringified_array[:100] + "...")
    
    # 4. How Pydantic Validator parses it
    parsed_files = json.loads(stringified_array)
    file_item = parsed_files[0]
    
    raw_content = file_item["contentBytes"]
    
    # 5. Extract logic from batch-upload
    if isinstance(raw_content, dict):
        b64_str = raw_content.get("$content", "")
    elif isinstance(raw_content, str):
        b64_str = raw_content.strip()
        if b64_str.startswith("{") and "$content" in b64_str:
            try:
                content_dict = json.loads(b64_str)
                b64_str = content_dict.get("$content", b64_str)
            except json.JSONDecodeError:
                pass

    print("Extracted B64:", b64_str[:50] + "...")
    print("Equals Original?", b64_str == real_b64)
    
test_pa_stringification()
