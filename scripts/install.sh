#!/bin/bash
# Model Guard installer: pip install + register Tier-1 hooks.
# Usage: ./scripts/install.sh [--agent claude|codex|cursor|antigravity|all]
#        [--scope project|global] [--global] [--fail-closed-block] [--uninstall]
#
# Default is project-local: writes into ./.claude, ./.codex, ./.cursor,
# ./.agents in the current directory. Pass --global (or --scope global)
# to register in your home configs instead (whole machine).
#
# Merge-only: existing settings/hooks files are preserved; only Model Guard
# entries are added/removed. Never writes secrets; never logs TYPESAFE_API_KEY.
set -euo pipefail
MG_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AGENT="all"; SCOPE="project"; SCOPE_EXPLICIT=0; GLOBAL=0; FAIL_CLOSED=""; ACTION="install"
while [ $# -gt 0 ]; do
  case "$1" in
    --agent) AGENT="$2"; shift 2;;
    --scope) SCOPE="$2"; SCOPE_EXPLICIT=1; shift 2;;
    --global) GLOBAL=1; shift;;
    --fail-closed-block) FAIL_CLOSED="--fail-closed-block"; shift;;
    --uninstall) ACTION="uninstall"; shift;;
    *) echo "unknown flag $1" >&2; exit 1;;
  esac
done
# Legacy alias: --scope user == --scope global.
if [ "$SCOPE" = "user" ]; then
  echo "warning: --scope user is deprecated, use --scope global or --global" >&2
  SCOPE="global"
fi
if [ "$GLOBAL" = "1" ] && [ "$SCOPE_EXPLICIT" = "1" ] && [ "$SCOPE" = "project" ]; then
  echo "error: --global cannot be combined with --scope project (pick one)." >&2
  exit 1
fi
if [ "$GLOBAL" = "1" ] && [ "$SCOPE_EXPLICIT" = "0" ]; then
  SCOPE="global"
fi
export PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"
python3 -m pip install -e "$MG_ROOT" --break-system-packages -q
HOOK_BIN="$(command -v model-guard-hook || echo "$HOME/.local/bin/model-guard-hook")"
if [ "$ACTION" = "uninstall" ]; then
  PYTHONPATH="$MG_ROOT/src" python3 "$MG_ROOT/scripts/register.py" \
    --agent "$AGENT" --scope "$SCOPE" --uninstall
  exit 0
fi
if [ "$FAIL_CLOSED" = "--fail-closed-block" ]; then
  PYTHONPATH="$MG_ROOT/src" python3 "$MG_ROOT/scripts/register.py" \
    --agent "$AGENT" --scope "$SCOPE" --hook-bin "$HOOK_BIN" \
    --fail-closed-block
else
  PYTHONPATH="$MG_ROOT/src" python3 "$MG_ROOT/scripts/register.py" \
    --agent "$AGENT" --scope "$SCOPE" --hook-bin "$HOOK_BIN"
fi
echo "done ($SCOPE). Verify with: claude (via /hooks) | codex (/hooks) |"
echo "  tail ~/.model-guard/audit.jsonl"