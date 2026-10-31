import pytest

from authpilot import audit, gate, llm, store, stub_llm
from authpilot.agent import auto_approver, resume_case, run_case
from authpilot.payer_mock import app as payer_app
from authpilot.schemas import Status
from authpilot.tools._common import ToolRefused
from authpilot.tools.check_criteria import check_criteria
from authpilot.tools.draft_letter import draft_letter
from authpilot.tools.submit_request import submit_request
from helpers import appeal_case, clean_case, start

APPROVE = auto_approver("test-reviewer")


def _ready(case):
    case_id = start(case)
    check_criteria(case_id)
    draft_letter(case_id)
    return case_id


def test_rerunning_a_case_creates_a_new_submission():
    order, _, label = clean_case()
    first, _ = run_case(label.case_id, order, approver=APPROVE)
    second, _ = run_case(label.case_id, order, approver=APPROVE)
    assert first.request_id != second.request_id
    assert first.submissions != second.submissions
    assert payer_app.submissions()["count"] == 2


def test_submit_is_refused_without_human_approval():
    case_id = _ready(clean_case())
    with pytest.raises(ToolRefused, match="human approval"):
        submit_request(case_id)
    assert store.get_case(case_id).submission_id is None
    assert payer_app.submissions()["count"] == 0


def test_approval_is_bound_to_the_exact_letter():
    case_id = _ready(clean_case())
    gate.approve(case_id, "reviewer")
    state = store.get_case(case_id)
    state.letter += "\nAdded after approval."
    store.save_case(state)
    with pytest.raises(ToolRefused, match="human approval"):
        submit_request(case_id)


def test_approval_is_logged_as_a_human_action():
    case_id = _ready(clean_case())
    gate.approve(case_id, "Sara")
    event = [e for e in audit.read_events(case_id) if e["event_type"] == "human_action"][-1]
    assert event["actor"] == "Sara" and event["payload"]["action"] == "approve"
    assert submit_request(case_id).startswith("SUB-")


def test_nothing_to_approve_is_refused():
    case_id = start(clean_case())
    with pytest.raises(ToolRefused):
        gate.approve(case_id, "reviewer")


def test_agent_pauses_at_the_gate_and_resumes_after_approval():
    order, _, label = clean_case()
    state, _ = run_case(label.case_id, order)
    assert state.status is Status.ready_for_approval and state.submission_id is None
    assert gate.awaiting_approval(state) == "initial"
    gate.approve(label.case_id, "reviewer")
    state, _ = resume_case(label.case_id)
    assert state.status is Status.approved


def test_reviewer_rejection_escalates():
    order, _, label = clean_case()
    state, _ = run_case(label.case_id, order, approver=lambda s, kind: (False, "letter needs a signature"))
    assert state.status is Status.escalated and "letter needs a signature" in state.escalation_reason
    assert state.submission_id is None


def test_agent_cannot_approve_itself(monkeypatch):
    def planner(request):
        if "<case_state>" in str(request["messages"]):
            return {"content": [{"type": "tool_use", "id": "p", "name": "approve", "input": {"case_id": "x"}}],
                    "stop_reason": "tool_use", "model": "fake", "usage": {}}
        return stub_llm.respond(request)

    monkeypatch.setattr(llm, "stub_caller", planner)
    order, _, label = clean_case()
    state, _ = run_case(label.case_id, order)
    assert state.submission_id is None and state.approval is None


def test_appeal_needs_its_own_approval():
    order, chart, label = appeal_case()
    approvals = []

    def approver(state, kind):
        approvals.append(kind)
        return (kind == "initial", "reviewer")

    state, _ = run_case(label.case_id, order, approver=approver)
    assert approvals == ["initial", "appeal"]
    assert state.status is Status.escalated and len(state.submissions) == 1


def test_appeal_letter_addresses_the_denial_with_verified_evidence():
    order, chart, label = appeal_case()
    state, _ = run_case(label.case_id, order, approver=APPROVE)
    assert state.status is Status.approved
    assert "DAS28-SCORE" in state.appeal_letter and "2.4" in state.appeal_letter
    for statement in state.appeal_statements:
        assert statement.criterion_id.endswith(":2.4")
        assert all(e.verify(chart) for e in statement.evidence)
    assert any("flowsheet" in e.doc_id for s in state.appeal_statements for e in s.evidence)
    decision = payer_app.status(state.submissions[-1])
    assert decision.level == "appeal"


def test_same_denial_twice_escalates_instead_of_repeating(monkeypatch):
    monkeypatch.setattr(payer_app, "review", lambda package, level: ("denied", "RF-SCREEN", "Section 2.2: denied."))
    order, _, label = clean_case()
    state, _ = run_case(label.case_id, order, approver=APPROVE)
    assert state.status is Status.escalated
    assert state.loop_counts.appeals == 1 and len(state.submissions) == 2
    assert "cannot be appealed further" in state.escalation_reason


def test_appeal_cap_escalates(monkeypatch):
    codes = iter([("CT-DURATION", "2.1"), ("RF-SCREEN", "2.2"), ("NEURO-EXAM", "2.3")])

    def deny(package, level):
        code, ref = next(codes)
        return "denied", code, f"Section {ref}: denied."

    monkeypatch.setattr(payer_app, "review", deny)
    order, _, label = clean_case()
    state, _ = run_case(label.case_id, order, approver=APPROVE)
    assert state.status is Status.escalated
    assert state.loop_counts.appeals == 2 and len(state.submissions) == 3
    assert "after 2 appeals" in state.escalation_reason
