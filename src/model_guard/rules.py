"""User rules file: plain-English `RULES.md` + env config. Zero learning curve.

Resolution order for the rules file:
  1. --rules /path/to/RULES.md (explicit flag wins)
  2. $MODEL_GUARD_RULES (path to a RULES.md file)
  3. ./RULES.md, walking up parent dirs to filesystem root (project rules)
  4. ~/.model-guard/RULES.md (personal rules live here; `init` writes it)
  5. built-in defaults (no file found)

Env vars understood (all optional):
  TYPESAFE_API_KEY       live Jev judgments (required for semantic path)
  TYPESAFE_MODEL         model alias (default: jev-latest)
  MODEL_GUARD_RULES      path to RULES.md
  MODEL_GUARD_AUDIT_PATH audit JSONL path (default ~/.model-guard/audit.jsonl)
"""

from __future__ import annotations

import os
import re

RULES_FILENAME = "RULES.md"
HOME_RULES = os.path.join(os.path.expanduser("~"), ".model-guard", RULES_FILENAME)

DEFAULT_ALLOW = [
    "read-only commands (ls, cat, git status, tests, builds)",
    "writing code inside the current project folder",
    "running the project's own tests, linter, and typechecker",
]

DEFAULT_ASK = [
    "installing new packages or dependencies",
    "pushing to shared branches, publishing, or deploying",
    "any command using sudo or admin rights",
    "accessing credentials, secrets, or private keys",
]

DEFAULT_BLOCK = [
    "deleting things outside the current project folder",
    "sending code, files, or secrets to unknown outside servers",
    "wiping disks, formatting drives, shutting machines down",
    "anything matching a known-malicious pattern (curl|sh, fork bombs)",
]


def find_rules_file(explicit: str | None = None,
                    cwd: str | None = None) -> str | None:
    """Locate the RULES.md to use. Returns a path or None."""
    if explicit and os.path.isfile(explicit):
        return explicit
    env_path = os.environ.get("MODEL_GUARD_RULES", "")
    if env_path and os.path.isfile(env_path):
        return env_path
    start = cwd or os.getcwd()
    cur = os.path.abspath(start)
    while True:
        cand = os.path.join(cur, RULES_FILENAME)
        if os.path.isfile(cand):
            return cand
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    if os.path.isfile(HOME_RULES):
        return HOME_RULES
    return None


def parse_rules_file(path: str) -> dict:
    """Parse ALLOW/ASK/BLOCK sections + SENSITIVE lines from a RULES.md.

    Accepts headings like `## Always allow`, `## Ask me first`,
    `## Never allow`, `## Sensitive paths` (case-insensitive), with `-`
    or `*` bullets. Unknown sections are ignored. Returns dict with
    allow/ask/block/sensitive lists plus the raw text for Jev context.
    """
    out = {"allow": [], "ask": [], "block": [], "sensitive": [],
           "path": path, "raw": ""}
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return out
    out["raw"] = text[:4000]
    section = ""
    for line in text.splitlines():
        h = line.strip().lower()
        if h.startswith("#"):
            # Order matters: "never allow" must win over bare "allow".
            if ("never" in h or "block" in h or "deny" in h
                    or "forbid" in h):
                section = "block"
            elif "allow" in h:
                section = "allow"
            elif "ask" in h or "approv" in h or "confirm" in h:
                section = "ask"
            elif "sensitiv" in h or "protect" in h:
                section = "sensitive"
            else:
                section = ""
            continue
        m = re.match(r"\s*[-*]\s+(.+)", line)
        if m and section:
            text_item = m.group(1).strip()[:300]
            # Skip markdown horizontal rules mistaken for bullets.
            if set(text_item) <= {"-", "*"}:
                continue
            out[section].append(text_item)
    return out


def load_user_rules(explicit: str | None = None,
                    cwd: str | None = None) -> dict:
    """Load effective user rules: parsed file or built-in defaults."""
    path = find_rules_file(explicit, cwd)
    if path:
        parsed = parse_rules_file(path)
        parsed["source"] = path
        return parsed
    return {
        "allow": list(DEFAULT_ALLOW),
        "ask": list(DEFAULT_ASK),
        "block": list(DEFAULT_BLOCK),
        "sensitive": [],
        "path": None,
        "raw": "",
        "source": "built-in defaults",
    }
