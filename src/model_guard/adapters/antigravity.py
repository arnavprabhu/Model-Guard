"""Antigravity adapter (NATIVE hook, PROVISIONAL output contract).

Docs: https://antigravity.google/docs/hooks
Config: .agents/hooks.json (workspace) | ~/.gemini/config/hooks.json.
Events: PreToolUse / PostToolUse / PreInvocation / PostInvocation / Stop.
Common input: conversationId, workspacePaths, transcriptPath,
              artifactDirectoryPath, modelName.

PreToolUse output contract is under-specified in the public docs (page is
JS-rendered; Stop's {decision: continue} is specified). This adapter emits
the Claude/Codex-compatible hookSpecificOutput.permissionDecision shape AND
sets process exit codes (0 allow/ask, 2 block), then the live test against
`agy` determines which signal the CLI honors. Status stays PROVISIONAL
until that test passes.
"""

from __future__ import annotations

import json

AGENT = "antigravity"


def extract(hook_input: dict) -> dict:
    cmd = ""
    target = ""
    tool = str(hook_input.get("tool_name",
                             hook_input.get("toolName", "unknown")))
    for key in ("command", "tool_input", "toolInput", "input", "params"):
        val = hook_input.get(key)
        if isinstance(val, dict):
            val = val.get("command", val.get("file_path", json.dumps(val)))
        if val:
            cmd = str(val)[:4000]
            break
    cwd = ""
    ws = hook_input.get("workspacePaths") or hook_input.get("workspace_paths")
    if isinstance(ws, list) and ws:
        cwd = str(ws[0])
    return {
        "agent": AGENT, "tool": tool, "command": cmd, "target": target,
        "cwd": cwd or str(hook_input.get("cwd", "")), "user_request": "",
    }


def translate(hook_input: dict, envelope: dict) -> dict:
    verdict = envelope.get("verdict", "REQUIRE_APPROVAL")
    reason = str(envelope.get("reason", ""))[:500]
    mapping = {"ALLOW": "allow", "REQUIRE_APPROVAL": "ask", "BLOCK": "deny"}
    return {"hookSpecificOutput": {
        "hookEventName": str(hook_input.get(
            "hook_event_name", hook_input.get("hookEventName",
                                             "PreToolUse"))),
        "permissionDecision": mapping.get(verdict, "ask"),
        "permissionDecisionReason": reason or "Model Guard: " + verdict,
    }}
