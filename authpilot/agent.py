"""The agent loop: plain Python with Claude tool use.

Each turn the model sees a compact summary of the case state (not the conversation history)
and must call exactly one tool. Code decides which tools are allowed in the current state,
validates the call, runs it, and logs everything.

The loop stops when the case is final (approved, denied with no appeals left, escalated),
when it is queued because a dependency is down, or at the human approval gate. With an
approver callback the gate is resolved in-process (CLI and evaluation); otherwise the case
waits for a person and resume_case() continues it.
"""

import json
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from authpilot import audit, config, ehr, fallback, gate, llm, store
from authpilot.payer_client import PayerError
from authpilot.schemas import CaseState, Order, Status
from authpilot.tools import (
    check_criteria, check_status, draft_appeal, draft_letter, escalate, get_patient_record,
    request_missing_info, search_policy, submit_request,
)
from authpilot.tools._common import ToolRefused

AGENT_SYSTEM = (
    "You are AuthPilot. You own one prior authorization request from the physician's order to the "
    "payer's decision. Each turn you get the current case state and must call exactly one tool from "
    "allowed_tools.\n"
    "How to work:\n"
    "- Fetch the patient record, then check every policy criterion.\n"
    "- If criteria are not met, request the missing documentation from the clinic, then re-check "
    "the criteria when new documents arrive.\n"
    "- Draft the letter only when every criterion is met. A human must approve it before you submit.\n"
    "- After submitting, check the status. If denied, draft an appeal that addresses the denial "
    "reason, which a human approves before you submit it.\n"
    "- Escalate to a human when gaps cannot be resolved or something looks wrong. Never guess."
)

TERMINAL = {Status.approved, Status.escalated}

Approver = Callable[[CaseState, str], tuple[bool, str]]


@dataclass(frozen=True)
class Tool:
    spec: dict
    input_model: type[BaseModel]
    run: Callable[[CaseState, Any], dict]


def _run_get_patient_record(state: CaseState, args) -> dict:
    if args.patient_id != state.order.patient_id:
        raise ToolRefused("get_patient_record: patient_id does not match the order")
    record = get_patient_record.get_patient_record(args.patient_id, case_id=state.case_id)
    state = store.get_case(state.case_id)
    state.record_doc_ids = [d.doc_id for d in record.documents]
    store.save_case(state)
    return {"documents": state.record_doc_ids}


def _run_search_policy(state: CaseState, args) -> dict:
    hits = search_policy.search_policy(args.payer_id, args.procedure_code, args.query, args.k, case_id=state.case_id)
    return {"sections": [h.ref for h in hits]}


def _run_check_criteria(state: CaseState, args) -> dict:
    diagnostics: list = []
    try:
        results = check_criteria.check_criteria(state.case_id, diagnostics=diagnostics)
    except check_criteria.CriteriaExtractionError as exc:
        fallback.log(state.case_id, "criteria_extraction_escalate", error=str(exc)[:300])
        raise fallback.EscalationRequired(f"could not read the policy's criteria: {exc}") from exc
    reason = fallback.review_results(state.case_id, results, diagnostics)
    if reason:
        raise fallback.EscalationRequired(reason)
    return {"statuses": {r.criterion_id: r.status for r in results}}


def _run_request_missing_info(state: CaseState, args) -> dict:
    request = request_missing_info.request_missing_info(state.case_id)
    return {"request_id": request.request_id, "new_documents": request.new_doc_ids}


def _run_draft_letter(state: CaseState, args) -> dict:
    draft_letter.draft_letter(state.case_id)
    return {"letter_statements": len(store.get_case(state.case_id).letter_statements)}


def _run_submit_request(state: CaseState, args) -> dict:
    return {"submission_id": submit_request.submit_request(state.case_id)}


def _run_check_status(state: CaseState, args) -> dict:
    decision = check_status.check_status(state.case_id)
    return {"payer_status": decision.status, "reason_code": decision.reason_code}


def _run_draft_appeal(state: CaseState, args) -> dict:
    draft_appeal.draft_appeal(state.case_id, args.denial_reason)
    return {"appeal_number": store.get_case(state.case_id).loop_counts.appeals}


def _run_escalate(state: CaseState, args) -> dict:
    escalate.escalate(state.case_id, args.reason)
    return {"status": "escalated"}


