#!/usr/bin/env python3
"""Register/unregister Model Guard hooks (merge, never clobber).

Usage:
  python3 scripts/register.py --agent claude --hook-bin model-guard-hook
  python3 scripts/register.py --agent codex --uninstall
  python3 scripts/register.py --agent all --global --hook-bin model-guard-hook

Agents: claude | codex | cursor | antigravity | all
Scope: project (default, writes into ./.claude|./.codex|./.cursor|./.agents)
       | global (--global, writes into ~ home configs).
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from register_lib import (  # noqa: E402
    CLAUDE_MATCHER,
    TAG,
    _ensure_hook_list,
    _hook_entry,
    _load,
    _remove_tagged,
    _save,
)

HOME = os.path.expanduser("~")


def _normalize_scope(scope: str) -> str:
    """Map legacy 'user' to 'global' (back-compat shim)."""
    if scope == "user":
        print("warning: --scope user is deprecated, use --scope global "
              "or --global", file=sys.stderr)
        return "global"
    return scope


def _paths(agent: str, scope: str) -> list[str]:
    scope = _normalize_scope(scope)
    if scope == "project":
        cwd = os.getcwd()
        return {
            "claude": [os.path.join(cwd, ".claude", "settings.json")],
            "codex": [os.path.join(cwd, ".codex", "hooks.json")],
            "cursor": [os.path.join(cwd, ".cursor", "hooks.json")],
            "antigravity": [os.path.join(cwd, ".agents", "hooks.json")],
        }[agent]
    return {
        "claude": [os.path.join(HOME, ".claude", "settings.json")],
        "codex": [os.path.join(HOME, ".codex", "hooks.json")],
        "cursor": [os.path.join(HOME, ".cursor", "hooks.json")],
        "antigravity": [os.path.join(HOME, ".gemini", "config",
                                     "hooks.json")],
    }[agent]


def _install(agent: str, path: str, hook_bin: str,
             fail_closed: str) -> str:
    settings = _load(path)
    # hook_bin may already contain adapter args; only append if missing.
    if "--adapter" in hook_bin:
        cmd = hook_bin + fail_closed
    else:
        cmd = "%s --adapter %s%s" % (hook_bin, agent, fail_closed)
    if agent == "claude":
        changed = _ensure_hook_list(
            settings, "PreToolUse",
            _hook_entry(cmd, CLAUDE_MATCHER), TAG)
    elif agent == "codex":
        c1 = _ensure_hook_list(settings, "PreToolUse",
                               _hook_entry(cmd, ".*"), TAG)
        c2 = _ensure_hook_list(settings, "PermissionRequest",
                               _hook_entry(cmd, ".*"), TAG)
        changed = c1 or c2
    elif agent == "cursor":
        # Cursor hooks.json: {version, hooks: {event: [{command, failClosed}]}}
        hooks = settings.setdefault("hooks", {})
        changed = False
        for event in ("beforeShellExecution", "beforeMCPExecution",
                      "preToolUse"):
            lst = hooks.setdefault(event, [])
            if not any(TAG in str(e.get("command", "")) for e in lst):
                lst.append({"command": [hook_bin, "--adapter", "cursor"]
                            + ([fail_closed.strip()] if fail_closed else []),
                            "failClosed": True})
                changed = True
        settings["version"] = settings.get("version", 1)
    elif agent == "antigravity":
        changed = _ensure_hook_list(settings, "PreToolUse",
                                    _hook_entry(cmd, ".*"), TAG)
    else:
        raise ValueError(agent)
    if changed:
        _save(path, settings)
        return "installed -> %s" % path
    return "already present: %s" % path


def _uninstall(agent: str, path: str) -> str:
    settings = _load(path)
    hooks = settings.get("hooks", {})
    if not isinstance(hooks, dict):
        return "not present: %s" % path
    # Normalize cursor list-form commands so tag matching sees them.
    for event, lst in hooks.items():
        if isinstance(lst, list):
            for e in lst:
                if isinstance(e, dict) and isinstance(
                        e.get("command"), list):
                    e["_cmd_str"] = " ".join(str(x) for x in e["command"])
    if _remove_tagged(settings, TAG):
        for event, lst in hooks.items():
            if isinstance(lst, list):
                for e in lst:
                    if isinstance(e, dict):
                        e.pop("_cmd_str", None)
        # drop emptied events for a clean file
        for event in [k for k, v in hooks.items() if v == []]:
            del hooks[event]
        _save(path, settings)
        return "removed from %s" % path
    return "not present: %s" % path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="mg-register")
    ap.add_argument("--agent", default="all",
                    choices=["claude", "codex", "cursor",
                             "antigravity", "all"])
    ap.add_argument("--scope", default="project",
                    choices=["project", "global", "user"],
                    help="project (default): ./.{claude,codex,cursor,agents} "
                    "in cwd; global: ~/ home configs "
                    "('user' kept as deprecated alias for global).")
    ap.add_argument("--global", dest="global_scope", action="store_true",
                    help="Shortcut for --scope global (whole machine).")
    ap.add_argument("--hook-bin", default="model-guard-hook")
    ap.add_argument("--fail-closed-block", action="store_true")
    ap.add_argument("--uninstall", action="store_true")
    args = ap.parse_args(argv)
    raw = list(argv) if argv is not None else sys.argv[1:]
    scope_explicit = "--scope" in raw
    if args.global_scope and scope_explicit and args.scope == "project":
        ap.error("--global cannot be combined with --scope project "
                 "(pick one).")
    if args.global_scope and not scope_explicit:
        # --global given without explicit --scope: opt into global.
        args.scope = "global"
    args.scope = _normalize_scope(args.scope)
    agents = (["claude", "codex", "cursor", "antigravity"]
              if args.agent == "all" else [args.agent])
    fc = " --fail-closed-block" if args.fail_closed_block else ""
    for agent in agents:
        for path in _paths(agent, args.scope):
            if args.uninstall:
                print(_uninstall(agent, path))
            else:
                print(_install(agent, path, args.hook_bin, fc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
