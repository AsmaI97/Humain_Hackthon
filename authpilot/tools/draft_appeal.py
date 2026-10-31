"""draft_appeal: an appeal that addresses the payer's denial reason with verified evidence.

The appeal covers the denied policy section only, and uses the same faithfulness checks as the
letter. If the record has no verified evidence for the denied section, the tool refuses and the
case must be escalated rather than appealed.
"""

import re

from pydantic import Field

from authpilot import config, ehr, i18n, store
from authpilot.gaps import criterion_name
from authpilot.policies import find_policy
from authpilot.prompts import APPEAL_SYSTEM, APPEAL_TOOL, appeal_messages
from authpilot.schemas import CaseState, LetterStatement, Status, Strict
from authpilot.tools._common import log_call, log_result, refuse, tool_spec
from authpilot.tools.check_criteria import load_criteria
from authpilot.tools.draft_letter import LetterReport, request_statements, verify_statements


class DraftAppealInput(Strict):
    case_id: str
    denial_reason: str = Field(min_length=1)


def _render(state: CaseState, statements: list[LetterStatement], attachments: list[str]) -> str:
    order = state.order
    lines = [
        f"Date: {order.request_date.isoformat()}",
        f"To: {order.payer_id} Appeals",
        f"Re: Appeal of submission {state.submission_id} for {order.procedure_name} ({order.procedure_code})",
        f"Patient: {order.patient_id}    Order: {order.order_id}",
        f"Denial: {state.denial_reason}",
        "",
        f"We appeal the denial with reason code {state.denial_code} for policy section {state.denial_ref}. "
        "The record documents this criterion as follows:",
        "",
    ]
    for i, statement in enumerate(statements, 1):
        sources = ", ".join(sorted({e.doc_id for e in statement.evidence}))
        lines.append(f"{i}. {statement.text} [source: {sources}]")
    lines += [
        "",
        f"The supporting records are attached: {', '.join(attachments)}. "
        "We request reconsideration under the policy's appeal provisions.",
        "",
        "Sincerely,",
        f"{order.ordering_provider} (draft prepared by AuthPilot for staff review)",
    ]
    return "\n".join(lines)


def draft_appeal(case_id: str, denial_reason: str, report: LetterReport | None = None) -> str:
    log_call(case_id, "draft_appeal", {"case_id": case_id, "denial_reason": denial_reason})
    report = report if report is not None else LetterReport()
    state = store.get_case(case_id)
    if state.status is not Status.denied or not state.denial_code:
        raise refuse(case_id, "draft_appeal", "the case has no denial to appeal")
    if state.loop_counts.appeals >= config.MAX_APPEALS:
        raise refuse(case_id, "draft_appeal", f"appeal cap of {config.MAX_APPEALS} reached")
    if state.denial_code in state.appeal_codes:
        raise refuse(case_id, "draft_appeal", f"an appeal for {state.denial_code} was already denied")

    order = state.order
    policy = find_policy(order.payer_id, order.procedure_code)
    criteria = {c.id: c for c in load_criteria(policy, case_id=case_id)}
    denied = [r for r in state.results if r.criterion_id.split(":")[-1] == state.denial_ref]
    if not denied or denied[0].status != "met" or not denied[0].evidence:
        raise refuse(case_id, "draft_appeal", f"no verified evidence for denied section {state.denial_ref}")

    result = denied[0]
    chart = ehr.load_chart(order.patient_id)
    criterion = criteria[result.criterion_id]
    messages = appeal_messages(state.denial_code, state.denial_reason, f"{order.procedure_code} {order.procedure_name}",
                               order.request_date, [(criterion, criterion_name(criterion), result.evidence)])
    draft = request_statements(case_id, "draft_appeal", messages, APPEAL_SYSTEM, APPEAL_TOOL)
    statements = verify_statements(draft, {result.criterion_id: result}, criteria, chart, order, report)

    attachments = sorted({e.doc_id for s in statements for e in s.evidence})
    state.appeal_statements = statements
    state.appeal_letter = _render(state, statements, attachments)
    state.appeal_letter_ar = (i18n.render_appeal_ar(state, statements, {result.criterion_id: criterion_name(criterion)},
                                                    attachments)
                              if "ar" in config.LETTER_LANGUAGES else None)
    state.approval = None
    state.loop_counts.appeals += 1
    state.appeal_codes.append(state.denial_code)
    state.status = Status.appealing
    store.save_case(state)
    log_result(case_id, "draft_appeal", {
        "appeal_number": state.loop_counts.appeals, "denial_code": state.denial_code,
        "accepted": report.accepted, "fallbacks": report.fallbacks, "dropped": report.dropped,
        "appeal_letter": state.appeal_letter,
    })
    return state.appeal_letter


TOOL_SPEC = tool_spec(
    "draft_appeal",
    "Draft an appeal that addresses the payer's denial reason with verified evidence. Requires human approval before submission.",
    DraftAppealInput,
)


def parse_denied_section(reason: str | None) -> str | None:
    match = re.search(r"Section (\d+\.\d+)", reason or "")
    return match.group(1) if match else None
