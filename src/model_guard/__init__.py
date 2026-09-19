"""Model Guard — runtime safety layer for AI coding agents.

Core pipeline: normalize an intercepted tool/shell action -> deterministic
policy screen -> TypeSafe/Jev semantic risk judgment (one request) ->
deterministic ALLOW / REQUIRE_APPROVAL / BLOCK verdict -> append-only audit.
"""

__version__ = "0.1.0"

from model_guard.compose import evaluate_action
from model_guard.core import ALLOW, BLOCK, REQUIRE_APPROVAL, Decision

__all__ = [
    "ALLOW",
    "BLOCK",
    "REQUIRE_APPROVAL",
    "Decision",
    "evaluate_action",
    "__version__",
]
