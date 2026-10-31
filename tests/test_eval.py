import json
import sys

import pytest

from authpilot import config, ehr, policies
from authpilot.data import unseen_generator
from authpilot.eval import baselines, faults, metrics, perturb, run_all
from authpilot.eval.harness import load_split, run_agent_case
from authpilot.payer_mock import app as payer_app
from helpers import clean_case


def _rec(case_id, expected, predicted, run=0, **extra):
    base = {
        "case_id": case_id, "run": run, "tags": ["clean"], "expected": expected, "predicted": predicted,
        "confidence": {k: 0.9 for k in predicted}, "cited": {}, "expected_spans": {},
        "citations_total": 2, "citations_invalid": 0, "expected_ready": all(v == "met" for v in expected.values()),
        "predicted_ready": all(v == "met" for v in predicted.values()), "expected_final": "approved",
        "final_status": "approved", "denied": False, "letter_proposed": 4, "letter_accepted": 4,
        "letter_statements": 4, "letter_statements_verified": 4, "invalid_outputs": 0, "check_attempts": 4,
        "safe": True, "error": None, "tool_calls": 5, "input_tokens": 10, "output_tokens": 5, "latency_ms": 1.0,
    }
    base.update(extra)
    return base


# Metrics -----------------------------------------------------------------------------------


def test_criterion_metrics_and_false_met():
    records = [
        _rec("a", {"2.1": "met", "2.2": "not_met"}, {"2.1": "met", "2.2": "met"}),
        _rec("b", {"2.1": "unclear", "2.2": "met"}, {"2.1": "unclear", "2.2": "met"}),
    ]
    assert metrics.criterion_accuracy(records) == 0.75
    assert metrics.false_met_rate(records) == 0.5
    assert metrics.prf(records, "met") == {"precision": 0.6667, "recall": 1.0, "f1": 0.8, "support": 2}


def test_gap_scores_count_missing_predictions_as_gaps():
    records = [_rec("a", {"2.1": "not_met", "2.2": "met", "2.3": "unclear"}, {"2.1": "not_met", "2.2": "unclear"})]
    assert metrics.gap_scores(records) == {"gap_recall": 1.0, "gap_precision": 0.6667}


def test_bootstrap_is_seeded_and_brackets_the_estimate():
    records = [_rec(str(i), {"2.1": "met"}, {"2.1": "met" if i % 4 else "not_met"}) for i in range(40)]
    ci = metrics.bootstrap_ci(records, metrics.criterion_accuracy, n=300, seed=1)
    assert ci == metrics.bootstrap_ci(records, metrics.criterion_accuracy, n=300, seed=1)
    assert ci[0] <= metrics.criterion_accuracy(records) <= ci[1]


def test_coverage_shrinks_as_the_threshold_rises():
    records = [_rec("a", {"2.1": "met"}, {"2.1": "met"}, confidence={"2.1": 0.95}),
               _rec("b", {"2.1": "met"}, {"2.1": "met"}, confidence={"2.1": 0.6})]
    curve = metrics.coverage_curve(records, [0.5, 0.7, 0.99])
    assert [row["coverage"] for row in curve] == [1.0, 0.5, 0.0]


# Regression check --------------------------------------------------------------------------


def _report(acc, false_met=0.1, model="m"):
    return {"meta": {"split": "dev", "llm_mode": "stub", "agent_model": model, "run_at": "t"},
            "summaries": {"agent": {"criterion_accuracy": acc, "false_met_rate": false_met}},
            "perturbations": {}, "faults": {}}


def test_regression_detects_drops_in_either_direction():
    assert run_all.regression_check(_report(0.9), _report(0.9))["status"] == "pass"
    assert run_all.regression_check(_report(0.95), _report(0.9))["status"] == "pass"
    drop = run_all.regression_check(_report(0.85), _report(0.9))
    assert drop["status"] == "regression" and drop["drops"][0]["metric"] == "agent.criterion_accuracy"
    worse = run_all.regression_check(_report(0.9, false_met=0.2), _report(0.9, false_met=0.1))
    assert worse["drops"][0]["metric"] == "agent.false_met_rate"
    assert run_all.regression_check(_report(0.5, model="x"), _report(0.9))["status"] == "no comparable baseline"
    assert run_all.regression_check(_report(0.5), None)["status"] == "no baseline"


