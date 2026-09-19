"""User rules CLI: `model-guard init` + explain."""

from __future__ import annotations

import json
import os
import shutil

from model_guard.rules import HOME_RULES, load_user_rules

_TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "..", "..", "RULES.md")


def cmd_init(args) -> int:
    """Write ~/.model-guard/RULES.md from the template (never overwrite)."""
    dest = args.dest or HOME_RULES
    if os.path.exists(dest) and not args.force:
        print("rules already exist: %s (use --force to overwrite)" % dest)
        print("effective source: %s"
              % load_user_rules(cwd=os.getcwd()).get("source"))
        return 0
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    src = _TEMPLATE if os.path.isfile(_TEMPLATE) else None
    if src:
        shutil.copy(src, dest)
    else:
        with open(dest, "w", encoding="utf-8") as f:
            f.write("# Model Guard rules\n\n## Always allow\n- read files\n")
    print("wrote %s — edit it in plain English, then re-run." % dest)
    return 0


def cmd_rules(args) -> int:
    """Show the effective rules for this directory (file resolution demo)."""
    rules = load_user_rules(explicit=args.rules,
                            cwd=args.cwd or os.getcwd())
    if getattr(args, "json", False):
        print(json.dumps(rules, indent=2)[:4000])
    else:
        print("source: %s" % rules.get("source"))
        for key in ("allow", "ask", "block", "sensitive"):
            items = rules.get(key, [])
            print("\n[%s] (%d)" % (key.upper(), len(items)))
            for item in items[:12]:
                print("  - %s" % item)
    return 0
