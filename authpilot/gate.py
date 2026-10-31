"""Human approval gate. Only a person (CLI or dashboard) can approve; the agent has no tool for it.

An approval is bound to the SHA-256 of the exact letter it covers, so any later change to the
letter invalidates it.
"""

import hashlib

from authpilot import audit, store
from authpilot.schemas import Approval, CaseState, Status
from authpilot.tools._common import ToolRefused
from authpilot.tools.escalate import escalate


def letters_for(state: CaseState, kind: str) -> list[tuple[str, str]]:
    """(language, text) for every version of the letter: English first, then Arabic if drafted."""
    english = state.letter if kind == "initial" else state.appeal_letter
    arabic = state.letter_ar if kind == "initial" else state.appeal_letter_ar
    if not english:
        return []
    return [("en", english)] + ([("ar", arabic)] if arabic else [])


def letter_for(state: CaseState, kind: str) -> str | None:
    """Everything the approval covers: all versions of the letter, so editing either voids it."""
    versions = letters_for(state, kind)
    return "\n\n".join(text for _, text in versions) if versions else None


def letter_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def approval_valid(state: CaseState, kind: str) -> bool:
    letter = letter_for(state, kind)
    approval = state.approval
    return bool(letter and approval and approval.kind == kind and approval.letter_sha256 == letter_hash(letter))


def awaiting_approval(state: CaseState) -> str | None:
    if state.queued_reason:
        return None
    if state.status is Status.ready_for_approval and state.letter and not approval_valid(state, "initial"):
        return "initial"
    if state.status is Status.appealing and state.appeal_letter and not approval_valid(state, "appeal"):
        return "appeal"
    return None


def approve(case_id: str, reviewer: str) -> CaseState:
    state = store.get_case(case_id)
    kind = awaiting_approval(state)
    if kind is None:
        raise ToolRefused("approve: nothing is awaiting approval")
    state.approval = Approval(kind=kind, reviewer=reviewer, letter_sha256=letter_hash(letter_for(state, kind)))
    store.save_case(state)
    audit.log_event(case_id, reviewer, "human_action", {"action": "approve", "kind": kind,
                                                       "letter_sha256": state.approval.letter_sha256})
    return state


def reject(case_id: str, reviewer: str, reason: str) -> CaseState:
    state = store.get_case(case_id)
    kind = awaiting_approval(state)
    audit.log_event(case_id, reviewer, "human_action", {"action": "reject", "kind": kind, "reason": reason})
    return escalate(case_id, f"rejected by {reviewer}: {reason}")
