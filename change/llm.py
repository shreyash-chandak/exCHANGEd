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
        # Local servers (llama-server, Ollama) don't check this, but
        # litellm's openai/ provider path requires a non-empty key to be
        # present at all. Ignored by the ollama_chat/ provider.
        api_key="local-no-auth-required",
        temperature=temperature,
        max_tokens=max_tokens,
        # Two different mechanisms for the same thing, passed together and
        # each harmless to the other's provider: chat_template_kwargs'
        # enable_thinking is what llama-server's --jinja templating (and
        # vLLM) honor; a bare `think` kwarg is what litellm's ollama_chat/
        # provider maps onto Ollama's native /api/chat `think` field.
        # Measured directly (docs/serving.md): chat_template_kwargs alone
        # did NOT disable thinking through Ollama's OpenAI-compatible
        # endpoint (content came back empty, reasoning in a separate
        # `reasoning_content` field) -- only `think=False` via
        # ollama_chat/ actually worked for Ollama.
        think=False,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    if tools is not None:
        kwargs["tools"] = tools
    if seed is not None:
        kwargs["seed"] = seed

    response = litellm.completion(**kwargs)
    result = response.model_dump()

    for choice in result.get("choices", []):
        message = choice.get("message") or {}
        content = message.get("content") or ""
        reasoning = message.get("reasoning_content") or message.get("reasoning") or ""
        if "<think>" in content or reasoning:
            raise ThinkingLeakError(
                "response contains reasoning/a <think> block despite thinking "
                f"disabled: content={content!r} reasoning={reasoning!r}"
            )

    return result
