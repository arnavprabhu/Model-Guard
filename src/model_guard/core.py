"""Part 2: deterministic screens + Jev-gated composition + Decision model."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

from model_guard import policy as _p
from model_guard.jev_client import JevError, JevResult

ALLOW = "ALLOW"
REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
BLOCK = "BLOCK"


@dataclass
class Decision:
    verdict: str
    reason: str
    risk: float = 0.0
    hazards: dict[str, float] = field(default_factory=dict)
    severity: float = 0.0
    confidence: float = 0.0
    jev_verdict: str = ""
    deterministic_hit: str = ""
    model: str = ""
    latency_ms: float = 0.0
    fail_closed: bool = False


def _action_text(action: dict) -> str:
    parts = [
        str(action.get("command", "")),
        str(action.get("target", "")),
        str(action.get("tool", "")),
    ]
    return "\n".join(p for p in parts if p)


def _sensitive_hit(action: dict) -> str | None:
    """User RULES.md sensitive paths: approval minimum, even if no regex hit.

    Matches case-insensitively against command text, target, and cwd so a
    user-written `- ~/client-secrets` protects every spelling of access.
    """
    hay = "\n".join([
        str(action.get("command", "")),
        str(action.get("target", "")),
        str(action.get("cwd", "")),
    ]).lower()
    for raw in action.get("sensitive_paths", []) or []:
        needle = str(raw).strip().lower().rstrip("/")
        if not needle:
            continue
        # match expanded and literal forms (~, $HOME, absolute)
        expanded = os.path.expanduser(str(raw).strip()).lower()
        if needle in hay or expanded in hay:
            return str(raw).strip()
    return None


def deterministic_pre_screen(
    action: dict, cfg: _p.PolicyConfig | None = None
) -> Decision | None:
    """Return a Decision if deterministic rules fire, else None (defer to Jev).

    Order: BLOCK patterns -> APPROVAL patterns -> ALLOW fast path.
    Returns None when nothing fires so the caller proceeds to Jev.
    """
    cfg = cfg or _p.PolicyConfig()
    text = _action_text(action)
    tool = str(action.get("tool", ""))

    hit = _p._match(_p.BLOCK_PATTERNS, text)
    if hit:
        return Decision(
            verdict=BLOCK,
            reason="deterministic block: %s" % hit,
            risk=1.0,
            deterministic_hit="block:%s" % hit,
        )
    hit = _p._match(_p.APPROVAL_PATTERNS, text)
    if hit:
        return Decision(
            verdict=REQUIRE_APPROVAL,
            reason="deterministic approval: %s" % hit,
            risk=0.5,
            deterministic_hit="approval:%s" % hit,
        )
    # User RULES.md sensitive paths: approval minimum (checked before the
    # ALLOW fast path so a user's "ask me about X" can never be skipped).
    sens = _sensitive_hit(action)
    if sens:
        return Decision(
            verdict=REQUIRE_APPROVAL,
            reason="rules: sensitive path %s needs approval" % sens,
            risk=0.5,
            deterministic_hit="rules:sensitive",
        )
    # ALLOW fast path only for known-readonly tools or safe command shapes.
    if tool in _p.READONLY_TOOLS:
        return Decision(
            verdict=ALLOW,
            reason="deterministic allow: readonly tool %s" % tool,
            risk=0.0,
            deterministic_hit="allow:tool",
        )
    hit = _p._match(_p.ALLOW_PATTERNS, text)
    if hit:
        return Decision(
            verdict=ALLOW,
            reason="deterministic allow: %s" % hit,
            risk=0.05,
            deterministic_hit="allow:%s" % hit,
        )
    return None
