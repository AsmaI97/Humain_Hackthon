"""submit_request: send the approved package to the payer.

Refuses unless a human approved the exact letter being sent. Handles the initial request and
appeals. Each submission has a fixed idempotency key, so retries after a payer outage can never
create a second submission.
"""

from authpilot import ehr, fallback, gate, payer_client, store
from authpilot.schemas import CaseState, Status, Strict, SubmissionPackage, SubmittedCriterion
from authpilot.tools._common import log_call, log_result, refuse, tool_spec


class SubmitRequestInput(Strict):
    case_id: str


def build_package(state: CaseState, idempotency_key: str, letter: str,
                  appeal_of: str | None = None, letter_ar: str | None = None) -> SubmissionPackage:
    chart = ehr.load_chart(state.order.patient_id)
    criteria = [
        SubmittedCriterion(section_ref=r.criterion_id.split(":")[-1], status=r.status, evidence=r.evidence)
        for r in state.results
    ]
    cited = sorted({e.doc_id for r in state.results for e in r.evidence if e.doc_id in chart})
    return SubmissionPackage(
        case_id=state.case_id, idempotency_key=idempotency_key, order=state.order, criteria=criteria,
        letter=letter, letter_ar=letter_ar, attachments={doc_id: chart[doc_id] for doc_id in cited},
        appeal_of=appeal_of,
    )


def submit_request(case_id: str) -> str:
    log_call(case_id, "submit_request", {"case_id": case_id})
    state = store.get_case(case_id)
    if state.status is Status.ready_for_approval:
        if state.submission_id is not None:
            raise refuse(case_id, "submit_request", f"already submitted as {state.submission_id}")
        if not state.letter or state.gaps:
            raise refuse(case_id, "submit_request", "package is not ready: needs a letter and no open gaps")
        kind, letter, key, appeal_of = "initial", state.letter, f"{case_id}:{state.request_id}:initial", None
    elif state.status is Status.appealing:
        kind, letter, appeal_of = "appeal", state.appeal_letter, state.submission_id
        key = f"{case_id}:{state.request_id}:appeal-{state.loop_counts.appeals}"
    else:
        raise refuse(case_id, "submit_request", f"nothing to submit in status {state.status.value}")
    if not gate.approval_valid(state, kind):
        raise refuse(case_id, "submit_request", f"human approval of the {kind} letter is required")

    letter_ar = state.letter_ar if kind == "initial" else state.appeal_letter_ar
    package = build_package(state, key, letter, appeal_of=appeal_of, letter_ar=letter_ar)
    try:
        decision = fallback.with_payer_retries(case_id, "submit", lambda: payer_client.submit(package))
    except fallback.CaseQueued:
        state.payer_status = "pending"
        store.save_case(state)
        raise

    state.submission_id = decision.submission_id
    if decision.submission_id not in state.submissions:
        state.submissions.append(decision.submission_id)
    state.payer_status = decision.status
    state.status = Status.submitted
    store.save_case(state)
    log_result(case_id, "submit_request", {
        "kind": kind, "submission_id": decision.submission_id, "payer_status": decision.status,
        "attachments": list(package.attachments), "idempotency_key": key, "appeal_of": appeal_of,
        "approved_by": state.approval.reviewer if state.approval else None,
    })
    return decision.submission_id


TOOL_SPEC = tool_spec(
    "submit_request",
    "Submit the human-approved package (initial request or appeal) to the payer.",
    SubmitRequestInput,
)
