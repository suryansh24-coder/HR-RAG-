"""Deterministic prompt construction for grounded RAG generation.

The prompt is deliberately explicit about grounding rules because the entire
value of the product is that an employee can trust the answer. Three blocks are
assembled:

1. **System instructions** — role, grounding rules, citation rules, refusal
   behaviour and formatting expectations.
2. **Retrieved context** — numbered, provenance-stamped passages.
3. **User question** — optionally with the recent conversation turns so the
   model can resolve follow-up references ("what about carry forward?").

No LangChain prompt templates are used; the builder is a plain, testable function.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings

SYSTEM_INSTRUCTIONS = """You are HR Nexus, the intelligent HR knowledge assistant.

You answer questions about company HR policy using ONLY the retrieved knowledge base
context provided below. The context is the single source of truth for this answer.

Ground rules:
1. Every policy fact in your answer MUST come from the retrieved context.
2. Never invent policies, entitlements, numbers, dates, names, contacts, forms or
   procedures. If a detail is not in the context, leave it out.
3. Never invent citations. Only reference sources that appear in the context, using
   their exact filename and page number.
4. If the context is insufficient to answer, reply with exactly this sentence and
   nothing else: "{no_context}"
5. Separate clearly between:
   - Company policy (what the retrieved documents state), and
   - General guidance (how something is typically handled), labelling the latter as
     general guidance and never presenting it as company policy.
6. If a policy value varies by grade, location, tenure or employee category, state
   those conditions explicitly.
7. If the question is not about HR, briefly explain that you can only answer HR
   knowledge base questions and suggest a relevant HR topic.
8. If the context contains conflicting statements, say so and point to both sources
   instead of silently choosing one.

Style:
- Lead with a direct one-sentence answer.
- Then add supporting detail in short paragraphs or a compact bullet list.
- Keep the whole answer under 200 words unless the user asks for more detail.
- Use plain professional language. Do not use markdown tables."""


USER_PROMPT = "Question: {question}"

NO_CONTEXT_SYSTEM = """You are HR Nexus, the intelligent HR knowledge assistant.

No relevant HR knowledge base passages were retrieved for this question, so you have
no basis for an answer.

Reply with exactly this sentence and nothing else:
{no_context}"""


@dataclass
class PromptBundle:
    system: str
    user: str

    def as_messages(self) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": self.system},
            {"role": "user", "content": self.user},
        ]


def format_history(history: list[dict[str, str]], max_turns: int) -> str:
    """Render the last ``max_turns`` user turns as context for follow-ups."""
    turns = [turn for turn in history if turn.get("role") == "user"][-max_turns:]
    if not turns:
        return ""
    lines = "\n".join(f"- {turn['content'].strip()}" for turn in turns)
    return f"RECENT QUESTIONS IN THIS CONVERSATION:\n{lines}\n\n"


def build_prompt(
    question: str,
    context: str,
    history: list[dict[str, str]] | None = None,
) -> PromptBundle:
    """Build the grounded prompt for a question that *has* retrieved context."""
    history_block = format_history(history or [], settings.HISTORY_TURNS)
    system = (
        SYSTEM_INSTRUCTIONS.format(no_context=settings.NO_CONTEXT_RESPONSE)
        + "\n\n"
        + "RETRIEVED CONTEXT:\n"
        + context
    )
    user = history_block + USER_PROMPT.format(question=question)
    return PromptBundle(system=system, user=user)


def build_no_context_prompt(question: str) -> PromptBundle:
    """Build the prompt used when retrieval found nothing relevant."""
    return PromptBundle(
        system=NO_CONTEXT_SYSTEM.format(no_context=settings.NO_CONTEXT_RESPONSE),
        user=USER_PROMPT.format(question=question),
    )


def build_messages(
    question: str,
    context: str,
    history: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """Backwards-compatible helper returning raw chat-completion messages."""
    if not context.strip():
        return build_no_context_prompt(question).as_messages()
    return build_prompt(question, context, history).as_messages()
