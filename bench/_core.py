"""Part 2: case loading, static baseline, guard run, metric computation."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from model_guard.compose import evaluate_action  # noqa: E402
from model_guard.core import deterministic_pre_screen  # noqa: E402
from model_guard.policy import PolicyConfig  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
JEV_PRICE_PER_MTOK = 0.042  # TypeSafe input $/Mtok at time of writing; outputs free


def git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True,
            text=True, cwd=os.path.join(HERE, ".."),
        ).stdout.strip()
    except Exception:
        return "unknown"


def dataset_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()[:16]


def load_cases(path: str | None = None) -> list[dict]:
    path = path or os.path.join(HERE, "cases.jsonl")
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def action_of(case: dict) -> dict:
    return {
        "agent": "bench",
        "tool": case.get("tool", "Bash"),
        "command": case.get("command", ""),
        "target": case.get("target", ""),
        "cwd": "/repo",
        "user_request": case.get("user_request", ""),
    }


def allow_all_verdict(case: dict) -> tuple[str, float]:
    """Allow-everything baseline: no gate at all. Everything -> ALLOW."""
    t0 = time.perf_counter()
    return "ALLOW", (time.perf_counter() - t0) * 1000.0


def static_verdict(case: dict) -> tuple[str, float]:
    """Deterministic-rules-only baseline: Model Guard's local layer alone.

    Anything unmatched -> ALLOW. This is what a hand-maintained rule set
    does on its own: match known-bad strings, permit everything else.
    """
    t0 = time.perf_counter()
    d = deterministic_pre_screen(action_of(case), PolicyConfig())
    ms = (time.perf_counter() - t0) * 1000.0
    if d is None:
        return "ALLOW", ms  # allowlist default-allow gap
    return d.verdict, ms
