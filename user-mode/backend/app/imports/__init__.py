"""Importing a conversation the user already had somewhere else.

Everything in here treats the pasted text as untrusted data, in exactly the sense
SEC-09 means it: text claiming to be a system prompt, a developer, or Guider
itself carries no authority, and nothing extracted from a transcript can confirm
a plan, start a session, switch watching on or change policy
([ADR-018](../../../../docs/user-mode-guide/adr/018-imported-conversation-context.md)).
"""

from app.imports.redact import MAX_TRANSCRIPT, redact
from app.imports.text import extract_locally, vet_import

__all__ = ["MAX_TRANSCRIPT", "extract_locally", "redact", "vet_import"]
