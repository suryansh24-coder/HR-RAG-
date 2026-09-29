import json

import urllib.request

payload = json.dumps({"question": "What is the annual leave entitlement?", "conversation_id": None}).encode()
request = urllib.request.Request(
    "http://127.0.0.1:8000/api/chat/stream",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(request, timeout=90) as response:
    raw = response.read()
print(repr(raw))