# Perturbations -----------------------------------------------------------------------------


def test_threshold_perturbation_relabels_short_therapy():
    cases, tmp, affected = perturb.threshold()
    try:
        assert affected and all(label.procedure == "lumbar_mri" for _, _, label in cases)
        for _, _, label in cases:
            therapy = next(c for c in label.criteria if c.section_ref == "2.1")
            weeks = label.facts.get("therapy_weeks")
            if label.case_id in affected:
                assert weeks < 8 and therapy.status == "not_met" and label.expected_final == "escalated"
            elif isinstance(weeks, int):
                assert weeks >= 8
        text = (tmp / "payer_a_lumbar_mri_72148.md").read_text()
        assert perturb.THRESHOLD_TO in text and "2026.1-t8" in text
    finally:
        perturb.cleanup(tmp)


def test_reworded_policies_keep_the_same_criteria_under_new_numbers():
    cases, path = perturb.reworded()
    with perturb.policy_dir(path):
        for code, procedure in (("72148", "lumbar_mri"), ("J0135", "biologic")):
            policy = policies.find_policy("payer_a", code)
            assert policy.meta["version"].endswith("reworded")
            for new_ref in perturb.REWORDED_REFS[procedure].values():
                assert policy.section(new_ref).heading == "Criteria for coverage"
    assert config.POLICIES_DIR.name == "policies"
    refs = {c.section_ref for _, _, label in cases for c in label.criteria}
    assert refs == {"3.1", "3.2", "3.3", "3.4"}


def test_noisy_chart_keeps_every_label_span_verbatim():
    for order, chart, label in perturb.noisy(limit=10):
        assert "doc_90_education_handout" in chart
        for criterion in label.criteria:
            for ev in criterion.evidence:
                assert ev.verify(chart)


def test_removed_evidence_leaves_no_trace_of_removed_criteria():
    cases, removed = perturb.removed_evidence()
    assert cases and removed
    for order, chart, label in cases:
        for criterion in label.criteria:
            if f"{label.case_id}:{criterion.section_ref}" in removed:
                assert criterion.status == "not_met" and not criterion.evidence
            else:
                assert all(ev.verify(chart) for ev in criterion.evidence)


# Unseen procedure --------------------------------------------------------------------------


def test_unseen_cases_are_deterministic_and_match_the_files():
    first = [unseen_generator.case_files(c) for c in unseen_generator.generate_unseen()]
    assert first == [unseen_generator.case_files(c) for c in unseen_generator.generate_unseen()]
    for case, files in zip(unseen_generator.generate_unseen(), first):
        case_dir = config.CASES_DIR / "unseen" / case.label.case_id.replace("unseen_", "case_")
        for name, body in files.items():
            assert (case_dir / name).read_text() == body
        for criterion in case.label.criteria:
            assert all(ev.verify(case.chart) for ev in criterion.evidence)


def test_unseen_policy_has_no_coverage_criteria_heading():
    policy = policies.find_policy("payer_a", "J3490")
    assert not any("criteria" in s.heading.lower() for s in policy.sections)
    assert {s.ref for s in policy.sections} >= {"3.1", "3.2", "4.1"}


def test_agent_on_unseen_procedure_ends_safely():
    order, _, label = load_split("unseen", 1)[0]
    record = run_agent_case(order, label, variant="unseen")
    assert record.safe and record.error is None
    assert record.final_status in {"approved", "escalated"}
    assert payer_app.submissions()["count"] == record.submissions


# Harness, baselines, faults ----------------------------------------------------------------


def test_harness_records_a_clean_case():
    order, _, label = clean_case()
    record = run_agent_case(order, label)
    assert record.predicted == {"2.1": "met", "2.2": "met", "2.3": "met", "2.4": "met"}
    assert record.final_status == "approved" and record.safe and record.submissions == 1
    assert record.letter_statements == record.letter_statements_verified == 4
    assert record.input_tokens > 0 and record.tool_calls == 5


