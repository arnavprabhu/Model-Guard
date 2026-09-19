"""Part 2b: Jev-gated composition + evaluate_action entry point."""

from __future__ import annotations

import time

from model_guard import policy as _p
from model_guard.core import (
    ALLOW,
    BLOCK,
    REQUIRE_APPROVAL,
    Decision,
    deterministic_pre_screen,
)
from model_guard.jev_client import JevError, JevResult, judge


def _escalate(verdict: str) -> str:
    if verdict == ALLOW:
        return REQUIRE_APPROVAL
    if verdict == REQUIRE_APPROVAL:
        return BLOCK
    return BLOCK


def jev_post_screen(
    result: JevResult, cfg: _p.PolicyConfig | None = None
) -> Decision:
    """Combine Jev probabilities into a verdict using code-owned thresholds."""
    cfg = cfg or _p.PolicyConfig()
    risk = _p.weighted_risk(result.hazards, cfg)
    top_hazard = max(result.hazards.values()) if result.hazards else 0.0
    verdict = ALLOW
    reasons: list[str] = []

    # Severity gate (highest authority among Jev signals).
    if result.severity >= cfg.block_severity:
        verdict, r = BLOCK, "severity %.2f>=%.2f" % (
            result.severity, cfg.block_severity)
        reasons.append(r)
    elif result.severity >= cfg.ask_severity:
        verdict, r = REQUIRE_APPROVAL, "severity %.2f>=%.2f" % (
            result.severity, cfg.ask_severity)
        reasons.append(r)

    # Single-hazard gate ("any serious violation" rule, not compensating).
    if top_hazard >= cfg.block_any_hazard:
        verdict = BLOCK
        reasons.append("hazard %.2f>=%.2f" % (top_hazard, cfg.block_any_hazard))
    elif top_hazard >= cfg.ask_any_hazard and verdict == ALLOW:
        verdict = REQUIRE_APPROVAL
        reasons.append("hazard %.2f>=%.2f" % (top_hazard, cfg.ask_any_hazard))

    # Weighted composite gate.
    if risk >= cfg.block_weighted:
        verdict = BLOCK
        reasons.append("risk %.2f>=%.2f" % (risk, cfg.block_weighted))
    elif risk >= cfg.ask_weighted and verdict == ALLOW:
        verdict = REQUIRE_APPROVAL
        reasons.append("risk %.2f>=%.2f" % (risk, cfg.ask_weighted))

    # Model's own verdict Choice is advisory: can only escalate, never relax.
    order = {ALLOW: 0, REQUIRE_APPROVAL: 1, BLOCK: 2}
    jev_map = {
        "allow": ALLOW,
        "require_approval": REQUIRE_APPROVAL,
        "block": BLOCK,
    }
    jev_v = jev_map.get(result.verdict, REQUIRE_APPROVAL)
    if order[jev_v] > order[verdict]:
        verdict = jev_v
        reasons.append("jev_choice=%s" % result.verdict)

    # Confidence gating: uncertain model on non-trivial verdicts escalates.
    if result.verdict_confidence < cfg.low_confidence and verdict != BLOCK:
        verdict = _escalate(verdict)
        reasons.append(
            "low_confidence %.2f<%.2f" % (
                result.verdict_confidence, cfg.low_confidence)
        )

    return Decision(
        verdict=verdict,
        reason="; ".join(reasons) or "jev: all signals below thresholds",
        risk=risk,
        hazards=dict(result.hazards),
        severity=result.severity,
        confidence=result.verdict_confidence,
        jev_verdict=result.verdict,
        model=result.model,
        latency_ms=result.latency_ms,
    )


def evaluate_action(
    action: dict,
    cfg: _p.PolicyConfig | None = None,
    jev_fn=judge,
    skip_deterministic: bool = False,
) -> Decision:
    """Full pipeline: deterministic screen -> Jev -> composition.

    skip_deterministic=True forces the Jev path (used by the benchmark to
    measure the semantic layer in isolation).
    """
    cfg = cfg or _p.PolicyConfig()
    started = time.perf_counter()
    if not skip_deterministic:
        pre = deterministic_pre_screen(action, cfg)
        # BLOCK/APPROVAL from deterministic rules are final (fail-safe).
        # ALLOW fast path is final too (audited); Jev stays out of the loop
        # for trivial reads so latency stays near zero.
        if pre is not None:
            pre.latency_ms = (time.perf_counter() - started) * 1000.0
            return pre
    try:
        result = jev_fn(action)
    except JevError as e:
        return Decision(
            verdict=BLOCK if cfg.fail_closed_block else REQUIRE_APPROVAL,
            reason="fail_closed: %s" % e,
            risk=0.5,
            fail_closed=True,
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )
    except Exception as e:  # never crash a hook: fail closed
        return Decision(
            verdict=BLOCK if cfg.fail_closed_block else REQUIRE_APPROVAL,
            reason="fail_closed: unexpected %r" % e,
            risk=0.5,
            fail_closed=True,
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )
    decision = jev_post_screen(result, cfg)
    decision.latency_ms = max(
        decision.latency_ms, (time.perf_counter() - started) * 1000.0
    )
    return decision
