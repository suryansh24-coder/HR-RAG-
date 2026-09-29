import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.rag.generation.providers.extractive import ExtractiveProvider

ctx = """[1] source=fictional_attendance_policy.pdf, page=2
Overtime
Overtime is not paid. Time worked beyond 40 hours in a week is taken back as time off in lieu, which must be taken within the following calendar month. Approval for overtime is required in advance from the direct manager. Overtime that is not pre-approved is treated as a policy breach."""

p = ExtractiveProvider()
passages = p._parse_context(ctx)
for f, pg, s in passages:
    print(f"  p{pg} {s[:110]!r}")
print("----")
print(asyncio.run(p.complete("RETRIEVED CONTEXT:\n" + ctx, "Question: How is overtime compensated?")))
