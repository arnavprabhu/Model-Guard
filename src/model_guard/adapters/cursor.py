"""Cursor adapter (NATIVE hook).

Docs: https://cursor.com/docs/hooks.md
Config: .cursor/hooks.json (project; also runs on cloud agents).
Events: beforeShellExecution {command, cwd},
        beforeMCPExecution {tool_name, tool_input, mcp_server_name},
        preToolUse (generic). This adapter handles all three.
Output: {permission: allow|deny|ask, user_message, agent_message}.
        Invalid JSON blocks; crashes/timeouts/non-2 exits fail OPEN unless
        failClosed:true -> installer sets failClosed:true on gating hooks.
"""

from __future__ import annotations

import json

AGENT = "cursor"


def extract(hook_input: dict) -> dict:
    if "command" in hook_input and "tool_name" not in hook_input:
        return {
            "agent": AGENT,
            "tool": "Bash",
            "command": str(hook_input.get("command", "")),
            "target": "",
            "cwd": str(hook_input.get("cwd", "")),
            "user_request": "",
        }
    tool_input = hook_input.get("tool_input", "")
    if isinstance(tool_input, dict):
        try:
            cmd = json.dumps(tool_input, sort_keys=True)[:4000]
        except (TypeError, ValueError):
            cmd = str(tool_input)[:4000]
    else:
        cmd = str(tool_input or "")
    return {
        "agent": AGENT,
        "tool": str(hook_input.get("tool_name", "unknown")),
        "command": cmd,
        "target": "",
        "cwd": str(hook_input.get("cwd", "")),
        "user_request": "",
    }


def translate(hook_input: dict, envelope: dict) -> dict:
    verdict = envelope.get("verdict", "REQUIRE_APPROVAL")
    reason = str(envelope.get("reason", ""))[:500]
    mapping = {"ALLOW": "allow", "REQUIRE_APPROVAL": "ask", "BLOCK": "deny"}
    perm = mapping.get(verdict, "ask")
    if perm == "allow":
        return {"permission": "allow"}
    return {
        "permission": perm,
        "user_message": "Model Guard %s: %s" % (verdict, reason),
        "agent_message": "Model Guard verdict %s: %s" % (verdict, reason),
    }
