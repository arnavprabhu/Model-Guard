"""Per-agent stdin/stdout translators. Each adapter is a pure function pair:

  extract(hook_input: dict) -> action dict for model_guard
  translate(hook_input, envelope) -> agent-specific output dict

No network here; adapters exec `model-guard check --stdin-json`.
"""

from model_guard.adapters import antigravity, claude, codex, cursor

__all__ = ["antigravity", "claude", "codex", "cursor"]
