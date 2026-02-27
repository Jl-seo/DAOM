import base64
import re

# Simulate a slightly off-padding base64 string
test_str = "JVBERi0xLjcKCjEK" + "==" # Too much padding

b64_str = re.sub(r'[^a-zA-Z0-9+/=]', '', test_str)
print("Len before padding fix:", len(b64_str))

padding_needed = len(b64_str) % 4
if padding_needed:
    b64_str += '=' * (4 - padding_needed)

print("Len after padding fix:", len(b64_str))

try:
    print("Validate=True")
    base64.b64decode(b64_str, validate=True)
except Exception as e:
    print("Error:", e)
    
try:
    print("Validate=False")
    base64.b64decode(b64_str, validate=False)
except Exception as e:
    print("Error:", e)
