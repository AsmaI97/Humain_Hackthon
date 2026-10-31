"""Run cases through the real agent loop and turn each run into a flat record from the audit log.

A simulated reviewer approves every letter, so the gate never blocks evaluation. Labels are read
only here, after the run; the agent never sees them.
"""

import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from typing import Any, Iterator

from authpilot import audit, config, ehr, payer_client, store
from authpilot.agent import auto_approver, run_case
from authpilot.payer_mock import app as payer_app
from authpilot.schemas import CaseLabel, Chart, Order

READY_OUTCOMES = {"approve", "deny_then_appeal_approve"}


@dataclass
class CaseRecord:
    case_id: str
    split: str
    procedure: str
    tags: list[str]
    variant: str
    run: int
    expected: dict[str, str]
    predicted: dict[str, str] = field(default_factory=dict)
    confidence: dict[str, float] = field(default_factory=dict)
    cited: dict[str, list[list]] = field(default_factory=dict)
    expected_spans: dict[str, list[list]] = field(default_factory=dict)
    citations_total: int = 0
    citations_invalid: int = 0
    expected_ready: bool = False
    predicted_ready: bool | None = None
    expected_final: str | None = None
    final_status: str | None = None
    denied: bool = False
    appealed: bool = False
    letter_proposed: int = 0
    letter_accepted: int = 0
    letter_fallbacks: int = 0
    letter_statements: int = 0
    letter_statements_verified: int = 0
    tool_calls: int = 0
    gap_loops: int = 0
    appeals: int = 0
    submissions: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    check_attempts: int = 0
    invalid_outputs: int = 0
    escalation_reason: str | None = None
    queued: bool = False
    safe: bool = True
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def new_record(label: CaseLabel, variant: str, run: int) -> CaseRecord:
    return CaseRecord(
        case_id=label.case_id, split=label.split, procedure=label.procedure,
        tags=label.hard_case_tags or ["clean"], variant=variant, run=run,
        expected={c.section_ref: c.status for c in label.criteria},
        expected_spans={c.section_ref: [[e.doc_id, e.start, e.end] for e in c.evidence] for c in label.criteria},
        expected_ready=label.expected_outcome in READY_OUTCOMES,
        expected_final=label.expected_final,
    )


@contextmanager
def chart_override(patient_id: str, chart: Chart | None) -> Iterator[None]:
    if chart is not None:
        ehr.set_chart_override(patient_id, chart)
    try:
        yield
    finally:
        ehr.clear_chart_override(patient_id)
        ehr.clear_patient(patient_id)


def _initial_verdicts(events: list[dict]) -> list[dict]:
    """Verdicts from the first check_criteria call of the run (before any clinic documents)."""
    first, seen = [], set()
    for event in events:
        p = event["payload"]
        if event["event_type"] == "decision" and "criterion_id" in p:
            ref = p.get("section_ref") or p["criterion_id"].split(":")[-1]
            if ref in seen:
                break
            seen.add(ref)
            first.append(p)
    return first


def _submitted_packages_are_sound(state, chart: Chart) -> bool:
    for submission_id in state.submissions:
        package = payer_app._packages.get(submission_id)
        if package is None:
            return False
        for item in package.criteria:
            for evidence in item.evidence:
                if not evidence.verify(chart):
                    return False
    return len(set(state.submissions)) == len(state.submissions) == payer_app.submissions()["count"]


def run_agent_case(order: Order, label: CaseLabel, variant: str = "agent", run: int = 0,
                   chart: Chart | None = None) -> CaseRecord:
    record = new_record(label, variant, run)
    payer_client.reset()
    store.clear()
    started = time.perf_counter()
    with chart_override(order.patient_id, chart):
        try:
            state, run_id = run_case(label.case_id, order, approver=auto_approver("eval-reviewer"))
        except Exception as exc:  # an unexpected crash is recorded as an unsafe failure, never hidden
            record.error = f"{type(exc).__name__}: {exc}"
            record.safe = False
            record.latency_ms = round((time.perf_counter() - started) * 1000, 2)
            return record
        record.latency_ms = round((time.perf_counter() - started) * 1000, 2)
        final_chart = ehr.load_chart(order.patient_id)
        events = audit.read_events(label.case_id, run_id=run_id)

        for verdict in _initial_verdicts(events):
            ref = verdict.get("section_ref") or verdict["criterion_id"].split(":")[-1]
            record.predicted[ref] = verdict["status"]
            record.confidence[ref] = verdict["confidence"]
            record.cited[ref] = [[e["doc_id"], e["start"], e["end"]] for e in verdict.get("evidence", [])]
            record.citations_total += verdict.get("citations_total", 0)
            record.citations_invalid += verdict.get("citations_invalid", 0)
        if record.predicted:
            record.predicted_ready = (set(record.expected) <= set(record.predicted)
                                      and all(s == "met" for s in record.predicted.values()))
        else:
            record.predicted_ready = False

        for event in events:
            p, kind = event["payload"], event["event_type"]
            if kind == "llm_call":
                record.input_tokens += p.get("input_tokens", 0)
                record.output_tokens += p.get("output_tokens", 0)
            elif kind == "decision" and "criterion_id" in p:
                record.check_attempts += p.get("attempts", 0)
                record.invalid_outputs += p.get("invalid_outputs", 0)
            elif kind == "tool_result" and p.get("tool") == "draft_letter" and not record.letter_proposed:
                record.letter_proposed = p.get("proposed", 0)
                record.letter_accepted = p.get("accepted", 0)
                record.letter_fallbacks = p.get("fallbacks", 0)
            elif kind == "tool_result" and p.get("tool") == "check_status" and p.get("status") == "denied":
                record.denied = True
            elif kind == "tool_result" and p.get("tool") == "draft_appeal":
                record.appealed = True

        record.letter_statements = len(state.letter_statements)
        record.letter_statements_verified = sum(
            all(e.verify(final_chart) for e in s.evidence) for s in state.letter_statements)
        record.final_status = "queued" if state.queued_reason else state.status.value
        record.tool_calls = state.loop_counts.tool_calls
        record.gap_loops = state.loop_counts.gap_loops
        record.appeals = state.loop_counts.appeals
        record.submissions = len(state.submissions)
        record.escalation_reason = state.escalation_reason
        record.queued = bool(state.queued_reason)
        record.safe = _submitted_packages_are_sound(state, final_chart) and (
            not state.submissions or state.approval is not None)
    return record


def run_agent_cases(cases: list[tuple[Order, Chart | None, CaseLabel]], variant: str, runs: int = 1) -> list[dict]:
    records = []
    for run in range(runs):
        for order, chart, label in cases:
            records.append(run_agent_case(order, label, variant=variant, run=run, chart=chart).to_dict())
    return records


def load_split(split: str, limit: int | None = None) -> list[tuple[Order, Chart | None, CaseLabel]]:
    names = ehr.list_cases(split)[:limit] if limit else ehr.list_cases(split)
    cases = []
    for name in names:
        order, _, label = ehr.load_case_files(split, name)
        cases.append((order, None, label))
    return cases


@contextmanager
def settings(**overrides: Any) -> Iterator[None]:
    """Temporarily change config values (ablations, perturbations)."""
    old = {name: getattr(config, name) for name in overrides}
    for name, value in overrides.items():
        setattr(config, name, value)
    try:
        yield
    finally:
        for name, value in old.items():
            setattr(config, name, value)
