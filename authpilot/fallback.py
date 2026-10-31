"""Fallback policy. Every rule logs a 'fallback' audit event when it fires.

Rules (from the spec):
- Invalid structured output: retry with the validation error, max 2, then escalate.
- Evidence span not found in chart: drop the claim, mark "evidence not found".
- Low confidence or unclear status: abstain and escalate with a summary.
- Weak retrieval: widen the search, then put the full policy in context, then escalate.
- LLM error or timeout: retry with backoff (llm.py), then switch to CHEAP_MODEL, then queue.
- Payer API down: retry, mark pending, never double submit (idempotency key).
- Loop caps reached: escalate to a human (agent.py).
"""

import json
import time
from pathlib import Path
from typing import Any, Callable

from authpilot import audit, config, llm, store
from authpilot.policies import Policy, PolicySection
from authpilot.schemas import CaseState, Criterion, CriterionResult
from authpilot.tools.escalate import escalate

sleep: Callable[[float], None] = time.sleep

INVALID_OUTPUT_REASONING = "Model output was invalid after retries."
EVIDENCE_NOT_FOUND_REASONING = "Evidence not found: the cited text does not appear in the chart."


class CaseQueued(Exception):
    """A dependency is unavailable; the case is parked to be retried later."""


class EscalationRequired(Exception):
    """The case cannot proceed safely and must go to a human."""


def log(case_id: str, rule: str, **details: Any) -> None:
    audit.log_event(case_id, "fallback", "fallback", {"rule": rule, **details})


# LLM error or timeout --------------------------------------------------------------------


def complete(*, case_id: str, purpose: str, model: str | None = None, **kwargs) -> llm.LLMResponse:
    """llm.complete with the model fallback chain: requested model, then CHEAP_MODEL, then queue."""
    model = model or config.AGENT_MODEL
    try:
        return llm.complete(model=model, case_id=case_id, purpose=purpose, **kwargs)
    except llm.LLMError as exc:
        first_error = f"{type(exc).__name__}: {exc}"
    if model != config.CHEAP_MODEL:
        log(case_id, "llm_error_switch_model", purpose=purpose, from_model=model, to_model=config.CHEAP_MODEL,
            error=first_error)
        try:
            return llm.complete(model=config.CHEAP_MODEL, case_id=case_id, purpose=purpose, **kwargs)
        except llm.LLMError as exc:
            first_error = f"{type(exc).__name__}: {exc}"
    log(case_id, "llm_error_queue", purpose=purpose, error=first_error)
    raise CaseQueued(f"LLM unavailable during {purpose}")


def queue_case(case_id: str, reason: str) -> CaseState:
    state = store.get_case(case_id)
    state.queued_reason = reason
    store.save_case(state)
    path = Path(config.RUNTIME_DIR) / "queue.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"case_id": case_id, "reason": reason, "status": state.status.value}) + "\n")
    log(case_id, "queued", reason=reason, status=state.status.value)
    return state


# Weak retrieval --------------------------------------------------------------------------


def _weak(hits: list) -> bool:
    return not hits or hits[0].score < config.RETRIEVAL_MIN_SCORE


def policy_context(policy: Policy, payer_id: str, procedure_code: str, criterion: Criterion, case_id: str,
                   search: Callable) -> list[PolicySection]:
    if not policy.sections:
        log(case_id, "retrieval_escalate", criterion_id=criterion.id)
        raise EscalationRequired(f"policy {policy.policy_id} has no readable sections")
    hits = search(payer_id, procedure_code, criterion.text, config.RETRIEVAL_K, case_id=case_id)
    if _weak(hits):
        name = criterion.text.split(". ")[0]
        log(case_id, "retrieval_widen", criterion_id=criterion.id, k=config.RETRIEVAL_WIDE_K)
        hits = search(payer_id, procedure_code, f"{name} {criterion.text}", config.RETRIEVAL_WIDE_K, case_id=case_id)
    if _weak(hits):
        log(case_id, "retrieval_full_policy", criterion_id=criterion.id)
        return list(policy.sections)
    refs = [criterion.section_ref] + [h.ref for h in hits if h.ref != criterion.section_ref]
    return [s for s in (policy.section(r) for r in refs) if s is not None]


# Evidence span not found ------------------------------------------------------------------


def evidence_not_found(case_id: str, criterion_id: str, status: str, confidence: float, reasoning: str,
                       has_valid_evidence: bool, invalid: list[dict]) -> tuple[str, float, str]:
    if invalid:
        log(case_id, "evidence_dropped", criterion_id=criterion_id, quotes=[q.get("quote", "") for q in invalid])
    if status == "met" and not has_valid_evidence:
        log(case_id, "evidence_not_found", criterion_id=criterion_id)
        return "unclear", min(confidence, 0.3), EVIDENCE_NOT_FOUND_REASONING
    return status, confidence, reasoning


# Invalid output, low confidence, unclear --------------------------------------------------


def review_results(case_id: str, results: list[CriterionResult], diagnostics: list) -> str | None:
    """Return an escalation summary if the agent must abstain, else None."""
    invalid = [d.criterion_id for d in diagnostics if d.attempts and d.invalid_outputs == d.attempts]
    if invalid:
        log(case_id, "invalid_output_escalate", criteria=invalid)
        return f"model output invalid after retries for {', '.join(invalid)}"
    unsure = [r for r in results if r.status == "unclear" or r.confidence < config.CONFIDENCE_THRESHOLD]
    if not unsure:
        return None
    summary = "; ".join(f"{r.criterion_id} {r.status} ({r.confidence:.2f}): {r.reasoning}" for r in unsure)
    log(case_id, "abstain_low_confidence_or_unclear", criteria=[r.criterion_id for r in unsure],
        threshold=config.CONFIDENCE_THRESHOLD)
    return f"abstained, needs human review: {summary}"


def escalate_with(case_id: str, reason: str) -> CaseState:
    return escalate(case_id, reason)


# Payer down -------------------------------------------------------------------------------


def with_payer_retries(case_id: str, action: str, call: Callable[[], Any]) -> Any:
    from authpilot.payer_client import PayerUnavailable

    for attempt in range(config.PAYER_MAX_RETRIES + 1):
        try:
            return call()
        except PayerUnavailable as exc:
            log(case_id, "payer_retry", action=action, attempt=attempt + 1, error=str(exc))
            if attempt < config.PAYER_MAX_RETRIES:
                sleep(config.PAYER_BACKOFF_S * (2 ** attempt))
    log(case_id, "payer_pending", action=action)
    raise CaseQueued(f"payer unavailable during {action}; marked pending")