TOOLS: dict[str, Tool] = {
    "get_patient_record": Tool(get_patient_record.TOOL_SPEC, get_patient_record.GetPatientRecordInput, _run_get_patient_record),
    "search_policy": Tool(search_policy.TOOL_SPEC, search_policy.SearchPolicyInput, _run_search_policy),
    "check_criteria": Tool(check_criteria.TOOL_SPEC, check_criteria.CheckCriteriaInput, _run_check_criteria),
    "request_missing_info": Tool(request_missing_info.TOOL_SPEC, request_missing_info.RequestMissingInfoInput,
                                 _run_request_missing_info),
    "draft_letter": Tool(draft_letter.TOOL_SPEC, draft_letter.DraftLetterInput, _run_draft_letter),
    "submit_request": Tool(submit_request.TOOL_SPEC, submit_request.SubmitRequestInput, _run_submit_request),
    "check_status": Tool(check_status.TOOL_SPEC, check_status.CheckStatusInput, _run_check_status),
    "draft_appeal": Tool(draft_appeal.TOOL_SPEC, draft_appeal.DraftAppealInput, _run_draft_appeal),
    "escalate": Tool(escalate.TOOL_SPEC, escalate.EscalateInput, _run_escalate),
}


def is_final(state: CaseState) -> bool:
    return state.status in TERMINAL


def allowed_tools(state: CaseState) -> list[str]:
    if is_final(state) or state.queued_reason or gate.awaiting_approval(state):
        return []
    if state.status is Status.submitted:
        return ["check_status", "escalate"]
    if state.status is Status.denied:
        return ["draft_appeal", "escalate"]
    if state.status is Status.appealing:
        return ["submit_request", "escalate"]
    allowed = ["get_patient_record", "search_policy", "check_criteria"]
    if state.gaps and state.loop_counts.gap_loops < config.MAX_GAP_LOOPS:
        allowed.append("request_missing_info")
    if state.results and not state.gaps and state.submission_id is None:
        allowed.append("draft_letter")
    if state.status is Status.ready_for_approval and gate.approval_valid(state, "initial"):
        allowed.append("submit_request")
    return allowed + ["escalate"]


def summarize(state: CaseState, last_result: dict | None, last_error: str | None) -> dict:
    new_docs = sorted({d for r in state.info_requests for d in r.new_doc_ids} - set(state.checked_doc_ids))
    last_request = state.info_requests[-1] if state.info_requests else None
    return {
        "case_id": state.case_id,
        "patient_id": state.order.patient_id,
        "payer_id": state.order.payer_id,
        "procedure": f"{state.order.procedure_code} {state.order.procedure_name}",
        "request_date": state.order.request_date.isoformat(),
        "status": state.status.value,
        "record_fetched": bool(state.record_doc_ids),
        "criteria_checked": bool(state.results),
        "criteria": [{"criterion_id": r.criterion_id, "status": r.status, "confidence": r.confidence}
                     for r in state.results],
        "gaps": [g.model_dump() for g in state.gaps],
        "new_documents_since_check": new_docs,
        "gap_loops": state.loop_counts.gap_loops,
        "max_gap_loops": config.MAX_GAP_LOOPS,
        "last_info_request": {"request_id": last_request.request_id,
                              "new_documents": len(last_request.new_doc_ids)} if last_request else None,
        "letter_drafted": bool(state.letter),
        "approved_by_human": bool(state.approval),
        "submitted": state.submission_id is not None,
        "payer_status": state.payer_status,
        "denial_reason": state.denial_reason,
        "appeals": state.loop_counts.appeals,
        "max_appeals": config.MAX_APPEALS,
        "tool_calls": state.loop_counts.tool_calls,
        "max_tool_calls": config.MAX_TOOL_CALLS,
        "allowed_tools": allowed_tools(state),
        "last_result": last_result,
        "last_error": last_error,
    }


def _plan(state: CaseState, summary: dict) -> llm.LLMResponse:
    content = (f"<case_state>{json.dumps(summary, sort_keys=True)}</case_state>\n"
               "Choose the next action by calling exactly one tool.")
    return fallback.complete(
        messages=[{"role": "user", "content": content}],
        tools=[TOOLS[name].spec for name in summary["allowed_tools"]],
        model=config.AGENT_MODEL, system=AGENT_SYSTEM, tool_choice={"type": "any"},
        case_id=state.case_id, purpose="plan",
    )


def _first_tool_call(response: llm.LLMResponse) -> dict | None:
    return next((b for b in response.content if b.get("type") == "tool_use"), None)


