"""Codex CLI/Desktop adapter (NATIVE hook).

Docs: https://developers.openai.com/codex/hooks.md
Config: ~/.codex/hooks.json | ~/.codex/config.toml | <repo>/.codex/*
Events: PreToolUse {tool_name, tool_input.command, tool_use_id},
        PermissionRequest {tool_name, tool_input}.
Output PreToolUse: hookSpecificOutput.permissionDecision deny (+Reason),
        or legacy {decision: block, reason}, or exit 2 + stderr.
        NOTE: "ask" and legacy "approve" are parsed-but-unsupported for
        PreToolUse (hook run fails, tool continues) -> Model Guard ASK on
        PreToolUse emits additionalContext (advisory) and relies on the
        PermissionRequest hook for the real ask->deny gate.
Output PermissionRequest: hookSpecificOutput.decision.behavior allow|deny;
        any deny wins; no-decision falls through to normal approval UI.
"""

from __future__ import annotations

import json

AGENT = "codex"


def _text(tool_name: str, tool_input) -> str:
    if isinstance(tool_input, dict):
        if not tool_input:
            return ""
        if "command" in tool_input:
            return str(tool_input.get("command", ""))
        try:
            return json.dumps(tool_input, sort_keys=True)[:4000]
        except (TypeError, ValueError):
            return str(tool_input)[:4000]
    return str(tool_input or "")


def extract(hook_input: dict) -> dict:
    tool_name = str(hook_input.get("tool_name", ""))
    return {
        "agent": AGENT,
        "tool": tool_name or "unknown",
        "command": _text(tool_name, hook_input.get("tool_input")),
        "target": "",
        "cwd": str(hook_input.get("cwd", "")),
        "user_request": "",
    }


def translate(hook_input: dict, envelope: dict) -> dict:
    verdict = envelope.get("verdict", "REQUIRE_APPROVAL")
    reason = str(envelope.get("reason", ""))[:500]
    event = str(hook_input.get("hook_event_name", "PreToolUse"))
    if event == "PermissionRequest":
        if verdict == "BLOCK":
            return {"hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": {"behavior": "deny", "message": reason}}}
        if verdict == "ALLOW":
            return {"hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": {"behavior": "allow"}}}
        # ASK: decline to decide -> normal approval prompt continues.
        return {}
    # PreToolUse
    if verdict == "BLOCK":
        return {"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason}}
    if verdict == "ALLOW":
        return {"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": reason or "Model Guard: allow"}}
    # ASK on PreToolUse: "ask" unsupported -> advisory context + let the
    # PermissionRequest hook / normal approval flow decide.
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": "Model Guard: approval recommended: " + reason}}
