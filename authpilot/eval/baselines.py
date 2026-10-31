"""Baselines the agent is compared against. Both produce records shaped like the agent's, with
no final outcome (they have no loops, letters or submission).

- single_prompt: one model call with the full policy and the whole chart, no tools or loops.
  Its quotes go through the same verbatim check as the agent's.
- keyword: no model at all. A criterion is met when any of its keywords appears in a chart
  sentence; otherwise it is not met. It never says unclear.
"""

import re
import time

from pydantic import ValidationError

from authpilot import audit, config, ehr, llm
from authpilot.eval.harness import CaseRecord, new_record
from authpilot.evidence import check_citations
from authpilot.policies import find_policy
from authpilot.prompts import SINGLE_SYSTEM, SINGLE_TOOL, SingleAssessment, single_messages, tool_spec
from authpilot.schemas import CaseLabel, Chart, Order
from authpilot.stub_llm import _anchors, _sentences


def _criteria_sections(policy) -> list:
    return [s for s in policy.sections if re.fullmatch(r"\d+\.\d+", s.ref) and "criteria" in s.heading.lower()]


def _base_chart(order: Order, chart: Chart | None) -> Chart:
    ehr.clear_patient(order.patient_id)
    return chart or ehr.load_chart(order.patient_id)


def single_prompt_case(order: Order, label: CaseLabel, chart: Chart | None = None, run: int = 0) -> CaseRecord:
    record = new_record(label, "single_prompt", run)
    chart = _base_chart(order, chart)
    policy = find_policy(order.payer_id, order.procedure_code)
    started = time.perf_counter()
    try:
        response = llm.complete(
            single_messages(policy, chart, order.request_date, f"{order.procedure_code} {order.procedure_name}"),
            tools=[tool_spec(SINGLE_TOOL)], model=config.AGENT_MODEL, system=SINGLE_SYSTEM,
            tool_choice={"type": "tool", "name": SINGLE_TOOL}, case_id=label.case_id, purpose="single_prompt",
            max_tokens=4096,
        )
    except llm.LLMError as exc:
        record.error = f"{type(exc).__name__}: {exc}"
        record.predicted_ready = False
        return record
    record.latency_ms = round((time.perf_counter() - started) * 1000, 2)
    record.input_tokens = response.usage.get("input_tokens", 0)
    record.output_tokens = response.usage.get("output_tokens", 0)
    record.check_attempts = 1
    try:
        parsed = SingleAssessment.model_validate(response.tool_input(SINGLE_TOOL) or {})
    except ValidationError as exc:
        record.invalid_outputs = 1
        record.error = f"invalid output: {str(exc).splitlines()[0]}"
        record.predicted_ready = False
        audit.log_event(label.case_id, "eval", "error", {"baseline": "single_prompt", "error": record.error})
        return record
    for item in parsed.results:
        check = check_citations(chart, [q.model_dump() for q in item.evidence])
        status = item.status
        if status == "met" and not check.valid:
            status = "unclear"
        record.predicted[item.section_ref] = status
        record.confidence[item.section_ref] = item.confidence
        record.cited[item.section_ref] = [[e.doc_id, e.start, e.end] for e in check.valid]
        record.citations_total += check.total
        record.citations_invalid += len(check.invalid)
    record.predicted_ready = (set(record.expected) <= set(record.predicted)
                              and all(s == "met" for s in record.predicted.values()))
    return record


def keyword_case(order: Order, label: CaseLabel, chart: Chart | None = None, run: int = 0) -> CaseRecord:
    record = new_record(label, "keyword", run)
    chart = _base_chart(order, chart)
    policy = find_policy(order.payer_id, order.procedure_code)
    started = time.perf_counter()
    sentences = list(_sentences(chart))
    for section in _criteria_sections(policy):
        anchors = _anchors(section.text)
        match = next(((doc_id, s) for doc_id, s in sentences
                      if any(re.search(r"\b" + re.escape(a) + r"\b", s.lower()) for a in anchors)), None)
        record.predicted[section.ref] = "met" if match else "not_met"
        record.confidence[section.ref] = 1.0
        if match:
            check = check_citations(chart, [{"doc_id": match[0], "quote": match[1]}])
            record.cited[section.ref] = [[e.doc_id, e.start, e.end] for e in check.valid]
            record.citations_total += check.total
            record.citations_invalid += len(check.invalid)
    record.latency_ms = round((time.perf_counter() - started) * 1000, 2)
    record.predicted_ready = (set(record.expected) <= set(record.predicted)
                              and all(s == "met" for s in record.predicted.values()))
    return record


def run_baseline(name: str, cases: list) -> list[dict]:
    fn = {"single_prompt": single_prompt_case, "keyword": keyword_case}[name]
    return [fn(order, label, chart).to_dict() for order, chart, label in cases]
