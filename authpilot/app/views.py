"""Data shaping for the dashboard. Pure functions over case state and audit events, so they can
be tested without Streamlit."""

from typing import Any

from authpilot import audit, gate, store
from authpilot.schemas import CaseState, Status

STATUS_MARK = {"met": "[met]", "not_met": "[NOT MET]", "unclear": "[UNCLEAR]"}


def _short(value: Any, limit: int = 140) -> str:
    text = value if isinstance(value, str) else str(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def describe_event(event: dict) -> tuple[str, str]:
    """(kind, one-line description) for one audit event."""
    p, kind = event["payload"], event["event_type"]
    if kind == "tool_call":
        return "tool call", f"{p['tool']}({_short(p.get('args', {}), 80)})"
    if kind == "tool_result":
        body = {k: v for k, v in p.items() if k not in ("tool", "letter", "message", "appeal_letter")}
        return "tool result", f"{p['tool']}: {_short(body)}"
    if kind == "llm_call":
        return "model", (f"{p.get('purpose')} by {p.get('served_by', p.get('model'))} ({p.get('source')}), "
                         f"{p.get('input_tokens', 0)}/{p.get('output_tokens', 0)} tokens, {p.get('latency_ms')} ms")
    if kind == "decision":
        if "criterion_id" in p:
            return "verdict", f"{p['criterion_id']} = {p['status']} (confidence {p['confidence']})"
        if p.get("event") == "step":
            result = {k: v for k, v in (p.get("result") or {}).items() if k != "tool"}
            return "step", f"step {p['step']}: {p['tool']} -> {p['status_after']}  {_short(result, 120) if result else ''}".strip()
        return "event", f"{p.get('event')}: {_short({k: v for k, v in p.items() if k != 'event'})}"
    if kind == "human_action":
        return "human", f"{event['actor']} {p.get('action')} ({p.get('kind')}) {p.get('reason', '')}".strip()
    if kind == "fallback":
        return "fallback", f"{p.get('rule')}: {_short({k: v for k, v in p.items() if k != 'rule'})}"
    if kind == "error":
        return "error", _short(p)
    return kind, _short(p)


def timeline_rows(case_id: str, include_model_calls: bool = False, include_tool_calls: bool = False) -> list[dict]:
    """Events of the case's latest run (from its last run_started, including later resumes).
    By default: agent steps, verdicts, human actions, fallbacks, errors and run events.
    Tool calls (including the ones tools make internally) and model calls are opt-in details."""
    rows = []
    events = audit.read_events(case_id)
    starts = [i for i, e in enumerate(events) if e["payload"].get("event") == "run_started"]
    for event in events[starts[-1]:] if starts else events:
        if event["event_type"] == "llm_call" and not include_model_calls:
            continue
        if event["event_type"] in ("tool_call", "tool_result") and not include_tool_calls:
            continue
        kind, text = describe_event(event)
        rows.append({"time": event["ts"][11:19], "run": event["run_id"], "kind": kind, "detail": text})
    return rows


def checklist_rows(state: CaseState) -> list[dict]:
    gaps = {g.criterion_id: g.description for g in state.gaps}
    return [
        {
            "criterion": result.criterion_id,
            "status": STATUS_MARK[result.status],
            "status_key": result.status,
            "confidence": result.confidence,
            "reasoning": result.reasoning,
            "quotes": [(e.doc_id, e.span_text) for e in result.evidence],
            "gap": gaps.get(result.criterion_id),
        }
        for result in state.results
    ]


def needs_human(state: CaseState) -> str | None:
    if gate.awaiting_approval(state):
        return f"approve {gate.awaiting_approval(state)} letter"
    if state.status is Status.escalated:
        return "escalated"
    if state.queued_reason:
        return "queued"
    return None


def queue_rows() -> list[dict]:
    rows = []
    for case_id in store.list_case_ids():
        state = store.reload(case_id)
        reason = needs_human(state)
        if reason:
            rows.append({
                "case": case_id,
                "procedure": state.order.procedure_name,
                "status": state.status.value,
                "needs": reason,
                "reason": state.escalation_reason or state.queued_reason or "",
            })
    return rows