def test_baselines_produce_predictions_without_loops():
    order, _, label = clean_case()
    for name in ("single_prompt", "keyword"):
        (record,) = baselines.run_baseline(name, [(order, None, label)])
        assert set(record["predicted"]) == {"2.1", "2.2", "2.3", "2.4"}
        assert record["final_status"] is None


def test_payer_down_fault_is_safe():
    order, _, label = clean_case()
    with faults.payer_down():
        record = run_agent_case(order, label, variant="fault")
    assert record.safe and record.queued and record.submissions == 0


# End to end --------------------------------------------------------------------------------


def test_quick_evaluation_saves_report_and_passes_regression(tmp_path):
    report = run_all.evaluate("dev", runs=2, limit=3, skip={"faults", "ablations"}, log=lambda *_: None)
    path, regression = run_all.save(report, tmp_path)
    assert regression["status"] == "no baseline"
    saved = json.loads(path.read_text())
    assert {"agent", "single_prompt", "keyword"} <= set(saved["summaries"])
    assert saved["meta"]["runs"] == 2 and saved["agent_run_spread"]["criterion_accuracy"]["runs"] == 2
    assert set(saved["perturbations"]) == {"threshold_6_to_8_weeks", "reworded_policy", "noisy_chart",
                                           "removed_evidence", "unseen_procedure"}
    markdown = (tmp_path / "latest_dev_stub.md").read_text()
    for heading in ("Main results", "Robustness and adaptation", "Coverage vs accuracy", "Regression check"):
        assert heading in markdown
    again = run_all.evaluate("dev", runs=2, limit=3, skip={"faults", "ablations"}, log=lambda *_: None)
    assert run_all.save(again, tmp_path)[1]["status"] == "pass"


def test_one_page_summary_is_built_from_a_saved_report(tmp_path, monkeypatch):
    from authpilot.eval import summary

    monkeypatch.setattr(config, "RESULTS_DIR", tmp_path)
    assert summary.latest_report() is None
    report = run_all.evaluate("dev", runs=1, limit=3, skip={"faults", "ablations"}, log=lambda *_: None)
    run_all.save(report, tmp_path / "eval")
    path = summary.latest_report()
    assert path.name == "latest_dev_stub.json"
    text = summary.build(json.loads(path.read_text()))
    for heading in ("Headline results vs proposal targets", "Does each part earn its place?",
                    "Robustness and adaptation", "Safety under faults", "Read with care"):
        assert heading in text
    assert len(text.splitlines()) < 80


def test_slides_are_built_from_a_saved_report_and_escape_text(tmp_path):
    from authpilot.eval import slides

    report = run_all.evaluate("dev", runs=1, limit=3, skip={"faults", "ablations"}, log=lambda *_: None)
    report["meta"]["agent_model"] = "<script>x</script>"
    html = slides.build(report)
    assert html.count('<section class="slide') == 13
    assert "<script>x</script>" not in html and "&lt;script&gt;" in html
    assert "offline stub model" in html and "Headline results vs targets" in html


def test_quick_criteria_eval_ignores_documents_left_by_earlier_runs():
    from authpilot.agent import auto_approver, run_case
    from authpilot.eval import criteria_eval
    from helpers import supplied_gap_case

    order, _, label = supplied_gap_case()
    run_case(label.case_id, order, approver=auto_approver("demo"))
    supplied = set(ehr.load_supplemental(order.patient_id)["documents"])
    assert supplied and supplied <= set(ehr.load_chart(order.patient_id))
    report = criteria_eval.run("dev")
    row = next(c for c in report["cases"] if c["case_id"] == label.case_id)
    assert all(r["correct"] for r in row["criteria"] if r["expected"] == "not_met")


def test_sealed_split_is_refused(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run_all", "--split", "sealed"])
    with pytest.raises(SystemExit, match="sealed"):
        run_all.main()
