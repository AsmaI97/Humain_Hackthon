from authpilot import audit, config, llm, stub_llm
from authpilot.agent import TOOLS, allowed_tools, auto_approver, run_case
from authpilot.schemas import Status
from helpers import appeal_case, clean_case, supplied_gap_case, unsupplied_gap_case

APPROVE = auto_approver("test-reviewer")


def _run(case, approver=APPROVE):
    order, _, label = case
    return run_case(label.case_id, order, approver=approver)


def _tools_called(case_id, run_id):
    return [e["payload"]["tool"] for e in audit.read_events(case_id, run_id=run_id)
            if e["event_type"] == "decision" and e["payload"].get("event") == "step"]


def _planner_override(choose):
    """Fake model: `choose(request)` answers planning turns (None = defer to the stub)."""
    def caller(request):
        if "<case_state>" in str(request["messages"]):
            answer = choose(request)
            if answer is not None:
                name, args = answer
                return {"content": [{"type": "tool_use", "id": "p", "name": name, "input": args}],
                        "stop_reason": "tool_use", "model": "fake", "usage": {}}
        return stub_llm.respond(request)
    return caller


def test_clean_case_runs_to_approval():
    state, run_id = _run(clean_case())
    assert state.status is Status.approved
    assert _tools_called(state.case_id, run_id) == [
        "get_patient_record", "check_criteria", "draft_letter", "submit_request", "check_status"]


def test_gap_is_filled_by_the_clinic_then_approved():
    state, run_id = _run(supplied_gap_case())
    assert state.status is Status.approved
    assert state.loop_counts.gap_loops == 1
    tools = _tools_called(state.case_id, run_id)
    assert tools[:4] == ["get_patient_record", "check_criteria", "request_missing_info", "check_criteria"]


def test_unresolvable_gap_escalates():
    state, _ = _run(unsupplied_gap_case())
    assert state.status is Status.escalated
    assert state.submission_id is None
    assert "gaps" in state.escalation_reason


def test_tool_call_cap_escalates(monkeypatch):
    monkeypatch.setattr(llm, "stub_caller", _planner_override(
        lambda r: ("search_policy", {"payer_id": "payer_a", "procedure_code": "72148", "query": "therapy"})))
    state, _ = _run(clean_case())
    assert state.status is Status.escalated
    assert state.loop_counts.tool_calls == config.MAX_TOOL_CALLS
    assert "cap" in state.escalation_reason


def test_disallowed_tool_is_rejected_and_logged(monkeypatch):
    calls = []

    def submit_first(request):
        calls.append(1)
        return ("submit_request", {"case_id": "x"}) if len(calls) == 1 else None

    monkeypatch.setattr(llm, "stub_caller", _planner_override(submit_first))
    state, run_id = _run(clean_case())
    errors = [e for e in audit.read_events(state.case_id, run_id=run_id) if e["event_type"] == "error"]
    assert "not allowed" in errors[0]["payload"]["error"]
    assert state.status is Status.approved


def test_other_patients_record_is_refused(monkeypatch):
    monkeypatch.setattr(llm, "stub_caller", _planner_override(
        lambda r: ("get_patient_record", {"patient_id": "PD9999"})))
    state, run_id = _run(clean_case())
    errors = [e["payload"]["error"] for e in audit.read_events(state.case_id, run_id=run_id) if e["event_type"] == "error"]
    assert any("does not match the order" in e for e in errors)
    assert state.status is Status.escalated and state.submission_id is None


def test_runs_are_separated_in_the_audit_log():
    case = clean_case()
    _, first = _run(case)
    _, second = _run(case)
    assert first != second
    for run_id in (first, second):
        events = audit.read_events(case[2].case_id, run_id=run_id)
        assert events[0]["payload"]["event"] == "run_started"
        assert events[-1]["payload"]["event"] == "run_finished"


def test_allowed_tools_follow_state():
    state, _ = _run(clean_case())
    assert allowed_tools(state) == []
    assert set(TOOLS) == {"get_patient_record", "search_policy", "check_criteria", "request_missing_info",
                          "draft_letter", "submit_request", "check_status", "draft_appeal", "escalate"}


def test_appeal_scenario_is_approved_after_appeal():
    state, run_id = _run(appeal_case())
    assert state.status is Status.approved
    assert state.loop_counts.appeals == 1 and len(state.submissions) == 2
    assert _tools_called(state.case_id, run_id)[-4:] == ["check_status", "draft_appeal", "submit_request", "check_status"]
