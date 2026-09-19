"""Claude Code adapter (NATIVE hook).

Docs: https://code.claude.com/docs/en/hooks.md
Events: PreToolUse (tool_name/tool_input/tool_use_id),
        PermissionRequest (tool_name/tool_input/permission_suggestions).
Output PreToolUse: hookSpecificOutput.permissionDecision allow|deny|ask
        (+permissionDecisionReason). Exit 2 also blocks.
Output PermissionRequest: hookSpecificOutput.decision.behavior allow|deny.
"""

from __future__ import annotations

AGENT = "claude-code"


def _tool_text(tool_name: str, tool_input: dict) -> tuple[str, str]:
    """Return (command, target) normalized from Claude tool inputs."""
    if not isinstance(tool_input, dict) or not tool_input:
        return "", ""
    if tool_name in ("Bash", "PowerShell"):
        return str(tool_input.get("command", "")), ""
    if tool_name in ("Write", "Edit", "Read"):
        return "", str(tool_input.get("file_path", ""))
    # MCP + generic: keep full JSON as the command surface for Jev.
    import json

    try:
        return json.dumps(tool_input, sort_keys=True)[:4000], ""
    except (TypeError, ValueError):
        return str(tool_input)[:4000], ""


def extract(hook_input: dict) -> dict:
    tool_name = str(hook_input.get("tool_name", ""))
    tool_input = hook_input.get("tool_input", {})
    command, target = _tool_text(tool_name, tool_input)
    return {
        "agent": AGENT,
        "tool": tool_name or "unknown",
        "command": command,
        "target": target,
        "cwd": str(hook_input.get("cwd", "")),
        "user_request": "",
    }


def translate(hook_input: dict, envelope: dict) -> dict:
    """Map ALLOW/ASK/BLOCK envelope to Claude's hookSpecificOutput."""
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
        return {"hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": {"behavior": "deny",
                         "message": "Model Guard: approval required: "
                         + reason}}}
    mapping = {"ALLOW": "allow", "REQUIRE_APPROVAL": "ask", "BLOCK": "deny"}
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": mapping.get(verdict, "ask"),
        "permissionDecisionReason": reason or "Model Guard verdict: " + verdict,
    }}
