"""check_status: poll the payer for the decision on the current submission."""

from authpilot import fallback, payer_client, store
from authpilot.schemas import PayerDecision, Status, Strict
from authpilot.tools._common import log_call, log_result, refuse, tool_spec
from authpilot.tools.draft_appeal import parse_denied_section


class CheckStatusInput(Strict):
    case_id: str


def check_status(case_id: str) -> PayerDecision:
    log_call(case_id, "check_status", {"case_id": case_id})
    state = store.get_case(case_id)
    if state.submission_id is None or state.status is not Status.submitted:
        raise refuse(case_id, "check_status", "no submission is awaiting a decision")

    decision = fallback.with_payer_retries(case_id, "status", lambda: payer_client.status(state.submission_id))
    state.payer_status = decision.status
    if decision.status == "approved":
        state.status = Status.approved
    elif decision.status == "denied":
        state.status = Status.denied
        state.denial_code = decision.reason_code
        state.denial_reason = f"{decision.reason_code}: {decision.reason}"
        state.denial_ref = parse_denied_section(decision.reason)
    store.save_case(state)
    log_result(case_id, "check_status", decision.model_dump())
    return decision


TOOL_SPEC = tool_spec("check_status", "Get the payer's decision for the submitted request.", CheckStatusInput)
