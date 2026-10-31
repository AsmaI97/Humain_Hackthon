"""Fault injection: every fault must leave the case in a safe state.

Safe means: nothing reaches the payer that was not human-approved and evidence-backed, nothing
is submitted twice, and the case ends escalated, queued for retry, or correctly completed.
"""

import pytest

from authpilot import audit, config, llm, payer_client, stub_llm
from authpilot.agent import auto_approver, resume_case, run_case
from authpilot.payer_client import PayerUnavailable
from authpilot.payer_mock import app as payer_app
from authpilot.prompts import CHECK_TOOL
from authpilot.schemas import Status
from authpilot.tools import search_policy
from helpers import clean_case

APPROVE = auto_approver("test-reviewer")


def _run(case=None):
    order, _, label = case or clean_case()
    state, run_id = run_case(label.case_id, order, approver=APPROVE)
    return state, run_id


def _fallback_rules(case_id):
    return [e["payload"]["rule"] for e in audit.read_events(case_id) if e["event_type"] == "fallback"]


def _assert_nothing_submitted(state):
    assert state.submission_id is None and state.submissions == []
    assert payer_app.submissions()["count"] == 0


def _check_answers(transform):
    """Fake model: criterion checks come from the stub, then pass through transform()."""
    def caller(request):
        response = stub_llm.respond(request)
        if (request.get("tool_choice") or {}).get("name") == CHECK_TOOL:
            block = response["content"][0]
            block["input"] = transform(block["input"])
        return response
    return caller


# Invalid structured output --------------------------------------------------------------


def test_invalid_model_output_is_retried_then_escalated(monkeypatch):
    monkeypatch.setattr(llm, "stub_caller", _check_answers(lambda answer: {"status": "probably", "confidence": 7}))
    state, _ = _run()
    assert state.status is Status.escalated
    assert "model output invalid after retries" in state.escalation_reason
    _assert_nothing_submitted(state)
    rules = _fallback_rules(state.case_id)
    assert "invalid_output_exhausted" in rules and "invalid_output_escalate" in rules


# Evidence span not found ------------------------------------------------------------------


def test_fabricated_evidence_is_dropped_and_the_case_escalates(monkeypatch):
    def fabricate(answer):
        return {"status": "met", "confidence": 0.95, "reasoning": "Documented.",
                "evidence": [{"doc_id": "doc_01_progress_note", "quote": "Completed 40 weeks of physical therapy."}]}

    monkeypatch.setattr(llm, "stub_caller", _check_answers(fabricate))
    state, _ = _run()
    assert state.status is Status.escalated
    assert all(r.status == "unclear" and r.evidence == [] for r in state.results)
    assert "Evidence not found" in state.escalation_reason
    _assert_nothing_submitted(state)
    assert "evidence_not_found" in _fallback_rules(state.case_id)


# Low confidence or unclear ----------------------------------------------------------------


def test_low_confidence_abstains_and_escalates(monkeypatch):
    monkeypatch.setattr(llm, "stub_caller", _check_answers(lambda answer: {**answer, "confidence": 0.4}))
    state, _ = _run()
    assert state.status is Status.escalated and state.escalation_reason.startswith("abstained")
    assert all(r.status == "met" for r in state.results)
    _assert_nothing_submitted(state)


def test_unclear_criterion_abstains_with_a_summary():
    from helpers import find_case

    state, _ = _run(find_case(lambda l: "ambiguous" in l.hard_case_tags))
    assert state.status is Status.escalated
    assert "unclear" in state.escalation_reason
    _assert_nothing_submitted(state)


# Weak or empty retrieval ------------------------------------------------------------------


def test_empty_retrieval_widens_then_uses_full_policy(monkeypatch):
    monkeypatch.setattr(search_policy, "search_sections", lambda policy, query, k: [])
    state, _ = _run()
    rules = _fallback_rules(state.case_id)
    assert rules.count("retrieval_widen") == 4 and rules.count("retrieval_full_policy") == 4
    assert state.status is Status.approved


def test_policy_without_sections_escalates(monkeypatch):
    from authpilot import fallback
    from authpilot.policies import Policy

    real = fallback.policy_context

    def empty_policy(policy, *args, **kwargs):
        return real(Policy(meta=policy.meta, sections=(), path=policy.path), *args, **kwargs)

    monkeypatch.setattr(fallback, "policy_context", empty_policy)
    state, _ = _run()
    assert state.status is Status.escalated and "no readable sections" in state.escalation_reason
    _assert_nothing_submitted(state)


