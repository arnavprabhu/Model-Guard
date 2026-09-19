"""Append-only JSONL audit trail.

Every decision — ALLOW, REQUIRE_APPROVAL, BLOCK, fail-closed — is appended
as one JSON object per line. The API key is never written; command text is
truncated to bound log size (full text stays in the agent transcript).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone

DEFAULT_PATH = os.path.expanduser("~/.model-guard/audit.jsonl")
MAX_CMD_CHARS = 2000


def _redact(text: str) -> str:
    """Mask likely secret values so the audit log stays shareable."""
    import re

    text = re.sub(
        r"(?i)(api[_-]?key|token|secret|password|passwd)\s*[:=]\s*"
        r"([\"']?)([^\\s\"',;}]+)\\2",
        r"\1=[REDACTED]",
        text,
    )
    return text


def append_audit(
    action: dict,
    decision,
    path: str = DEFAULT_PATH,
    extra: dict | None = None,
) -> dict:
    """Append one record; return the record. Never raises (audit is best-effort
    but must not break the hook path — callers wrap defensively anyway)."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except OSError:
        path = os.path.join("/tmp", "model-guard-audit.jsonl")
        os.makedirs(os.path.dirname(path), exist_ok=True)
    cmd = _redact(str(action.get("command", "") or action.get("target", "")))
    if len(cmd) > MAX_CMD_CHARS:
        cmd = cmd[:MAX_CMD_CHARS] + "…[truncated]"
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "epoch": time.time(),
        "agent": action.get("agent", "unknown"),
        "tool": action.get("tool", "unknown"),
        "command": cmd,
        "command_sha256": hashlib.sha256(
            str(action.get("command", "")).encode()
        ).hexdigest()[:16],
        "cwd": action.get("cwd", ""),
        "verdict": decision.verdict,
        "reason": decision.reason,
        "risk": round(decision.risk, 4),
        "hazards": {k: round(v, 4) for k, v in decision.hazards.items()},
        "severity": round(decision.severity, 3),
        "confidence": round(decision.confidence, 3),
        "jev_verdict": decision.jev_verdict,
        "deterministic_hit": decision.deterministic_hit,
        "fail_closed": decision.fail_closed,
        "model": decision.model,
        "latency_ms": round(decision.latency_ms, 1),
    }
    if extra:
        record["extra"] = extra
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except OSError:
        pass
    return record
