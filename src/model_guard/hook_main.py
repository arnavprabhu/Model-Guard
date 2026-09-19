"""Part 2: main() for the hook entrypoint."""

from __future__ import annotations

import argparse
import json
import sys

from model_guard import __version__
from model_guard.adapters import antigravity, claude, codex, cursor
from model_guard.audit import append_audit
from model_guard.compose import evaluate_action
from model_guard.core import BLOCK
from model_guard.policy import PolicyConfig

ADAPTERS = {"claude": claude, "codex": codex, "cursor": cursor,
            "antigravity": antigravity}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="model-guard-hook")
    p.add_argument("--adapter", required=True, choices=sorted(ADAPTERS))
    p.add_argument("--version", action="version",
                   version="%(prog)s " + __version__)
    p.add_argument("--audit-path", default=None)
    p.add_argument("--fail-closed-block", action="store_true")
    p.add_argument("--timeout", type=float, default=25.0,
                   help="Advisory only; hook timeout is set agent-side.")
    args = p.parse_args(argv)

    try:
        raw = sys.stdin.read()
        hook_input = json.loads(raw) if raw.strip() else {}
        if not isinstance(hook_input, dict):
            hook_input = {}
    except json.JSONDecodeError:
        hook_input = {}
    except Exception:
        hook_input = {}

    adapter = ADAPTERS[args.adapter]
    action = adapter.extract(hook_input)
    cfg = PolicyConfig(fail_closed_block=args.fail_closed_block)
    try:
        decision = evaluate_action(action, cfg)
    except Exception as e:  # last-resort guard: never crash the hook
        decision = evaluate_action(
            action, cfg,
            jev_fn=lambda a: (_ for _ in ()).throw(Exception(str(e))),
        )
    try:
        kwargs = {} if args.audit_path is None else {"path": args.audit_path}
        append_audit(action, decision, extra={"adapter": args.adapter},
                     **kwargs)
    except Exception:
        pass

    envelope = {"verdict": decision.verdict, "reason": decision.reason}
    try:
        out = adapter.translate(hook_input, envelope)
    except Exception:
        out = {}
    sys.stdout.write(json.dumps(out))
    sys.stdout.flush()
    if decision.verdict == BLOCK:
        sys.stderr.write("model-guard BLOCKED (%s): %s\n"
                         % (action.get("tool"), decision.reason))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
