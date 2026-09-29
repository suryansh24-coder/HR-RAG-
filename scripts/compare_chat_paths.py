import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"


def post(path, payload, timeout=90):
    request = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


question = "What is the annual leave entitlement?"

status, body = post("/api/chat", {"question": question, "conversation_id": None})
print(f"BUFFERED /api/chat  -> status={status} bytes={len(body)}")
if status == 200:
    data = json.loads(body)
    print(f"   answer: {data['answer'][:110]}")
    print(f"   sources: {len(data['sources'])}  conversation={data['conversation_id']}")
else:
    print("   ", body[:300])

status, body = post("/api/chat/stream", {"question": question, "conversation_id": None})
print(f"STREAM  /api/chat/stream -> status={status} bytes={len(body)}")
print(f"   repr: {body[:300]!r}")

status, body = post("/api/chat/suggestions", {"question": question})
print(f"SUGGEST /api/chat/suggestions -> status={status} bytes={len(body)}")
