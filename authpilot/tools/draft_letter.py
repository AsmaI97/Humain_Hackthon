"""draft_letter: a medical-necessity letter in which every clinical statement maps to chart spans.

The model proposes statements with quotes. Code accepts a statement only if
1) it is about a criterion that is met,
2) at least one cited quote is a verbatim substring of the chart, and
3) every number in the statement appears in its accepted quotes.
A met criterion with no accepted statement gets a plain quotation written by code instead.
"""

import re
from dataclasses import dataclass, field

from pydantic import ValidationError

from authpilot import audit, config, ehr, fallback, i18n, store
from authpilot.evidence import check_citations
from authpilot.gaps import criterion_name
from authpilot.policies import find_policy
from authpilot.prompts import LETTER_SYSTEM, LETTER_TOOL, LetterDraft, letter_messages, retry_messages, tool_spec
from authpilot.schemas import CaseState, Chart, Criterion, CriterionResult, LetterStatement, Order, Status, Strict
from authpilot.tools._common import log_call, log_result, refuse
from authpilot.tools._common import tool_spec as make_tool_spec
from authpilot.tools.check_criteria import load_criteria

_NUMBER = re.compile(r"\d+(?:\.\d+)?")


class DraftLetterInput(Strict):
    case_id: str


@dataclass
class LetterReport:
    proposed: int = 0
    accepted: int = 0
    dropped: list[dict] = field(default_factory=list)
    fallbacks: int = 0


def unsupported_numbers(text: str, quotes: list[str], ignore: set[str]) -> list[str]:
    allowed = {n for q in quotes for n in _NUMBER.findall(q)} | ignore
    return [n for n in _NUMBER.findall(text) if n not in allowed]


def request_statements(case_id: str, purpose: str, messages: list[dict], system: str, tool: str) -> LetterDraft | None:
    for _ in range(config.MAX_INVALID_OUTPUT_RETRIES + 1):
        response = fallback.complete(messages=messages, tools=[tool_spec(tool)], model=config.AGENT_MODEL,
                                     system=system, tool_choice={"type": "tool", "name": tool},
                                     case_id=case_id, purpose=purpose)
        try:
            return LetterDraft.model_validate(response.tool_input(tool) or {})
        except ValidationError as exc:
            audit.log_event(case_id, "agent", "error", {"stage": purpose, "error": str(exc)[:500]})
            messages = messages + retry_messages(response.content, tool, str(exc)[:500])
    fallback.log(case_id, "invalid_output_exhausted", stage=purpose)
    return None


def verify_statements(draft: LetterDraft | None, met: dict[str, CriterionResult], criteria: dict[str, Criterion],
                      chart: Chart, order: Order, report: LetterReport) -> list[LetterStatement]:
    """Keep only faithful statements; fill every met criterion without one with a plain quotation."""
    accepted: dict[str, LetterStatement] = {}
    for statement in (draft.statements if draft else []):
        report.proposed += 1
        reason = None
        check = None
        if statement.criterion_id not in met:
            reason = "criterion is not met or unknown"
        else:
            check = check_citations(chart, [q.model_dump() for q in statement.quotes])
            ignore = {criteria[statement.criterion_id].section_ref, order.procedure_code}
            if not check.valid:
                reason = "no cited quote is verbatim in the chart"
            elif bad := unsupported_numbers(statement.text, [e.span_text for e in check.valid], ignore):
                reason = f"numbers not in cited quotes: {bad}"
            elif statement.criterion_id in accepted:
                reason = "duplicate statement for criterion"
        if reason:
            report.dropped.append({"criterion_id": statement.criterion_id, "text": statement.text, "reason": reason})
            continue
        accepted[statement.criterion_id] = LetterStatement(criterion_id=statement.criterion_id,
                                                           text=statement.text.strip(), evidence=check.valid)
        report.accepted += 1

    statements = []
    for cid, result in met.items():
        if cid not in accepted:
            report.fallbacks += 1
            span = result.evidence[0]
            accepted[cid] = LetterStatement(
                criterion_id=cid, text=f'{criterion_name(criteria[cid])}: the record states "{span.span_text}"',
                evidence=[span],
            )
        statements.append(accepted[cid])
    return statements


def _render(state: CaseState, policy_id: str, statements: list[LetterStatement]) -> str:
    order = state.order
    lines = [
        f"Date: {order.request_date.isoformat()}",
        f"To: {order.payer_id} Utilization Management",
        f"Re: Prior authorization request for {order.procedure_name} ({order.procedure_code})",
        f"Patient: {order.patient_id}    Order: {order.order_id}",
        f"Ordering provider: {order.ordering_provider}",
        "",
        f"We request authorization of {order.procedure_name} under policy {policy_id}. "
        "The patient's record documents each coverage criterion as follows:",
        "",
    ]
    for i, statement in enumerate(statements, 1):
        sources = ", ".join(sorted({e.doc_id for e in statement.evidence}))
        lines.append(f"{i}. {statement.text} [source: {sources}]")
    lines += [
        "",
        "Each statement above is supported by the cited records, which are attached.",
        "",
        "Sincerely,",
        f"{order.ordering_provider} (draft prepared by AuthPilot for staff review)",
    ]
    return "\n".join(lines)


def draft_letter(case_id: str, report: LetterReport | None = None) -> str:
    log_call(case_id, "draft_letter", {"case_id": case_id})
    report = report if report is not None else LetterReport()
    state = store.get_case(case_id)
    if not state.results:
        raise refuse(case_id, "draft_letter", "criteria have not been checked")
    if state.gaps or any(r.status != "met" for r in state.results):
        raise refuse(case_id, "draft_letter", "not every criterion is met")
    if state.submission_id is not None:
        raise refuse(case_id, "draft_letter", "the request was already submitted")

    order = state.order
    chart = ehr.load_chart(order.patient_id)
    policy = find_policy(order.payer_id, order.procedure_code)
    criteria = {c.id: c for c in load_criteria(policy, case_id=case_id)}
    met = {r.criterion_id: r for r in state.results}
    items = [(criteria[cid], criterion_name(criteria[cid]), met[cid].evidence) for cid in met]
    messages = letter_messages(f"{order.procedure_code} {order.procedure_name}", order.request_date, items)
    draft = request_statements(case_id, "draft_letter", messages, LETTER_SYSTEM, LETTER_TOOL)
    statements = verify_statements(draft, met, criteria, chart, order, report)

    state.letter_statements = statements
    state.letter = _render(state, policy.policy_id, statements)
    state.letter_ar = (i18n.render_letter_ar(state, policy.policy_id, statements,
                                             {cid: criterion_name(c) for cid, c in criteria.items()})
                       if "ar" in config.LETTER_LANGUAGES else None)
    state.approval = None
    state.status = Status.ready_for_approval
    store.save_case(state)
    log_result(case_id, "draft_letter", {
        "proposed": report.proposed, "accepted": report.accepted, "fallbacks": report.fallbacks,
        "dropped": report.dropped, "letter": state.letter, "languages": config.LETTER_LANGUAGES,
    })
    return state.letter


TOOL_SPEC = make_tool_spec(
    "draft_letter",
    "Draft the medical-necessity letter from the verified evidence. Only allowed when every criterion is met.",
    DraftLetterInput,
)
