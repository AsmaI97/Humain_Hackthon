"""Metrics over evaluation records, bootstrap confidence intervals, and the coverage curve."""

import random
import statistics
from collections import defaultdict
from typing import Callable

STATUSES = ("met", "not_met", "unclear")


def _rows(records: list[dict]) -> list[tuple[str, str]]:
    return [(exp, rec["predicted"].get(ref, "missing")) for rec in records for ref, exp in rec["expected"].items()]


def _ratio(num: float, den: float) -> float | None:
    return round(num / den, 4) if den else None


def prf(records: list[dict], status: str) -> dict:
    rows = _rows(records)
    tp = sum(e == status and p == status for e, p in rows)
    fp = sum(e != status and p == status for e, p in rows)
    fn = sum(e == status and p != status for e, p in rows)
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4),
            "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0, "support": tp + fn}


def criterion_accuracy(records: list[dict]) -> float | None:
    rows = _rows(records)
    return _ratio(sum(e == p for e, p in rows), len(rows))


def false_met_rate(records: list[dict]) -> float | None:
    rows = [(e, p) for e, p in _rows(records) if e != "met"]
    return _ratio(sum(p == "met" for _, p in rows), len(rows))


def citation_validity(records: list[dict]) -> float | None:
    total = sum(r["citations_total"] for r in records)
    return _ratio(total - sum(r["citations_invalid"] for r in records), total)


def evidence_support(records: list[dict]) -> float | None:
    """For criteria both labeled and predicted met: does a cited span overlap a labeled span?"""
    hits = total = 0
    for rec in records:
        for ref, exp in rec["expected"].items():
            if exp == "met" and rec["predicted"].get(ref) == "met":
                total += 1
                labeled = rec["expected_spans"].get(ref, [])
                hits += any(c[0] == l[0] and c[1] < l[2] and l[1] < c[2]
                            for c in rec["cited"].get(ref, []) for l in labeled)
    return _ratio(hits, total)


def gap_scores(records: list[dict]) -> dict:
    found = planted = overlap = 0
    for rec in records:
        p = {ref for ref, s in rec["expected"].items() if s != "met"}
        f = {ref for ref in rec["expected"] if rec["predicted"].get(ref, "missing") != "met"}
        planted += len(p)
        found += len(f)
        overlap += len(p & f)
    return {"gap_recall": _ratio(overlap, planted), "gap_precision": _ratio(overlap, found)}


def decision_accuracy(records: list[dict]) -> float | None:
    rows = [r for r in records if r["predicted_ready"] is not None]
    return _ratio(sum(r["predicted_ready"] == r["expected_ready"] for r in rows), len(rows))


def final_accuracy(records: list[dict]) -> float | None:
    rows = [r for r in records if r["final_status"] is not None and r["expected_final"]]
    return _ratio(sum(r["final_status"] == r["expected_final"] for r in rows), len(rows))


def denial_recovery(records: list[dict]) -> dict:
    denied = [r for r in records if r["denied"]]
    return {"denied_runs": len(denied), "recovered": sum(r["final_status"] == "approved" for r in denied),
            "rate": _ratio(sum(r["final_status"] == "approved" for r in denied), len(denied))}


def letter_scores(records: list[dict]) -> dict:
    return {
        "letter_faithfulness": _ratio(sum(r["letter_accepted"] for r in records),
                                      sum(r["letter_proposed"] for r in records)),
        "letter_support": _ratio(sum(r["letter_statements_verified"] for r in records),
                                 sum(r["letter_statements"] for r in records)),
    }


def _mean(records: list[dict], key: str) -> float | None:
    values = [r[key] for r in records if r.get(key) is not None]
    return round(statistics.fmean(values), 2) if values else None


