"""Part 3: main() — evaluate, audit, emit envelope, map exit code."""

from __future__ import annotations

import json
import sys

from model_guard.audit import append_audit
from model_guard.cli_args import build_action, build_parser
from model_guard.compose import evaluate_action
from model_guard.core import ALLOW, BLOCK
from model_guard.policy import PolicyConfig
from model_guard.rules import load_user_rules
from model_guard.rules_cli import cmd_init, cmd_rules


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "init":
        return cmd_init(args)
    if args.cmd == "rules":
        return cmd_rules(args)
    if args.cmd == "check":
        cfg = PolicyConfig(fail_closed_block=args.fail_closed_block)
        action = build_action(args)
        # Attach user rules: Jev reads them as policy context; the
        # deterministic layer honors `sensitive` paths directly.
        rules = load_user_rules(explicit=args.rules,
                                cwd=action.get("cwd") or None)
        action["user_rules"] = {
            "allow": rules.get("allow", []),
            "ask": rules.get("ask", []),
            "block": rules.get("block", []),
            "source": str(rules.get("source")),
        }
        if rules.get("sensitive"):
            action["sensitive_paths"] = list(rules["sensitive"])
        decision = evaluate_action(
            action, cfg, skip_deterministic=args.no_deterministic
        )
        if not args.no_audit:
            try:
                append_audit(action, decision, path=args.audit_path)
            except Exception:
                pass  # audit must never break the gate
        if args.quiet:
            print(decision.verdict)
        else:
            print(json.dumps({
                "verdict": decision.verdict,
                "reason": decision.reason,
                "risk": round(decision.risk, 4),
                "hazards": decision.hazards,
                "severity": decision.severity,
                "confidence": decision.confidence,
                "fail_closed": decision.fail_closed,
                "model": decision.model,
                "latency_ms": round(decision.latency_ms, 1),
                "rules_source": str(rules.get("source")),
            }))
        if getattr(args, "explain", False):
            print("rules from: %s" % rules.get("source"))
            for key in ("allow", "ask", "block"):
                for item in rules.get(key, [])[:6]:
                    print("  [%s] %s" % (key.upper(), item))
        if decision.verdict == BLOCK:
            print("model-guard: BLOCKED: %s" % decision.reason,
                  file=sys.stderr)
            return 2
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
