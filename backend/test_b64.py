import base64
import re

# Simulate a URL-safe Base64 string that got passed and stripped.
# First, encode "Test PDF content"
msg = b"Test PDF content"
b64_normal = base64.b64encode(msg).decode('utf-8')
b64_urlsafe = base64.urlsafe_b64encode(msg).decode('utf-8')

print("Normal:", b64_normal)
print("URL Safe:", b64_urlsafe)

# Current code logic
stripped = re.sub(r'[^a-zA-Z0-9+/=]', '', b64_urlsafe)
print("Stripped:", stripped)

try:
    print(base64.b64decode(stripped))
except Exception as e:
    print("Error:", e)
