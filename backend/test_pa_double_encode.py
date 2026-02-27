import base64
import re
import json

def test_pa_double_encode():
    # 1. Real PDF Base64
    msg = b"%PDF-1.4\n1 0 obj\n<<"
    real_b64 = base64.b64encode(msg).decode('utf-8')
    
    # 2. Suppose PA wraps it in a dict, then accidentally base64 encodes the dict instead of the file content
    pa_obj = json.dumps({"$content-type": "application/pdf", "$content": real_b64}).encode('utf-8')
    double_encoded_b64 = base64.b64encode(pa_obj).decode('utf-8')
    
    print("Direct Base64:", real_b64)
    print("PA Double Encode Base64:", double_encoded_b64)
    
    # Let's decode double_encoded using our backend logic
    # Assume it arrives as `raw_content = double_encoded_b64` (a string)
    b64_str = double_encoded_b64.strip()
    
    b64_str = b64_str.replace('-', '+').replace('_', '/')
    b64_str = re.sub(r'[^a-zA-Z0-9+/=]', '', b64_str)
    
    padding_needed = len(b64_str) % 4
    if padding_needed:
        b64_str += '=' * (4 - padding_needed)
        
    decoded_file_content = base64.b64decode(b64_str, validate=True)
    
    # My "Defensive Check" from earlier:
    is_metadata = decoded_file_content.startswith(b'{') or decoded_file_content.startswith(b'[')
    
    print("Decoded snippet:", decoded_file_content[:50])
    print("Is Metadata Triggered?", is_metadata)
    
test_pa_double_encode()
