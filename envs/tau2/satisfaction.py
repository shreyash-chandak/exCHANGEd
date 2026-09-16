"""Shared end-of-episode user-satisfaction question (guide 4a.6/4b's
`user_satisfied` field), used by both refunds and retail canonicalization.

Asks the model playing the customer to roleplay from a flattened transcript
rather than reconstructing tau2's own `UserState.flip_roles()` message
framing -- simpler, and avoids the risk of getting that internal role
convention subtly wrong for a one-off question asked after the episode is
already over. LIVE only (calls `change.llm.chat`).
"""

from __future__ import annotations

import re

from change.llm import chat

_SATISFACTION_QUESTION = (
    "On a scale of 1 to 5 (1 = very dissatisfied, 5 = very satisfied), how satisfied "
    "are you with how the agent just handled your request? Reply with only the number."
)


def ask_user_satisfied(transcript: str) -> bool:
    messages = [
        {
            "role": "system",
            "content": (
                "You are the customer from the transcript below, replying to a "
                "satisfaction survey about the support interaction you just had."
            ),
        },
        {"role": "user", "content": f"Transcript:\n{transcript}\n\n{_SATISFACTION_QUESTION}"},
    ]
    response = chat(messages, temperature=0.0, max_tokens=10)
    content = response["choices"][0]["message"]["content"].strip()
    match = re.search(r"[1-5]", content)
    if not match:
        raise ValueError(f"user satisfaction response not parseable as 1-5: {content!r}")
    return int(match.group(0)) >= 4
