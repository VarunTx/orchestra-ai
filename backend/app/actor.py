"""Request actor, so an action taken by a machine client is attributable in the audit log."""
from __future__ import annotations

from contextvars import ContextVar

# Defaults to the historical label so existing call sites keep working unchanged.
CURRENT_ACTOR: ContextVar[str] = ContextVar('current_actor', default='owner')
