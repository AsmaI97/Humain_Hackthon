"""Minimal Phase 1 evaluation: criterion accuracy and citation validity on one split.

Usage: python -m authpilot.eval.criteria_eval --split dev
The sealed split is refused unless --allow-sealed is passed. Never tune on it.
"""

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from authpilot import config, ehr, store
from authpilot.eval.guard import dump_report
from authpilot.data.generator import SPLITS
from authpilot.schemas import CaseLabel, CriterionResult
from authpilot.tools.check_criteria import CriterionDiagnostics, check_criteria

STATUSES = ("met", "not_met", "unclear")


def _overlaps(a, b) -> bool:
    return a.doc_id == b.doc_id and a.start < b.end and b.start < a.end


def _score_case(label: CaseLabel, results: list[CriterionResult], diags: list[CriterionDiagnostics]) -> dict:
    by_ref = {r.criterion_id.split(":")[-1]: r for r in results}
    rows = []
    for expected in label.criteria:
        got = by_ref.get(expected.section_ref)
        predicted = got.status if got else "missing"
        supported = None
        if got and predicted == "met" and expected.status == "met":
            supported = any(_overlaps(e, x) for e in got.evidence for x in expected.evidence)
        rows.append({
            "section_ref": expected.section_ref,
            "criterion_id": expected.criterion_id,
            "expected": expected.status,
            "predicted": predicted,
            "correct": predicted == expected.status,
            "evidence_supported": supported,
            "reasoning": got.reasoning if got else "",
            "cited": [e.span_text for e in got.evidence] if got else [],
            "expected_evidence": [e.span_text for e in expected.evidence],
        })
    return {
        "case_id": label.case_id,
        "procedure": label.procedure,
        "tags": label.hard_case_tags or ["clean"],
        "criteria": rows,
        "errors": sum(not r["correct"] for r in rows),
        "citations_total": sum(d.citations_total for d in diags),
        "citations_invalid": sum(d.citations_invalid for d in diags),
        "attempts": sum(d.attempts for d in diags),
        "invalid_outputs": sum(d.invalid_outputs for d in diags),
        "input_tokens": sum(d.input_tokens for d in diags),
        "output_tokens": sum(d.output_tokens for d in diags),
        "latency_ms": round(sum(d.latency_ms for d in diags), 2),
    }


def _prf(rows: list[dict], status: str) -> dict:
    tp = sum(r["predicted"] == status and r["expected"] == status for r in rows)
    fp = sum(r["predicted"] == status and r["expected"] != status for r in rows)
    fn = sum(r["predicted"] != status and r["expected"] == status for r in rows)
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f1, 4), "support": tp + fn}


def summarize(cases: list[dict]) -> dict:
    rows = [row for case in cases for row in case["criteria"]]
    not_met_rows = [r for r in rows if r["expected"] != "met"]
    supported = [r["evidence_supported"] for r in rows if r["evidence_supported"] is not None]
    citations_total = sum(c["citations_total"] for c in cases)
    attempts = sum(c["attempts"] for c in cases)
    by_tag: dict[str, list[bool]] = defaultdict(list)
    for case in cases:
        for tag in case["tags"]:
            by_tag[tag].extend(r["correct"] for r in case["criteria"])
    return {
        "cases": len(cases),
        "criteria": len(rows),
        "criterion_accuracy": round(sum(r["correct"] for r in rows) / len(rows), 4),
        "per_status": {s: _prf(rows, s) for s in STATUSES},
        "false_met_rate": round(sum(r["predicted"] == "met" for r in not_met_rows) / len(not_met_rows), 4)
        if not_met_rows else 0.0,
        "citation_validity": round(1 - sum(c["citations_invalid"] for c in cases) / citations_total, 4)
        if citations_total else 1.0,
        "evidence_support_rate": round(sum(supported) / len(supported), 4) if supported else None,
        "invalid_output_rate": round(sum(c["invalid_outputs"] for c in cases) / attempts, 4) if attempts else 0.0,
        "accuracy_by_tag": {t: round(sum(v) / len(v), 4) for t, v in sorted(by_tag.items())},
        "confusion": dict(Counter(f"{r['expected']}->{r['predicted']}" for r in rows)),
        "mean_tokens_per_case": round(sum(c["input_tokens"] + c["output_tokens"] for c in cases) / len(cases), 1),
        "mean_latency_ms_per_case": round(sum(c["latency_ms"] for c in cases) / len(cases), 2),
    }


def run(split: str) -> dict:
    store.clear()
    cases = []
    for case_name in ehr.list_cases(split):
        order, _, label = ehr.load_case_files(split, case_name)
        ehr.clear_patient(order.patient_id)
        store.create_case(label.case_id, order)
        diags: list[CriterionDiagnostics] = []
        results = check_criteria(label.case_id, diagnostics=diags)
        cases.append(_score_case(label, results, diags))
    worst = sorted((c for c in cases if c["errors"]), key=lambda c: (-c["errors"], c["case_id"]))[:3]
    return {
        "meta": {
            "split": split,
            "seed": SPLITS[split][1],
            **config.result_provenance(),
            "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        "summary": summarize(cases),
        "worst_failures": worst,
        "cases": cases,
    }


def print_report(report: dict) -> None:
    meta, s = report["meta"], report["summary"]
    print(f"split={meta['split']} mode={meta['llm_mode']} model={meta['agent_model']} prompt={meta['prompt_version']}")
    print(f"cases={s['cases']} criteria={s['criteria']}")
    print(f"criterion accuracy     {s['criterion_accuracy']:.3f}")
    print(f"false-met rate         {s['false_met_rate']:.3f}")
    print(f"citation validity      {s['citation_validity']:.3f}")
    print(f"evidence support rate  {s['evidence_support_rate']}")
    print(f"invalid output rate    {s['invalid_output_rate']:.3f}")
    for status, m in s["per_status"].items():
        print(f"  {status:8s} P={m['precision']:.3f} R={m['recall']:.3f} F1={m['f1']:.3f} n={m['support']}")
    print("accuracy by tag:", s["accuracy_by_tag"])
    print("confusion (expected->predicted):", s["confusion"])
    print(f"mean tokens/case {s['mean_tokens_per_case']}, mean latency/case {s['mean_latency_ms_per_case']} ms")
    print("\nworst failures:" if report["worst_failures"] else "\nworst failures: none")
    for case in report["worst_failures"]:
        print(f"- {case['case_id']} ({case['procedure']}, {','.join(case['tags'])}): {case['errors']} wrong")
        for row in case["criteria"]:
            if not row["correct"]:
                print(f"    {row['section_ref']} {row['criterion_id']}: expected {row['expected']}, got {row['predicted']}")
                print(f"      reasoning: {row['reasoning']}")
                print(f"      cited: {row['cited']}")
                print(f"      label evidence: {row['expected_evidence']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "sealed"], default="dev")
    parser.add_argument("--allow-sealed", action="store_true")
    args = parser.parse_args()
    if args.split == "sealed" and not args.allow_sealed:
        raise SystemExit("Refusing to run on the sealed split without --allow-sealed.")
    report = run(args.split)
    print_report(report)
    print(f"\nsaved {save_report(report)}")


def save_report(report: dict) -> Path:
    out = Path(config.RESULTS_DIR) / f"criteria_{report['meta']['split']}_{report['meta']['llm_mode']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(dump_report(report), encoding="utf-8")
    return out


if __name__ == "__main__":
    main()
