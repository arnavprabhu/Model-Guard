"""Part 4: CLI entry — 4-system comparison, table, JSON output."""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import platform
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from model_guard.policy import PolicyConfig  # noqa: E402

from _core import JEV_PRICE_PER_MTOK, dataset_hash, git_commit  # noqa: E402
from _core import action_of, allow_all_verdict, load_cases  # noqa: E402
from _core import static_verdict  # noqa: E402
from _score import by_category, guard_verdict, jev_only_verdict  # noqa: E402
from _score import score  # noqa: E402


def run_system(cases, system, cfg):
    """Run one system over all cases. Returns (rows, usages, extras)."""
    rows, usages = [], []
    local_hits = jev_calls = fail_closed = 0
    models = set()
    for c in cases:
        if system == "allow_all":
            got, ms = allow_all_verdict(c)
            rows.append({"expected": c["expected"], "got": got,
                         "category": c["category"], "latency_ms": ms,
                         "id": c["id"]})
        elif system == "static":
            got, ms = static_verdict(c)
            rows.append({"expected": c["expected"], "got": got,
                         "category": c["category"], "latency_ms": ms,
                         "id": c["id"]})
            if got != "ALLOW":
                local_hits += 1
        elif system == "jev_only":
            g = jev_only_verdict(c, cfg)
            rows.append({"expected": c["expected"], "got": g["verdict"],
                         "category": c["category"],
                         "latency_ms": g["latency_ms"], "id": c["id"],
                         "fail_closed": g["fail_closed"]})
            if g.get("usage"):
                usages.append(g["usage"])
            jev_calls += 1
            if g["fail_closed"]:
                fail_closed += 1
            if g.get("model"):
                models.add(g["model"])
        else:  # guard (full: deterministic floor + RULES + Jev)
            g = guard_verdict(c, cfg)
            rows.append({"expected": c["expected"], "got": g["verdict"],
                         "category": c["category"],
                         "latency_ms": g["latency_ms"], "id": c["id"],
                         "fail_closed": g["fail_closed"]})
            if g.get("usage"):
                usages.append(g["usage"])
            if g.get("deterministic_hit"):
                local_hits += 1
            else:
                jev_calls += 1
            if g["fail_closed"]:
                fail_closed += 1
            if g.get("model"):
                models.add(g["model"])
    return rows, usages, {"local_hits": local_hits, "jev_calls": jev_calls,
                          "fail_closed": fail_closed, "models": sorted(models)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="mg-bench")
    ap.add_argument("--mode", default="all",
                    choices=["allow_all", "static", "jev_only", "guard",
                             "both", "all"])
    ap.add_argument("--cases", default=None)
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--fail-closed-block", action="store_true")
    ap.add_argument("--model", default=None,
                    help="Pin Jev model (else TYPESAFE_MODEL or jev-latest).")
    args = ap.parse_args(argv)

    if args.model:
        os.environ["TYPESAFE_MODEL"] = args.model
    here = os.path.dirname(os.path.abspath(__file__))
    cases_path = args.cases or os.path.join(here, "cases.jsonl")
    cases = load_cases(args.cases)
    cfg = PolicyConfig(fail_closed_block=args.fail_closed_block)
    if args.mode == "both":  # legacy: static vs guard
        systems = ["static", "guard"]
    elif args.mode == "all":
        systems = ["allow_all", "static", "jev_only", "guard"]
    else:
        systems = [args.mode]
    report: dict = {
        "meta": {
            "datetime_utc": datetime.now(timezone.utc).isoformat(),
            "git_commit": git_commit(),
            "dataset": os.path.basename(cases_path),
            "dataset_hash": dataset_hash(cases_path),
            "n_cases": len(cases),
            "python": platform.python_version(),
            "jev_model_requested": args.model
            or os.environ.get("TYPESAFE_MODEL", "") or "jev-latest",
            "policy_thresholds": dataclasses.asdict(cfg),
            "price_per_mtok_usd": JEV_PRICE_PER_MTOK,
        },
        "n": len(cases),
    }

    for system in systems:
        rows, usages, extras = run_system(cases, system, cfg)
        s = score(rows)
        s["by_category"] = by_category(rows)
        s["fail_closed_count"] = extras["fail_closed"]
        if system in ("jev_only", "guard"):
            tot_in = sum(u.get("input_tokens", 0) for u in usages)
            if tot_in:
                per_1k = tot_in / len(rows) / 1e6 * JEV_PRICE_PER_MTOK * 1000
            else:
                per_1k = 1100 / 1e6 * JEV_PRICE_PER_MTOK * 1000
            s["cost_per_1k_actions_usd"] = round(per_1k, 4)
            s["cost_basis"] = ("measured" if tot_in else
                               "estimate_1100_in_tok_per_action")
            s["jev_input_tokens_total"] = tot_in
            s["jev_calls"] = extras["jev_calls"]
            s["local_hits"] = extras["local_hits"]
            nrows = len(rows) or 1
            s["local_pct"] = round(extras["local_hits"] / nrows * 100, 1)
            s["jev_pct"] = round(extras["jev_calls"] / nrows * 100, 1)
            s["jev_models_seen"] = extras["models"]
            if extras["models"]:
                report["meta"]["jev_model_seen"] = extras["models"]
        report[system] = s
        if system == "guard":
            report["guard_rows"] = rows

    # Comparison table: headline metrics only.
    if len(systems) > 1:
        print("=== benchmark (%d cases) ===" % len(cases))
        hdr = "%-28s" + "".join("%14s" for _ in systems)
        print(hdr % (("metric",) + tuple(systems)))
        for k in ("unsafe_auto_allow_rate", "dangerous_auto_allow_rate",
                  "unnecessary_intervention_rate", "false_block_rate",
                  "exact_accuracy", "p50_ms", "p95_ms"):
            print(hdr % ((k,) + tuple(report[s][k] for s in systems)))
        for s in systems:
            if report[s].get("cost_per_1k_actions_usd") is not None:
                print("%-28s %14s" % (
                    "cost/1k (%s)" % s,
                    "$%.4f (%s)" % (report[s]["cost_per_1k_actions_usd"],
                                    report[s]["cost_basis"])))
        for s in systems:
            if report[s].get("local_pct") is not None:
                print("%-28s %14s" % (
                    "local/jev split (%s)" % s,
                    "%s%%/%s%%" % (report[s]["local_pct"],
                                   report[s]["jev_pct"])))
        if report.get("guard", {}).get("fail_closed_count"):
            print("note: guard fail-closed (no live Jev) on %d/%d; "
                  "run with TYPESAFE_API_KEY for semantic numbers."
                  % (report["guard"]["fail_closed_count"], len(cases)))
        if "guard" in report:
            print("\n--- per-category guard "
                  "(unsafe/danger/unnec/fblock/acc) ---")
            for cat, m in report["guard"]["by_category"].items():
                print("%-18s n=%-3d unsafe=%-2d danger=%-2d unnec=%-2d "
                      "fblock=%-2d acc=%s"
                      % (cat, m["n"], m["unsafe"], m["dangerous"],
                         m["unnecessary"], m["false_block"],
                         m["exact_accuracy"]))
    else:
        print(json.dumps(report[systems[0]], indent=2))

    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(report, f, indent=2)
        print("wrote %s" % args.json_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
