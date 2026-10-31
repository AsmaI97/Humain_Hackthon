import pytest

from authpilot import audit, ehr, llm, store, stub_llm
from authpilot.prompts import CHECK_TOOL
from authpilot.schemas import Status
from authpilot.tools.check_criteria import (
    TOOL_SPEC, CriteriaExtractionError, CriterionDiagnostics, check_criteria, load_criteria,
)
from authpilot.policies import find_policy

CASE = "dev_002"


@pytest.fixture
def case():
    order, chart, label = ehr.load_case_files("dev", "case_002")
    store.create_case(CASE, order)
    return order, chart, label


def _check_reply(tool_input):
    """Fake model: real stub for criteria extraction, a fixed answer for criterion checks."""
    def caller(request):
        if (request.get("tool_choice") or {}).get("name") == CHECK_TOOL:
            return {"content": [{"type": "tool_use", "id": "x1", "name": CHECK_TOOL, "input": tool_input(request)}],
                    "stop_reason": "tool_use", "model": "fake", "usage": {"input_tokens": 5, "output_tokens": 5}}
        return stub_llm.respond(request)
    return caller


def test_stub_run_returns_verified_results_and_saves_state(case):
    _, chart, _ = case
    results = check_criteria(CASE)
    assert [r.criterion_id for r in results] == [f"PA-RX-207:2.{i}" for i in range(1, 5)]
    for result in results:
        assert all(e.verify(chart) for e in result.evidence)
        if result.status == "met":
            assert result.evidence
    state = store.get_case(CASE)
    assert len(state.results) == 4
    assert state.status is Status.needs_evidence
    assert [g.criterion_id for g in state.gaps] == ["PA-RX-207:2.2"]
    assert state.gaps[0].description.startswith("Policy 2.2 (Prior conventional therapy)")
    assert state.checked_doc_ids == list(chart)
    decisions = [e for e in audit.read_events(CASE) if e["event_type"] == "decision"]
    assert len(decisions) == 4


def test_fabricated_evidence_is_dropped_and_met_is_downgraded(case, monkeypatch):
    monkeypatch.setattr(llm, "stub_caller", _check_reply(lambda r: {
        "status": "met", "confidence": 0.95, "reasoning": "Looks fine.",
        "evidence": [{"doc_id": "doc_01_rheumatology_consult", "quote": "Methotrexate 25 mg for 2 years."}],
    }))
    diags: list[CriterionDiagnostics] = []
    results = check_criteria(CASE, diagnostics=diags)
    for result, diag in zip(results, diags):
        assert result.status == "unclear" and result.evidence == []
        assert result.confidence <= 0.3
        assert diag.downgraded and diag.citations_invalid == 1


def test_without_citation_check_fabrications_survive(case, monkeypatch):
    _, chart, _ = case
    monkeypatch.setattr(llm, "stub_caller", _check_reply(lambda r: {
        "status": "met", "confidence": 0.95, "reasoning": "Looks fine.",
        "evidence": [{"doc_id": "doc_01_rheumatology_consult", "quote": "Invented."}],
    }))
    results = check_criteria(CASE, verify_citations=False)
    assert all(r.status == "met" for r in results)
    assert not any(e.verify(chart) for r in results for e in r.evidence)


def test_invalid_output_is_retried_with_the_error(case, monkeypatch):
    calls = []

    def answer(request):
        calls.append(request)
        if len(calls) % 2 == 1:
            return {"status": "probably", "evidence": [], "reasoning": "x", "confidence": 2}
        return {"status": "not_met", "evidence": [], "reasoning": "Nothing found.", "confidence": 0.8}

    monkeypatch.setattr(llm, "stub_caller", _check_reply(answer))
    diags: list[CriterionDiagnostics] = []
    results = check_criteria(CASE, diagnostics=diags)
    assert all(r.status == "not_met" for r in results)
    assert all(d.attempts == 2 and d.invalid_outputs == 1 for d in diags)
    retry_turn = calls[1]["messages"][-1]["content"][0]
    assert retry_turn["type"] == "tool_result" and retry_turn["is_error"] is True


def test_persistently_invalid_output_becomes_unclear_with_zero_confidence(case, monkeypatch):
    monkeypatch.setattr(llm, "stub_caller", _check_reply(lambda r: {"status": "maybe"}))
    diags: list[CriterionDiagnostics] = []
    results = check_criteria(CASE, diagnostics=diags)
    assert all(r.status == "unclear" and r.confidence == 0.0 for r in results)
    assert all(d.attempts == 3 for d in diags)


def test_no_retrieval_puts_full_policy_in_context(case):
    diags: list[CriterionDiagnostics] = []
    check_criteria(CASE, use_retrieval=False, diagnostics=diags)
    n_sections = len(find_policy("payer_a", "J0135").sections)
    assert all(len(d.retrieved_refs) == n_sections for d in diags)


def test_retrieval_context_starts_with_the_criterion_section(case):
    diags: list[CriterionDiagnostics] = []
    check_criteria(CASE, diagnostics=diags)
    assert all(d.retrieved_refs[0] == d.section_ref for d in diags)


def test_extraction_rejects_unknown_sections(monkeypatch):
    def bad(request):
        return {"content": [{"type": "tool_use", "id": "e1", "name": "record_criteria",
                             "input": {"criteria": [{"section_ref": "9.9", "name": "made up"}]}}],
                "stop_reason": "tool_use", "model": "fake", "usage": {}}

    monkeypatch.setattr(llm, "stub_caller", bad)
    with pytest.raises(CriteriaExtractionError, match="9.9"):
        load_criteria(find_policy("payer_a", "72148"))


def test_criterion_text_comes_from_policy_not_model():
    policy = find_policy("payer_a", "72148")
    for criterion in load_criteria(policy):
        assert criterion.text == policy.section(criterion.section_ref).text


def test_tool_spec():
    assert TOOL_SPEC["name"] == "check_criteria"
    assert "case_id" in TOOL_SPEC["input_schema"]["properties"]
