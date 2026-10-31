"""check_criteria: assess every policy criterion for a case with cited, code-verified evidence."""

from dataclasses import dataclass, field

from pydantic import ValidationError

from authpilot import audit, config, fallback, store
from authpilot.evidence import check_citations, unchecked_evidence
from authpilot.gaps import detect_gaps
from authpilot.policies import Policy, PolicySection, find_policy
from authpilot.prompts import (
    CHECK_SYSTEM, CHECK_TOOL, EXTRACT_SYSTEM, EXTRACT_TOOL, CriteriaExtraction, CriterionAssessment,
    check_messages, extraction_messages, retry_messages, tool_spec,
)
from authpilot.schemas import Chart, Criterion, CriterionResult, Status, Strict
from authpilot.tools._common import log_call, log_result
from authpilot.tools._common import tool_spec as make_tool_spec
from authpilot.tools.get_patient_record import get_patient_record
from authpilot.tools.search_policy import search_policy


class CheckCriteriaInput(Strict):
    case_id: str


class CriteriaExtractionError(Exception):
    pass


@dataclass
class CriterionDiagnostics:
    criterion_id: str
    section_ref: str
    attempts: int = 0
    invalid_outputs: int = 0
    citations_total: int = 0
    citations_invalid: int = 0
    downgraded: bool = False
    retrieved_refs: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0


# Criteria extraction ------------------------------------------------------------------------

_criteria_cache: dict[tuple, list[Criterion]] = {}


def _validate_extraction(policy: Policy, raw: dict | None) -> CriteriaExtraction:
    if raw is None:
        raise ValueError(f"no {EXTRACT_TOOL} tool call in the response")
    parsed = CriteriaExtraction.model_validate(raw)
    refs = [c.section_ref for c in parsed.criteria]
    unknown = [r for r in refs if policy.section(r) is None]
    if unknown:
        raise ValueError(f"section_ref not in policy: {unknown}")
    if len(set(refs)) != len(refs):
        raise ValueError("duplicate section_ref")
    return parsed


def load_criteria(policy: Policy, case_id: str = "-") -> list[Criterion]:
    """Ask the cheap model which sections are criteria. Criterion text always comes from the
    policy itself, never from the model."""
    key = (policy.policy_id, policy.meta.get("version"), config.LLM_MODE, config.CHEAP_MODEL)
    if key in _criteria_cache:
        return _criteria_cache[key]
    messages = extraction_messages(policy)
    last_error = ""
    for _ in range(config.MAX_INVALID_OUTPUT_RETRIES + 1):
        response = fallback.complete(
            messages=messages, tools=[tool_spec(EXTRACT_TOOL)], model=config.CHEAP_MODEL, system=EXTRACT_SYSTEM,
            tool_choice={"type": "tool", "name": EXTRACT_TOOL}, case_id=case_id, purpose="extract_criteria",
        )
        try:
            parsed = _validate_extraction(policy, response.tool_input(EXTRACT_TOOL))
        except (ValidationError, ValueError) as exc:
            last_error = str(exc).splitlines()[0]
            audit.log_event(case_id, "agent", "error", {"stage": "extract_criteria", "error": last_error})
            messages = messages + retry_messages(response.content, EXTRACT_TOOL, last_error)
            continue
        criteria = [
            Criterion(id=f"{policy.policy_id}:{c.section_ref}", section_ref=c.section_ref,
                      text=policy.section(c.section_ref).text)
            for c in parsed.criteria
        ]
        _criteria_cache[key] = criteria
        return criteria
    raise CriteriaExtractionError(f"criteria extraction failed for {policy.policy_id}: {last_error}")


def clear_criteria_cache() -> None:
    _criteria_cache.clear()


# Criterion assessment ---------------------------------------------------------------------


def _policy_context(policy: Policy, payer_id: str, procedure_code: str, criterion: Criterion,
                    use_retrieval: bool, case_id: str) -> list[PolicySection]:
    if not use_retrieval:
        return list(policy.sections)
    return fallback.policy_context(policy, payer_id, procedure_code, criterion, case_id, search=search_policy)


def _finalize(criterion: Criterion, assessment: CriterionAssessment, chart: Chart, verify_citations: bool,
              diag: CriterionDiagnostics, case_id: str) -> CriterionResult:
    quotes = [q.model_dump() for q in assessment.evidence]
    status, confidence, reasoning = assessment.status, assessment.confidence, assessment.reasoning
    if verify_citations:
        check = check_citations(chart, quotes)
        evidence = check.valid
        diag.citations_total, diag.citations_invalid = check.total, len(check.invalid)
        new_status, confidence, reasoning = fallback.evidence_not_found(
            case_id, criterion.id, status, confidence, reasoning, bool(evidence), check.invalid)
        diag.downgraded = new_status != status
        status = new_status
    else:
        evidence = unchecked_evidence(chart, quotes)
        diag.citations_total = len(evidence)
        diag.citations_invalid = sum(not e.verify(chart) for e in evidence)
    return CriterionResult(criterion_id=criterion.id, status=status, evidence=evidence,
                           reasoning=reasoning, confidence=confidence)


