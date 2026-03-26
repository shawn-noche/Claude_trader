"""
Thin wrapper around the Anthropic API.

All LLM calls go through this module so model swaps, retry logic,
and token accounting are handled in one place.
"""

import logging
import anthropic

from backend.config import settings

logger = logging.getLogger(__name__)

_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


def complete(system_prompt: str, user_prompt: str) -> str:
    """
    Send a single-turn completion request.

    Returns the text content of the first content block.
    Raises anthropic.APIError on failure.
    """
    client = get_client()
    logger.debug("LLM request — model=%s, system_len=%d, user_len=%d",
                 settings.claude_model, len(system_prompt), len(user_prompt))

    message = client.messages.create(
        model=settings.claude_model,
        max_tokens=settings.llm_max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    text = message.content[0].text
    logger.debug("LLM response — stop_reason=%s, output_tokens=%d",
                 message.stop_reason, message.usage.output_tokens)
    return text
