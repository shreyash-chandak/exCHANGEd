"""Single LLM chat entrypoint (session-2 guide 4.1.3). Every live code path
calls `chat()`; nothing else in this repo calls litellm directly.
"""

from __future__ import annotations

from typing import Any

import litellm

from change.config import LLM_BASE_URL, LLM_MODEL


class ThinkingLeakError(RuntimeError):
    """Raised when a response contains a <think> block despite thinking
    being disabled -- guide 4.1.3 requires this be treated as an error, not
    silently stripped, since it means the disable mechanism didn't take."""


def chat(
    messages: list[dict],
    tools: list[dict] | None = None,
    temperature: float = 0.0,
    seed: int | None = None,
    max_tokens: int = 512,
) -> dict:
    """Calls the configured local model (CHANGE_LLM_MODEL / CHANGE_LLM_BASE_URL)
    through litellm with thinking disabled via chat_template_kwargs'
    enable_thinking=False (the mechanism llama-server's --jinja templating
    and Ollama's OpenAI-compatible endpoint both honor for Qwen3.5's chat
    template). Returns litellm's response as a plain dict. Raises
    ThinkingLeakError if a <think> block appears in the output anyway."""
    if LLM_MODEL is None:
        raise RuntimeError(
            "CHANGE_LLM_MODEL is not set -- copy .env.example to .env and fill it in"
        )

    kwargs: dict[str, Any] = dict(
        model=LLM_MODEL,
        messages=messages,
        api_base=LLM_BASE_URL,
        temperature=temperature,
        max_tokens=max_tokens,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    if tools is not None:
        kwargs["tools"] = tools
    if seed is not None:
        kwargs["seed"] = seed

    response = litellm.completion(**kwargs)
    result = response.model_dump()

    for choice in result.get("choices", []):
        content = (choice.get("message") or {}).get("content") or ""
        if "<think>" in content:
            raise ThinkingLeakError(
                f"response contains a <think> block despite enable_thinking=False: {content!r}"
            )

    return result
