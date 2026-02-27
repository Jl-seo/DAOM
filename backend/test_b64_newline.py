import base64
import re

def sim_power_automate_decode(raw_content_bytes_node):
    # Simulate the logic in power_automate.py
    b64_str = raw_content_bytes_node.get("$content", "")
    
    # Simulate URL-safe replacements
    b64_str = b64_str.replace('-', '+').replace('_', '/')
    
    # Remove all non-base64 characters (e.g. whitespace, newlines injected by PA)
    b64_str = re.sub(r'[^a-zA-Z0-9+/=]', '', b64_str)
    
    # Fix padding
    padding_needed = len(b64_str) % 4
    if padding_needed:
        b64_str += '=' * (4 - padding_needed)
    
    try:
        # validate=True will fail if there are any non-alphabet characters remaining.
        # But we just stripped them, so it should be fine.
        decoded = base64.b64decode(b64_str, validate=True)
        print(f"Success! Decoded {len(decoded)} bytes.")
        return decoded
    except Exception as e:
        print(f"Failed to decode: {e}")
        return None

# Test with various common Power Automate corruptions:
# 1. Newlines inserted every 76 characters
# 2. Incomplete padding
test_string = "JVBERi0xLjcKCjEgMCBvYmogICUKPDwK" + "\r\n" + "L1R5cGUgL0NhdGFsb2cKL1BhZ2VzIDIgMCBSDgo+PgplbmRvYmoKCjIgMCBvYmoKPDwKL1R5cGUgL1BhZ2VzCi9LaWRzIFszIDAgUl0KL0NvdW50IDEKPj4KZW5kb2JqCgplbmQ="

sim_power_automate_decode({"$content": test_string})
sim_power_automate_decode({"$content": test_string.replace("\r\n", " ")})
