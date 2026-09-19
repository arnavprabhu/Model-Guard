"""Part 2: argument parsing, action building, verdict envelope, main()."""

from __future__ import annotations

import argparse
import json
import os
import sys

from model_guard import __version__
from model_guard.audit import DEFAULT_PATH, append_audit
from model_guard.compose import evaluate_action
from model_guard.core import ALLOW, BLOCK, REQUIRE_APPROVAL
from model_guard.policy import PolicyConfig


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="model-guard",
        description="Runtime safety gate for AI coding-agent actions.",
    )
    p.add_argument("--version", action="version", version="%(prog)s " + __version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="Evaluate one action, print verdict JSON.")
    c.add_argument("--agent", default="unknown")
    c.add_argument("--tool", default="Bash")
    c.add_argument("--command", default="")
    c.add_argument("--target", default="")
    c.add_argument("--cwd", default="")
    c.add_argument("--user-request", default="")
    c.add_argument("--stdin-json", action="store_true",
                   help="Read action JSON object from stdin.")
    c.add_argument("--audit-path", default=DEFAULT_PATH)
    c.add_argument("--no-audit", action="store_true")
    c.add_argument("--fail-closed-block", action="store_true",
                   help="Jev failure -> BLOCK instead of REQUIRE_APPROVAL.")
    c.add_argument("--no-deterministic", action="store_true",
                   help="Force the Jev path (benchmark / ablation).")
    c.add_argument("--quiet", action="store_true",
                   help="Only print verdict word to stdout.")
    c.add_argument("--rules", default=None,
                   help="Path to RULES.md (overrides auto-discovery).")
    c.add_argument("--explain", action="store_true",
                   help="Print which rule section drove the verdict.")

    i = sub.add_parser("init", help="Create ~/.model-guard/RULES.md.")
    i.add_argument("--dest", default=None)
    i.add_argument("--force", action="store_true")

    r = sub.add_parser("rules", help="Show effective rules for this dir.")
    r.add_argument("--rules", default=None)
    r.add_argument("--cwd", default=None)
    r.add_argument("--json", action="store_true")
    return p


def build_action(args: argparse.Namespace) -> dict:
    if args.stdin_json:
        raw = sys.stdin.read()
        try:
            obj = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            obj = {"command": raw.strip()}
        if isinstance(obj, dict):
            action = {
                "agent": obj.get("agent", args.agent),
                "tool": obj.get("tool", args.tool),
                "command": obj.get("command", args.command),
                "target": obj.get("target", args.target),
                "cwd": obj.get("cwd", args.cwd),
                "user_request": obj.get("user_request", args.user_request),
            }
            for k in ("recent_actions", "sensitive_paths", "org_rules"):
                if k in obj:
                    action[k] = obj[k]
            return action
    return {
        "agent": args.agent,
        "tool": args.tool,
        "command": args.command,
        "target": args.target,
        "cwd": args.cwd,
        "user_request": args.user_request,
    }
