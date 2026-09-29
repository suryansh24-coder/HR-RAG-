"""Reproduce the empty /api/chat/stream body and surface the real exception."""

import os
import tempfile

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.gettempdir()}/hr_sse_probe.db")

import sys

sys.path.insert(0, "backend")

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# Drive the generator directly so the traceback is not swallowed by
# StreamingResponse, which has already sent headers by that point.
from app.api.routes import chat as chat_routes

original = chat_routes.pipeline.stream_query


async def boom(*args, **kwargs):
    raise RuntimeError("probe: pipeline exploded")


try:
    response = client.post(
        "/api/chat/stream",
        json={"question": "What is the annual leave entitlement?", "conversation_id": None},
    )
    print("status:", response.status_code)
    print("body length:", len(response.content))
    print("body repr:", repr(response.content[:400]))
finally:
    chat_routes.pipeline.stream_query = original

print("\n--- now with a real question, full traceback via direct generator call ---")


async def main():
    gen = None
    # Rebuild the same generator the route builds, and step it by hand.
    from app.schemas import ChatRequest

    payload = ChatRequest(question="What is the annual leave entitlement?", conversation_id=None)

    async def fake_request():
        class R:
            async def is_disconnected(self):
                return False

        return R()

    # Call the route function to get the StreamingResponse, then iterate.
    response = await chat_routes.chat_stream(payload, fake_request())
    iterator = response.body_iterator
    try:
        async for chunk in iterator:
            print("CHUNK:", chunk[:200])
    except Exception:
        import traceback

        traceback.print_exc()


import asyncio

asyncio.run(main())