def summarize(records: list[dict]) -> dict:
    agentic = [r for r in records if r["final_status"] is not None]
    return {
        "cases": len({r["case_id"] for r in records}),
        "runs": len({r["run"] for r in records}) if records else 0,
        "criteria": len(_rows(records)),
        "criterion_accuracy": criterion_accuracy(records),
        "per_status": {s: prf(records, s) for s in STATUSES},
        "false_met_rate": false_met_rate(records),
        "citation_validity": citation_validity(records),
        "evidence_support": evidence_support(records),
        **gap_scores(records),
        "decision_accuracy": decision_accuracy(records),
        "final_accuracy": final_accuracy(agentic) if agentic else None,
        "denial_recovery": denial_recovery(agentic) if agentic else None,
        **(letter_scores(agentic) if agentic else {"letter_faithfulness": None, "letter_support": None}),
        "invalid_output_rate": _ratio(sum(r["invalid_outputs"] for r in records),
                                      sum(r["check_attempts"] for r in records)),
        "safe_rate": _ratio(sum(r["safe"] for r in records), len(records)),
        "errors": sum(r["error"] is not None for r in records),
        "mean_tool_calls": _mean(agentic, "tool_calls"),
        "mean_tokens": round(statistics.fmean([r["input_tokens"] + r["output_tokens"] for r in records]), 1)
        if records else None,
        "mean_latency_ms": _mean(records, "latency_ms"),
        "accuracy_by_tag": {tag: criterion_accuracy([r for r in records if tag in r["tags"]])
                            for tag in sorted({t for r in records for t in r["tags"]})},
        "final_status_counts": dict(sorted(_count(r["final_status"] for r in agentic).items())),
    }


def _count(values) -> dict:
    out: dict = defaultdict(int)
    for v in values:
        out[str(v)] += 1
    return dict(out)


def per_run_spread(records: list[dict], metric: Callable[[list[dict]], float | None]) -> dict:
    """Mean and standard deviation of a metric across repeated runs of the same cases."""
    values = [metric([r for r in records if r["run"] == run]) for run in sorted({r["run"] for r in records})]
    values = [v for v in values if v is not None]
    if not values:
        return {"mean": None, "std": None, "runs": 0}
    return {"mean": round(statistics.fmean(values), 4),
            "std": round(statistics.pstdev(values), 4) if len(values) > 1 else 0.0, "runs": len(values)}


def bootstrap_ci(records: list[dict], metric: Callable[[list[dict]], float | None], n: int = 1000,
                 seed: int = 0, alpha: float = 0.05) -> list[float] | None:
    """Percentile bootstrap over cases (all runs of a resampled case are kept together)."""
    by_case: dict[str, list[dict]] = defaultdict(list)
    for rec in records:
        by_case[rec["case_id"]].append(rec)
    case_ids = sorted(by_case)
    if not case_ids:
        return None
    rng = random.Random(seed)
    stats = []
    for _ in range(n):
        sample = [rec for cid in rng.choices(case_ids, k=len(case_ids)) for rec in by_case[cid]]
        value = metric(sample)
        if value is not None:
            stats.append(value)
    if not stats:
        return None
    stats.sort()
    lo = stats[int(alpha / 2 * (len(stats) - 1))]
    hi = stats[int((1 - alpha / 2) * (len(stats) - 1))]
    return [round(lo, 4), round(hi, 4)]


def coverage_curve(records: list[dict], thresholds: list[float]) -> list[dict]:
    """A case is covered at threshold t when no initial verdict is unclear and every confidence is
    at least t (otherwise the agent abstains). Accuracy is measured on covered cases only."""
    curve = []
    for t in thresholds:
        covered = [r for r in records if r["predicted"] and all(
            r["predicted"][ref] != "unclear" and r["confidence"].get(ref, 0) >= t for ref in r["predicted"])]
        curve.append({
            "threshold": t,
            "coverage": _ratio(len(covered), len(records)),
            "criterion_accuracy": criterion_accuracy(covered),
            "decision_accuracy": decision_accuracy(covered),
        })
    return curve
