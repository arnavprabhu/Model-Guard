"""Adapter + CLI envelope tests (mocked Jev; no network)."""

import json
import subprocess
import sys

from model_guard.adapters import claude as claude_ad
from model_guard.adapters import codex as codex_ad
from model_guard.adapters import cursor as cursor_ad


def test_claude_pretooluse_bash_blocked():
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "rm -rf /"},
        "cwd": "/tmp",
    }
    out = claude_ad.translate(payload, {"verdict": "BLOCK", "reason": "x"})
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_claude_pretooluse_allow():
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "ls"},
        "cwd": "/tmp",
    }
    out = claude_ad.translate(payload, {"verdict": "ALLOW", "reason": "ok"})
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"


def test_claude_ask():
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "sudo apt update"},
        "cwd": "/tmp",
    }
    out = claude_ad.translate(
        payload, {"verdict": "REQUIRE_APPROVAL", "reason": "sudo"})
    assert out["hookSpecificOutput"]["permissionDecision"] == "ask"


def test_codex_permission_request_shapes():
    payload = {
        "hook_event_name": "PermissionRequest",
        "tool_name": "exec",
        "tool_input": {"command": "rm -rf /"},
    }
    out = codex_ad.translate(payload, {"verdict": "BLOCK", "reason": "x"})
    assert out["hookSpecificOutput"]["decision"]["behavior"] == "deny"
    out2 = codex_ad.translate(payload, {"verdict": "ALLOW", "reason": "ok"})
    assert out2["hookSpecificOutput"]["decision"]["behavior"] == "allow"
    out3 = codex_ad.translate(
        payload, {"verdict": "REQUIRE_APPROVAL", "reason": "y"})
    # ASK declines to decide so the normal approval prompt continues.
    assert out3 == {}


def test_codex_pretooluse_shapes():
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "rm -rf /"},
    }
    out = codex_ad.translate(payload, {"verdict": "BLOCK", "reason": "x"})
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    out2 = codex_ad.translate(
        payload, {"verdict": "REQUIRE_APPROVAL", "reason": "y"})
    assert "additionalContext" in out2["hookSpecificOutput"]


def test_cursor_before_shell_shapes():
    payload = {"command": "rm -rf /tmp/x", "cwd": "/tmp"}
    out = cursor_ad.translate(payload, {"verdict": "BLOCK", "reason": "x"})
    assert out["permission"] == "deny"
    out2 = cursor_ad.translate(
        payload, {"verdict": "REQUIRE_APPROVAL", "reason": "y"})
    assert out2["permission"] == "ask"


def test_extractors_do_not_crash_on_empty():
    assert claude_ad.extract({})["command"] == ""
    assert codex_ad.extract({})["command"] == ""
    assert cursor_ad.extract({})["command"] == ""


def test_cli_check_allow_fast_path(tmp_path):
    audit = str(tmp_path / "audit.jsonl")
    r = subprocess.run(
        [sys.executable, "-m", "model_guard.cli", "check",
         "--tool", "Bash", "--command", "ls -la",
         "--audit-path", audit, "--no-deterministic" ],
        capture_output=True, text=True, cwd="/tmp",
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": "src"},
    )
    # --no-deterministic forces Jev path -> missing key -> fail-closed ASK,
    # exit 0 with REQUIRE_APPROVAL envelope (proves fail-closed works).
    assert r.returncode == 0, r.stderr
    body = json.loads(r.stdout)
    assert body["verdict"] == "REQUIRE_APPROVAL"
    assert body["fail_closed"] is True
