"""request_missing_info: create a task and a message to the clinic for the open gaps.

Delivery is simulated: the message is appended to an outbox file (standing in for fax or email)
and the simulated clinic replies immediately with any documents it holds.
"""

import json
from pathlib import Path

from authpilot import clinic_sim, config, store
from authpilot.schemas import Gap, InfoRequest, Order, Status, Strict
from authpilot.tools._common import log_call, log_result, refuse, tool_spec


class RequestMissingInfoInput(Strict):
    case_id: str


def compose_message(order: Order, gaps: list[Gap]) -> str:
    lines = [
        f"To: {order.ordering_provider}",
        f"Re: Prior authorization for {order.procedure_name} ({order.procedure_code}), "
        f"patient {order.patient_id}, order {order.order_id}",
        "",
        "To complete this request we need documentation for the following:",
        *[f"- {gap.description}" for gap in gaps],
        "",
        "Please send the relevant notes or results. Prepared by AuthPilot for staff review.",
    ]
    return "\n".join(lines)


def _outbox_path() -> Path:
    return Path(config.RUNTIME_DIR) / "outbox.jsonl"


def request_missing_info(case_id: str) -> InfoRequest:
    log_call(case_id, "request_missing_info", {"case_id": case_id})
    state = store.get_case(case_id)
    if not state.gaps:
        raise refuse(case_id, "request_missing_info", "no open gaps")
    if state.loop_counts.gap_loops >= config.MAX_GAP_LOOPS:
        raise refuse(case_id, "request_missing_info", f"gap loop cap of {config.MAX_GAP_LOOPS} reached")

    request = InfoRequest(
        request_id=f"{case_id}-info-{len(state.info_requests) + 1}",
        gaps=list(state.gaps),
        message=compose_message(state.order, state.gaps),
    )
    outbox = _outbox_path()
    outbox.parent.mkdir(parents=True, exist_ok=True)
    with outbox.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"request_id": request.request_id, "case_id": case_id,
                             "to": state.order.ordering_provider, "message": request.message}) + "\n")

    new_docs = clinic_sim.respond(state.order.patient_id, state.gaps)
    request.new_doc_ids = list(new_docs)
    state.info_requests.append(request)
    state.loop_counts.gap_loops += 1
    state.status = Status.needs_evidence
    store.save_case(state)
    log_result(case_id, "request_missing_info", {
        "request_id": request.request_id, "gaps": [g.criterion_id for g in request.gaps],
        "message": request.message, "new_doc_ids": request.new_doc_ids,
    })
    return request


TOOL_SPEC = tool_spec(
    "request_missing_info",
    "Send the clinic a request for documentation covering every open gap. "
    "Any documents the clinic sends are added to the patient record.",
    RequestMissingInfoInput,
)