# LLM error or timeout ---------------------------------------------------------------------


def test_llm_timeouts_switch_to_cheap_model(monkeypatch):
    def agent_model_down(request):
        if request["model"] == config.AGENT_MODEL:
            raise llm.TransientLLMError("timeout")
        return stub_llm.respond(request)

    monkeypatch.setattr(llm, "stub_caller", agent_model_down)
    state, _ = _run()
    assert state.status is Status.approved
    assert "llm_error_switch_model" in _fallback_rules(state.case_id)


def test_llm_down_queues_the_case_and_resume_completes_it(monkeypatch):
    calls = []

    def down(request):
        calls.append(request["model"])
        raise llm.TransientLLMError("timeout")

    monkeypatch.setattr(llm, "stub_caller", down)
    state, _ = _run()
    assert state.queued_reason and "LLM unavailable" in state.queued_reason
    assert state.status is Status.intake
    _assert_nothing_submitted(state)
    retries = config.LLM_MAX_RETRIES + 1
    assert calls == [config.AGENT_MODEL] * retries + [config.CHEAP_MODEL] * retries
    assert (config.RUNTIME_DIR / "queue.jsonl").exists()

    monkeypatch.setattr(llm, "stub_caller", stub_llm.respond)
    state, _ = resume_case(state.case_id, approver=APPROVE)
    assert state.status is Status.approved and state.queued_reason is None


# Payer down -------------------------------------------------------------------------------


def test_payer_down_marks_pending_and_never_double_submits(monkeypatch):
    real_submit = payer_client.submit

    def down(package):
        raise PayerUnavailable("connection refused")

    monkeypatch.setattr(payer_client, "submit", down)
    state, _ = _run()
    assert state.queued_reason and "payer unavailable" in state.queued_reason
    assert state.payer_status == "pending" and state.status is Status.ready_for_approval
    _assert_nothing_submitted(state)
    assert _fallback_rules(state.case_id).count("payer_retry") == config.PAYER_MAX_RETRIES + 1

    monkeypatch.setattr(payer_client, "submit", real_submit)
    state, _ = resume_case(state.case_id, approver=APPROVE)
    assert state.status is Status.approved
    assert payer_app.submissions()["count"] == 1


def test_lost_response_retry_reuses_the_idempotency_key(monkeypatch):
    real_submit = payer_client.submit
    attempts = []

    def flaky(package):
        attempts.append(package.idempotency_key)
        decision = real_submit(package)
        if len(attempts) == 1:
            raise PayerUnavailable("response lost after the payer accepted the request")
        return decision

    monkeypatch.setattr(payer_client, "submit", flaky)
    state, _ = _run()
    assert state.status is Status.approved
    assert len(attempts) == 2 and attempts[0] == attempts[1]
    assert payer_app.submissions()["count"] == 1 and len(state.submissions) == 1


def test_payer_down_during_status_check_queues_then_recovers(monkeypatch):
    real_status = payer_client.status
    monkeypatch.setattr(payer_client, "status", lambda sid: (_ for _ in ()).throw(PayerUnavailable("timeout")))
    state, _ = _run()
    assert state.status is Status.submitted and state.queued_reason
    monkeypatch.setattr(payer_client, "status", real_status)
    state, _ = resume_case(state.case_id, approver=APPROVE)
    assert state.status is Status.approved and payer_app.submissions()["count"] == 1


def test_payer_http_errors_are_classified():
    class Broken:
        def request(self, *args, **kwargs):
            raise __import__("httpx").ConnectError("refused")

    payer_client._client, payer_client._client_url = Broken(), config.PAYER_URL
    try:
        with pytest.raises(PayerUnavailable):
            payer_client.status("SUB-00001")
    finally:
        payer_client._client = None


# Corrupted planner output -----------------------------------------------------------------


def test_corrupted_planner_output_is_contained(monkeypatch):
    def garbage(request):
        if "<case_state>" in str(request["messages"]):
            return {"content": [{"type": "text", "text": "{not json"}], "stop_reason": "end_turn",
                    "model": "fake", "usage": {}}
        return stub_llm.respond(request)

    monkeypatch.setattr(llm, "stub_caller", garbage)
    state, _ = _run()
    assert state.status is Status.escalated and "cap" in state.escalation_reason
    _assert_nothing_submitted(state)
