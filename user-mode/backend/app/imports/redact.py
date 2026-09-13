"""Dropping recognized secrets before a transcript is stored.

A pasted assistant thread routinely contains the key the user was debugging with.
ADR-018 says those are dropped rather than stored, so redaction happens on the way
in — before the row is written and before any provider sees the text — and the
count of what was removed is kept so the user can be told it happened.

This is a net, not a guarantee. It recognizes the shapes that show up in real
transcripts; it cannot know that `hunter2` was a password. The size cap and the
30-day retention are what limit the rest.
"""

import re

# 32 KiB, from ADR-018. Counted in characters here, which is what the column
# holds; the route checks the encoded size too.
MAX_TRANSCRIPT = 32 * 1024

PLACEHOLDER = "[removed]"

PATTERNS: tuple[re.Pattern[str], ...] = (
    # Provider keys, in the shapes their own docs publish.
    re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{8,}", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}", re.IGNORECASE),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{12,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}"),
    # Bearer tokens and anything labelled as a credential.
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{12,}", re.IGNORECASE),
    re.compile(
        r"\b(api[_\- ]?key|secret|token|password|passwd|pwd)\b\s*[:=]\s*\S+",
        re.IGNORECASE,
    ),
    # Whole private key blocks, including the body between the markers.
    re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
        re.IGNORECASE | re.DOTALL,
    ),
    # Connection strings carrying inline credentials.
    re.compile(r"\b[a-z][a-z0-9+.\-]*://[^\s/@:]+:[^\s/@]+@\S+", re.IGNORECASE),
)


def redact(text: str) -> tuple[str, int]:
    """The text with recognized secrets replaced, and how many were removed.

    Labelled pairs keep their label (`api_key: [removed]`) so the transcript still
    reads as what it was, without the value.
    """
    removed = 0
    for pattern in PATTERNS:
        def swap(match: re.Match[str]) -> str:
            nonlocal removed
            removed += 1
            label = match.group(1) if match.re.groups and match.group(1) else ""
            return f"{label}: {PLACEHOLDER}" if label else PLACEHOLDER

        text = pattern.sub(swap, text)
    return text, removed
