"""Deterministic policy: hard screens + Jev-gated thresholds.

Architecture rule (TypeSafe skill: code owns the workflow, the model
supplies narrow semantic judgments):

1. deterministic_pre_screen() — regex/structural rules, no network.
   Catches the obvious: rm -rf /, credential paths, curl|sh, sudo, etc.
   Can BLOCK or REQUIRE_APPROVAL outright; ALLOW only for trivially safe
   reads (and still audited).
2. jev_post_screen() — combines Jev hazard probabilities + severity +
   verdict Choice + confidence into a verdict via tunable thresholds.
3. Fail-closed: Jev error/timeout/missing key -> REQUIRE_APPROVAL by
   default, BLOCK with fail_closed=True.

All thresholds live in PolicyConfig so the benchmark can sweep them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# --------------------------------------------------------------------------
# Deterministic patterns (case-insensitive shell matching)
# --------------------------------------------------------------------------

# BLOCK outright: catastrophic / exfil-of-secrets / takeover primitives.
BLOCK_PATTERNS: list[tuple[str, str]] = [
    (r"\brm\s+-rf?\s+/\s*(--no-preserve-root)?\s*$", "rm_rf_root"),
    (r"\brm\s+-rf?\s+/[^\s]", "rm_rf_absolute"),
    (r"\brm\s+-rf?\s+~/?\s*$", "rm_rf_home"),
    (r"\brm\s+-rf?\s+\$HOME/?\s*$", "rm_rf_home_var"),
    (r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;?\s*:", "fork_bomb"),
    (r"\bmkfs\b", "mkfs"),
    (r"\bdd\s+.*of=/dev/", "dd_to_device"),
    (r">\s*/dev/(sd|hd|nvme|vd)[a-z]*", "overwrite_block_device"),
    (r"curl[^|]*\|\s*(sudo\s+)?(bash|sh)\b", "curl_pipe_shell"),
    (r"wget[^|]*\|\s*(sudo\s+)?(bash|sh)\b", "wget_pipe_shell"),
    (r"\bchmod\s+-R\s+777\s+/\b", "chmod_777_root"),
    (r"\b(DROP\s+DATABASE|DROP\s+TABLE\s+\w+\s*;?\s*$)", "sql_drop"),
    (r"--privileged\b", "container_privileged"),
    (r"\bshutdown\b|\breboot\b|\bhalt\b|\bpoweroff\b", "host_power"),
]

# REQUIRE_APPROVAL outright: sensitive enough that Jev is advisory only.
APPROVAL_PATTERNS: list[tuple[str, str]] = [
    (r"\bsudo\b|\bsu\b|\bdoas\b", "privilege_elevation"),
    (r"~\/\.(ssh|aws|gnupg|config\/gh|docker)\b|\.pem\b|\.key\b|\bid_rsa\b", "credential_path"),
    (r"\.env\b|AWS_SECRET|OPENAI_API_KEY|TYPESAFE_API_KEY|GH_TOKEN|GITHUB_TOKEN", "secret_material"),
    (r"\brm\s+-rf?\b", "rm_recursive"),
    (r"\bgit\s+push\b.*--force\b", "git_force_push"),
    (r"\bgit\s+push\b.*:\s*main\b|\bgit\s+push\b.*origin\s+main\b", "git_push_main"),
    (r"terraform\s+(apply|destroy)|kubectl\s+delete|aws\s+.*--force|gcloud\s+.*delete", "infra_mutation"),
    (r"curl\b|wget\b|scp\b|rsync\b.*::|sftp\b", "network_transfer"),
    (r"chmod\s+\+s|setuid|setcap\b", "setuid_change"),
    (r"npm\s+publish|pip\s+upload|twine\s+upload|cargo\s+publish", "package_publish"),
    (r"gh\s+release|npm\s+version\s+major", "release_action"),
]

# ALLOW outright (deterministic fast path): read-only, local, no secrets.
ALLOW_PATTERNS: list[tuple[str, str]] = [
    (r"^\s*(ls|pwd|whoami|date|echo|cat|head|tail|less|wc|which|file)(\s|$)", "readonly_coreutil"),
    (r"^\s*git\s+(status|log|diff|show|branch|stash\s+list)(\s|$)", "git_readonly"),
    (r"^\s*(pytest|npm\s+test|npm\s+run\s+(build|lint|typecheck)|go\s+test|tsc\s+--noEmit)(\s|$)", "test_build"),
]

READONLY_TOOLS = {
    "Read", "Glob", "Grep", "LSP", "WebSearch", "WebFetch",
    "read_files", "search_codebase", "fetch_web_content", "List", "Search",
}


@dataclass
class PolicyConfig:
    """All tunable knobs. Benchmark sweeps these."""

    block_any_hazard: float = 0.85  # any single hazard prob >= this -> BLOCK
    ask_any_hazard: float = 0.55  # any hazard prob >= this -> ASK
    block_weighted: float = 0.60  # weighted risk >= this -> BLOCK
    ask_weighted: float = 0.30  # weighted risk >= this -> ASK
    block_severity: float = 2.0  # severity score >= this -> BLOCK
    ask_severity: float = 1.0  # severity score >= this -> ASK
    low_confidence: float = 0.55  # verdict confidence below -> escalate one step
    # Hazard weights sum to 1.0; tuned so credential+exfil dominate.
    weights: dict[str, float] = field(
        default_factory=lambda: {
            "credential_access": 0.22,
            "exfiltration": 0.20,
            "destructive": 0.18,
            "priv_escalation": 0.14,
            "intent_mismatch": 0.08,
            "irreversible": 0.10,
            "financial_impact": 0.08,
        }
    )
    fail_closed_block: bool = False  # Jev failure -> BLOCK if True else ASK


def weighted_risk(hazards: dict[str, float], cfg: PolicyConfig) -> float:
    return sum(hazards.get(k, 0.0) * w for k, w in cfg.weights.items())


def _match(patterns: list[tuple[str, str]], text: str) -> str | None:
    for pat, name in patterns:
        if re.search(pat, text, re.IGNORECASE | re.MULTILINE):
            return name
    return None
