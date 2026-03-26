"""
Event classification service.

Sends the cleaned article to Claude and returns a strictly typed Event object.
The LLM call is wrapped in asyncio.to_thread so it doesn't block the event loop.
"""

import asyncio
import json
import logging
from pathlib import Path

from backend.schemas.article import Article
from backend.schemas.event import Event, EventType, Direction, Magnitude, TimeHorizon
from backend.services import llm_client

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "classify_event.txt"
_SYSTEM_PROMPT: str | None = None

# Max article characters forwarded to the classifier — enough context, not wasteful
_MAX_TEXT_CHARS = 8_000


class ClassificationError(Exception):
    """Raised when classification fails or the LLM returns unusable output."""


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

async def classify_event(article: Article) -> Event:
    """
    Classify the market event described in *article*.

    Returns a typed Event. Raises ClassificationError on unrecoverable failure.
    """
    system_prompt = _load_system_prompt()
    user_prompt = _build_user_prompt(article)

    logger.info("Classifying event for article: %s", article.title[:80])

    try:
        raw = await asyncio.to_thread(llm_client.complete, system_prompt, user_prompt)
    except Exception as exc:
        raise ClassificationError(f"LLM call failed: {exc}") from exc

    event = _parse_response(raw)
    logger.info(
        "Classification result: type=%s direction=%s magnitude=%s confidence=%.2f",
        event.event_type,
        event.direction,
        event.magnitude,
        event.confidence,
    )
    return event


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _load_system_prompt() -> str:
    global _SYSTEM_PROMPT
    if _SYSTEM_PROMPT is None:
        _SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")
    return _SYSTEM_PROMPT


def _build_user_prompt(article: Article) -> str:
    text_preview = article.text[:_MAX_TEXT_CHARS]
    return (
        f"Title: {article.title}\n"
        f"Source: {article.source_domain}\n\n"
        f"{text_preview}"
    )


def _parse_response(raw: str) -> Event:
    """Parse and validate the LLM JSON response into a typed Event."""
    cleaned = _strip_markdown_fences(raw)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ClassificationError(
            f"LLM returned invalid JSON: {exc}\nRaw output (first 500 chars): {raw[:500]}"
        ) from exc

    if not isinstance(data, dict):
        raise ClassificationError(f"Expected a JSON object, got {type(data).__name__}")

    return Event(
        event_type=_coerce_enum(data.get("event_type"), EventType, EventType.OTHER),
        event_summary=str(data.get("event_summary") or ""),
        focal_entities=_coerce_list(data.get("focal_entities")),
        direction=_coerce_enum(data.get("direction"), Direction, Direction.NEUTRAL),
        magnitude=_coerce_enum(data.get("magnitude"), Magnitude, Magnitude.LOW),
        time_horizon=_coerce_enum(data.get("time_horizon"), TimeHorizon, TimeHorizon.WEEKS),
        economic_mechanism=str(data.get("economic_mechanism") or ""),
        confidence=_coerce_float(data.get("confidence"), 0.5),
    )


def _strip_markdown_fences(text: str) -> str:
    """Remove ```json ... ``` wrappers that some models emit despite instructions."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    # Drop first line (```json or ```) and last line if it's a closing fence
    start = 1
    end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
    return "\n".join(lines[start:end])


def _coerce_enum(value, enum_class, default):
    if value is None:
        return default
    try:
        return enum_class(str(value).lower())
    except ValueError:
        logger.warning(
            "Unknown %s value %r — falling back to %s",
            enum_class.__name__, value, default.value,
        )
        return default


def _coerce_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if v]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _coerce_float(value, default: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default