def _step(case_id: str, state: CaseState) -> None:
    """One planning turn: ask the model for a tool call, check it, run it, log it."""
    summary = summarize(state, state_last_result.get(case_id), state_last_error.get(case_id))
    response = _plan(state, summary)
    state.loop_counts.tool_calls += 1
    store.save_case(state)
    call = _first_tool_call(response)
    last_result, last_error = None, None
    if call is None:
        last_error = "no tool was called"
    elif call["name"] not in summary["allowed_tools"]:
        last_error = f"{call['name']} is not allowed in status {state.status.value}"
    else:
        tool = TOOLS[call["name"]]
        try:
            args = tool.input_model.model_validate(call.get("input") or {})
            if getattr(args, "case_id", case_id) != case_id:
                raise ToolRefused(f"{call['name']}: case_id does not match this case")
            last_result = {"tool": call["name"], **tool.run(state, args)}
        except ValidationError as exc:
            last_error = f"invalid input for {call['name']}: {str(exc).splitlines()[0]}"
        except ToolRefused as exc:
            last_error = str(exc)
        except PayerError as exc:
            last_error = f"payer error: {exc}"
    state_last_result[case_id], state_last_error[case_id] = last_result, last_error
    if last_error:
        audit.log_event(case_id, "agent", "error", {"step": state.loop_counts.tool_calls, "error": last_error})
    else:
        audit.log_event(case_id, "agent", "decision", {
            "event": "step", "step": state.loop_counts.tool_calls, "tool": call["name"],
            "result": last_result, "status_after": store.get_case(case_id).status.value,
        })


state_last_result: dict[str, dict | None] = {}
state_last_error: dict[str, str | None] = {}


def _drive(case_id: str, approver: Approver | None) -> CaseState:
    while True:
        state = store.get_case(case_id)
        if is_final(state) or state.queued_reason:
            break
        kind = gate.awaiting_approval(state)
        if kind:
            if approver is None:
                audit.log_event(case_id, "agent", "decision", {"event": "awaiting_approval", "kind": kind})
                break
            ok, reviewer_or_reason = approver(state, kind)
            if ok:
                gate.approve(case_id, reviewer_or_reason)
            else:
                gate.reject(case_id, "reviewer", reviewer_or_reason)
            continue
        if state.status is Status.denied and state.loop_counts.appeals >= config.MAX_APPEALS:
            fallback.log(case_id, "appeal_cap", cap=config.MAX_APPEALS)
            escalate.escalate(case_id, f"denied after {config.MAX_APPEALS} appeals: {state.denial_reason}")
            break
        if state.loop_counts.tool_calls >= config.MAX_TOOL_CALLS:
            fallback.log(case_id, "tool_call_cap", cap=config.MAX_TOOL_CALLS)
            escalate.escalate(case_id, f"tool call cap of {config.MAX_TOOL_CALLS} reached")
            break
        try:
            _step(case_id, state)
        except fallback.CaseQueued as exc:
            fallback.queue_case(case_id, str(exc))
        except fallback.EscalationRequired as exc:
            escalate.escalate(case_id, str(exc))

    final = store.get_case(case_id)
    audit.log_event(case_id, "agent", "decision", {
        "event": "run_finished" if is_final(final) else "run_paused", "status": final.status.value,
        "tool_calls": final.loop_counts.tool_calls, "gap_loops": final.loop_counts.gap_loops,
        "appeals": final.loop_counts.appeals, "escalation_reason": final.escalation_reason,
        "denial_reason": final.denial_reason, "queued_reason": final.queued_reason,
        "awaiting_approval": gate.awaiting_approval(final),
    })
    return final


def run_case(case_id: str, order: Order, approver: Approver | None = None) -> tuple[CaseState, str]:
    """Start a case from intake. Returns the state where the loop stopped and the audit run id."""
    ehr.clear_patient(order.patient_id)
    store.create_case(case_id, order)
    state_last_result.pop(case_id, None)
    state_last_error.pop(case_id, None)
    run_id = audit.start_run()
    audit.log_event(case_id, "agent", "decision", {"event": "run_started", "order": order.model_dump(mode="json")})
    return _drive(case_id, approver), run_id


def resume_case(case_id: str, approver: Approver | None = None) -> tuple[CaseState, str]:
    """Continue a paused or queued case, e.g. after a human approval or when the payer is back."""
    state = store.get_case(case_id)
    if state.queued_reason:
        state.queued_reason = None
        store.save_case(state)
    run_id = audit.start_run()
    audit.log_event(case_id, "agent", "decision", {"event": "run_resumed", "status": state.status.value})
    return _drive(case_id, approver), run_id


def auto_approver(reviewer: str) -> Approver:
    """Approve every letter as the named reviewer. For the CLI demo and evaluation only."""
    return lambda state, kind: (True, reviewer)
