"""Part 2: per-agent register/unregister with JSON merge (no clobber)."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

CLAUDE_MATCHER = ("Bash|PowerShell|Edit|Write|Read|Glob|Grep|WebFetch|"
                  "WebSearch|MultiEdit|NotebookEdit|TodoWrite|Task|"
                  "BashOutput|KillShell|Skill|SlashCommand|mcp__.*")


def _load(path: str) -> dict:
    if os.path.exists(path):
        with open(path) as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = {}
            return data if isinstance(data, dict) else {}
    return {}


def _save(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".mg-tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def _hook_entry(hook_cmd: str, matcher: str) -> dict:
    return {"matcher": matcher,
            "hooks": [{"type": "command", "command": hook_cmd,
                       "timeout": 30}]}


def _ensure_hook_list(settings: dict, event: str, entry: dict,
                      tag: str) -> bool:
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        return False
    lst = hooks.setdefault(event, [])
    for group in lst:
        for h in group.get("hooks", []):
            if tag in str(h.get("command", "")):
                return False  # already installed
    lst.append(entry)
    return True


def _cmd_text(entry: dict) -> str:
    """Command text for tag matching (handles str + list forms)."""
    cmd = entry.get("command", "")
    if isinstance(cmd, list):
        cmd = " ".join(str(x) for x in cmd)
    extra = str(entry.get("_cmd_str", ""))
    return str(cmd) + " " + extra


def _remove_tagged(settings: dict, tag: str) -> bool:
    hooks = settings.get("hooks", {})
    if not isinstance(hooks, dict):
        return False
    changed = False
    for event in list(hooks.keys()):
        kept = []
        for group in hooks[event]:
            if not isinstance(group, dict):
                continue
            if "hooks" in group and isinstance(group["hooks"], list):
                cmds = [h for h in group["hooks"]
                        if tag not in _cmd_text(h)]
                if len(cmds) != len(group["hooks"]):
                    changed = True
                if cmds:
                    group["hooks"] = cmds
                    kept.append(group)
                # else: whole group was ours -> drop it (changed already True)
            elif "command" in group:
                # Cursor flat form: {command: [...], failClosed: true}
                if tag not in _cmd_text(group):
                    kept.append(group)
                else:
                    changed = True
            else:
                kept.append(group)
        if kept != hooks[event]:
            changed = True
        hooks[event] = kept
        if not hooks[event]:
            del hooks[event]
    return changed


TAG = "model-guard-hook"
