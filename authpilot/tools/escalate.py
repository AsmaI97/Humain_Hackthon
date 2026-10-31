"""escalate: hand the case to a human with a reason. Always allowed on a non-final case."""

from pydantic import Field

from authpilot import audit, store
from authpilot.schemas import CaseState, Status, Strict
from authpilot.tools._common import log_call, log_result, tool_spec


class EscalateInput(Strict):
    case_id: str
    reason: str = Field(min_length=1, max_length=300)


def escalate(case_id: str, reason: str) -> CaseState:
    log_call(case_id, "escalate", {"case_id": case_id, "reason": reason})
    state = store.get_case(case_id)
    state.status = Status.escalated
    state.escalation_reason = reason
    store.save_case(state)
    audit.log_event(case_id, "agent", "decision", {"event": "escalated", "reason": reason})
    log_result(case_id, "escalate", {"status": state.status.value})
    return state


TOOL_SPEC = tool_spec(
    "escalate",
    "Stop and hand the case to a human reviewer, with the reason. Use when the agent cannot proceed safely.",
    EscalateInput,
)
