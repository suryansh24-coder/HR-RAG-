"""Drive the frontend's SSE parser against the live backend.

The frontend unit tests exercise `streamChat` with synthetic SSE. This script
answers the question the mocks cannot: does the real server's SSE framing
actually parse into the events the UI expects?

It imports the real client module by rewriting its TypeScript-isms at load
time, so the parsing logic under test is the shipped logic, not a copy.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
CLIENT_TS = FRONTEND / "src" / "api" / "client.ts"


def find_esbuild() -> str:
    """Locate the real esbuild executable.

    `node_modules/.bin/esbuild` is a shell shim, and on Windows the binary lives
    inside the platform package, so glob for the `.exe` rather than guessing.
    """
    for pattern in (
        "node_modules/@esbuild/win32-x64/esbuild.exe",
        "node_modules/@esbuild/*/esbuild.exe",
    ):
        matches = sorted(FRONTEND.glob(pattern))
        if matches:
            return str(matches[0])
    raise SystemExit("esbuild not found; run `npm install` in frontend/")


def main() -> int:
    import urllib.request

    def post(path: str, payload: dict) -> tuple[int, bytes]:
        request = urllib.request.Request(
            f"http://127.0.0.1:8000{path}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    with urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=20) as response:
        health = json.loads(response.read())
    print(f"backend health: {health['status']}")

    with tempfile.TemporaryDirectory() as tmp:
        bundled = Path(tmp) / "client.mjs"
        # esbuild is already a frontend dependency; using it to transpile means
        # the code under test is the shipped source, not a hand-rewritten copy.
        transpile = subprocess.run(
            [
                find_esbuild(), str(CLIENT_TS),
                "--bundle", "--format=esm", "--platform=node",
                f"--outfile={bundled}",
            ],
            capture_output=True, text=True, cwd=FRONTEND,
        )
        if transpile.returncode != 0:
            print("TRANSPILE FAILED")
            print(transpile.stderr[-3000:])
            return 1

        script = Path(tmp) / "harness.mjs"
        script.write_text(
            f"""
import {{ streamChat }} from "./client.mjs";

// The client uses same-origin relative URLs, which a browser resolves against
// the page. Node's fetch needs an absolute URL, so resolve it here rather than
// changing the client, which must keep working behind the nginx proxy.
const ORIGIN = "http://127.0.0.1:8000";
const realFetch = globalThis.fetch;
globalThis.fetch = (input, init) =>
  realFetch(typeof input === "string" && input.startsWith("/") ? ORIGIN + input : input, init);

const events = [];
await streamChat("What is the annual leave entitlement?", null, {{
  onEvent: (event) => events.push(event),
}});
console.log(JSON.stringify(events));
""",
            encoding="utf-8",
        )
        completed = subprocess.run(
            ["node", str(script)], capture_output=True, text=True, timeout=180, cwd=tmp
        )

    if completed.returncode != 0:
        print("HARNESS FAILED")
        print(completed.stdout[-3000:])
        print(completed.stderr[-3000:])
        return 1

    events = json.loads(completed.stdout.strip().splitlines()[-1])
    stages = [event["stage"] for event in events]
    print(f"stream stages: {' -> '.join(stages)}")

    failures: list[str] = []
    expected = ["start", "retrieving", "sources", "generating", "complete"]
    if stages[: len(expected)] != expected:
        failures.append(f"stage order was {stages}, expected prefix {expected}")

    complete = next((event for event in events if event["stage"] == "complete"), None)
    if complete is None:
        failures.append("no complete event")
    else:
        data = complete["data"]
        answer = str(data.get("answer", ""))
        sources = data.get("sources") or []
        print(f"answer ({len(answer)} chars): {answer[:160]}")
        print(f"sources: {len(sources)}")
        for source in sources:
            print(f"  - {source.get('citation')} score={source.get('score')}")
            if "score" not in source:
                failures.append("source is missing `score` - the UI would render undefined")
            if "snippet" not in source:
                failures.append("source is missing `snippet`")
            if "citation" not in source:
                failures.append("source is missing `citation`")
        if not sources:
            failures.append("grounded answer carried no sources")
        if not data.get("context_used"):
            failures.append("context_used was false for a grounded answer")

    # The ungrounded path must also parse, since the UI renders a distinct
    # refusal state from `no_context`.
    status, body = post("/api/chat", {"question": "What is the CEO's home address?"})
    refusal = json.loads(body)
    print(f"refusal path: status={status} no_context={refusal.get('no_context')}")
    if not refusal.get("no_context"):
        failures.append("out-of-scope question was not refused")

    if failures:
        print("\nFAILURES:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("\nPASS: live SSE parsed into the stages and fields the UI renders")
    return 0


if __name__ == "__main__":
    sys.exit(main())