def assess_criterion(criterion: Criterion, context: list[PolicySection], chart: Chart, request_date,
                     procedure: str, case_id: str, verify_citations: bool = True,
                     model: str | None = None) -> tuple[CriterionResult, CriterionDiagnostics]:
    diag = CriterionDiagnostics(criterion.id, criterion.section_ref, retrieved_refs=[s.ref for s in context])
    messages = check_messages(criterion, context, chart, request_date, procedure)
    last_error = ""
    for _ in range(config.MAX_INVALID_OUTPUT_RETRIES + 1):
        diag.attempts += 1
        response = fallback.complete(
            messages=messages, tools=[tool_spec(CHECK_TOOL)], model=model or config.AGENT_MODEL, system=CHECK_SYSTEM,
            tool_choice={"type": "tool", "name": CHECK_TOOL}, case_id=case_id, purpose=f"check:{criterion.id}",
        )
        diag.input_tokens += response.usage.get("input_tokens", 0)
        diag.output_tokens += response.usage.get("output_tokens", 0)
        diag.latency_ms += response.latency_ms
        raw = response.tool_input(CHECK_TOOL)
        try:
            if raw is None:
                raise ValueError(f"no {CHECK_TOOL} tool call in the response")
            assessment = CriterionAssessment.model_validate(raw)
        except (ValidationError, ValueError) as exc:
            diag.invalid_outputs += 1
            if isinstance(exc, ValidationError):
                bits = []
                for err in exc.errors():
                    loc = ".".join(str(part) for part in err.get("loc") or ())
                    msg = err.get("msg") or "invalid"
                    bits.append(f"{loc}: {msg}" if loc else str(msg))
                last_error = "; ".join(bits) or str(exc).splitlines()[0]
            else:
                last_error = str(exc).splitlines()[0]
            audit.log_event(case_id, "agent", "error", {"stage": "check_criterion", "criterion_id": criterion.id,
                                                         "error": last_error[:500]})
            messages = messages + retry_messages(response.content, CHECK_TOOL, last_error[:500])
            continue
        return _finalize(criterion, assessment, chart, verify_citations, diag, case_id), diag

    fallback.log(case_id, "invalid_output_exhausted", criterion_id=criterion.id, error=last_error[:300])
    result = CriterionResult(criterion_id=criterion.id, status="unclear", evidence=[], confidence=0.0,
                             reasoning=fallback.INVALID_OUTPUT_REASONING)
    return result, diag


def check_criteria(case_id: str, *, use_retrieval: bool | None = None, verify_citations: bool | None = None,
                   diagnostics: list[CriterionDiagnostics] | None = None) -> list[CriterionResult]:
    use_retrieval = config.USE_RETRIEVAL if use_retrieval is None else use_retrieval
    verify_citations = config.VERIFY_CITATIONS if verify_citations is None else verify_citations
    log_call(case_id, "check_criteria", {"case_id": case_id, "use_retrieval": use_retrieval,
                                         "verify_citations": verify_citations})
    state = store.get_case(case_id)
    order = state.order
    state.status = Status.checking
    store.save_case(state)

    chart = get_patient_record(order.patient_id, case_id=case_id).as_chart()
    policy = find_policy(order.payer_id, order.procedure_code)
    criteria = load_criteria(policy, case_id=case_id)
    procedure = f"{order.procedure_code} {order.procedure_name}"

    results = []
    for criterion in criteria:
        context = _policy_context(policy, order.payer_id, order.procedure_code, criterion, use_retrieval, case_id)
        result, diag = assess_criterion(criterion, context, chart, order.request_date, procedure, case_id,
                                        verify_citations=verify_citations)
        results.append(result)
        if diagnostics is not None:
            diagnostics.append(diag)
        audit.log_event(case_id, "agent", "decision", {
            "criterion_id": result.criterion_id, "status": result.status, "confidence": result.confidence,
            "evidence": [e.model_dump() for e in result.evidence], "reasoning": result.reasoning,
            "citations_total": diag.citations_total, "citations_invalid": diag.citations_invalid,
            "downgraded": diag.downgraded, "section_ref": criterion.section_ref,
            "attempts": diag.attempts, "invalid_outputs": diag.invalid_outputs,
        })

    state.results = results
    state.gaps = detect_gaps(criteria, results)
    state.checked_doc_ids = list(chart)
    state.status = Status.needs_evidence if state.gaps else Status.checking
    store.save_case(state)
    log_result(case_id, "check_criteria", {
        "statuses": {r.criterion_id: r.status for r in results},
        "gaps": [g.criterion_id for g in state.gaps],
    })
    return results


TOOL_SPEC = make_tool_spec(
    "check_criteria",
    "Assess every coverage criterion of the payer policy against the patient's chart. "
    "Returns one result per criterion with verified evidence quotes.",
    CheckCriteriaInput,
)
