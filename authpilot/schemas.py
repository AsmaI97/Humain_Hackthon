"""Pydantic v2 models shared by the agent, tools, payer mock and evaluation."""

import re
from datetime import date
from enum import Enum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Status(str, Enum):
    intake = "intake"
    checking = "checking"
    needs_evidence = "needs_evidence"
    ready_for_approval = "ready_for_approval"
    submitted = "submitted"
    approved = "approved"
    denied = "denied"
    appealing = "appealing"
    escalated = "escalated"


CriterionStatus = Literal["met", "not_met", "unclear"]
Outcome = Literal["approve", "needs_evidence", "deny_then_appeal_approve", "deny"]
Procedure = Literal["lumbar_mri", "biologic", "glp1"]

Chart = dict[str, str]


class Order(Strict):
    order_id: str
    patient_id: str
    payer_id: str
    procedure_code: str
    procedure_name: str
    ordering_provider: str
    request_date: date


class Evidence(Strict):
    doc_id: str
    span_text: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(gt=0)

    @model_validator(mode="after")
    def _check_offsets(self) -> "Evidence":
        if self.end - self.start != len(self.span_text):
            raise ValueError("end - start must equal len(span_text)")
        return self

    def verify(self, chart: Chart) -> bool:
        doc = chart.get(self.doc_id)
        return doc is not None and doc[self.start : self.end] == self.span_text


class Criterion(Strict):
    id: str
    text: str
    section_ref: str


SENTENCE_END = re.compile(r"[.!?]+(?:\s|$)")
# Titles and short abbreviations are not sentence boundaries. "Dr. Amin" is one clause.
_ABBREVIATIONS = {"dr", "mr", "mrs", "ms", "prof", "vs", "etc", "e.g", "i.e", "st"}


def sentence_count(value: str) -> int:
    text = value.strip()
    count = 0
    for match in SENTENCE_END.finditer(text):
        prefix = text[: match.start()].rstrip()
        token = prefix.rsplit(None, 1)[-1].lower() if prefix else ""
        if token in _ABBREVIATIONS:
            continue
        count += 1
    return count


class CriterionResult(Strict):
    criterion_id: str
    status: CriterionStatus
    evidence: list[Evidence] = Field(default_factory=list)
    reasoning: str = Field(max_length=400)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("reasoning")
    @classmethod
    def _max_two_sentences(cls, value: str) -> str:
        if sentence_count(value) > 2:
            raise ValueError("reasoning must be at most 2 sentences")
        return value


class Gap(Strict):
    criterion_id: str
    description: str


class LoopCounts(Strict):
    gap_loops: int = 0
    appeals: int = 0
    tool_calls: int = 0


class InfoRequest(Strict):
    request_id: str
    gaps: list[Gap]
    message: str
    new_doc_ids: list[str] = Field(default_factory=list)


class LetterStatement(Strict):
    criterion_id: str
    text: str
    evidence: list[Evidence] = Field(min_length=1)


class Approval(Strict):
    kind: Literal["initial", "appeal"]
    reviewer: str
    letter_sha256: str


class CaseState(Strict):
    case_id: str
    order: Order
    request_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    results: list[CriterionResult] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    letter: str | None = None
    letter_ar: str | None = None
    letter_statements: list[LetterStatement] = Field(default_factory=list)
    status: Status = Status.intake
    loop_counts: LoopCounts = Field(default_factory=LoopCounts)
    record_doc_ids: list[str] = Field(default_factory=list)
    checked_doc_ids: list[str] = Field(default_factory=list)
    info_requests: list[InfoRequest] = Field(default_factory=list)
    approval: Approval | None = None
    submission_id: str | None = None
    submissions: list[str] = Field(default_factory=list)
    payer_status: str | None = None
    denial_reason: str | None = None
    denial_code: str | None = None
    denial_ref: str | None = None
    appeal_letter: str | None = None
    appeal_letter_ar: str | None = None
    appeal_statements: list[LetterStatement] = Field(default_factory=list)
    appeal_codes: list[str] = Field(default_factory=list)
    escalation_reason: str | None = None
    queued_reason: str | None = None


# Payer exchange ---------------------------------------------------------------------------


class SubmittedCriterion(Strict):
    section_ref: str
    status: CriterionStatus
    evidence: list[Evidence] = Field(default_factory=list)


class SubmissionPackage(Strict):
    case_id: str
    idempotency_key: str
    order: Order
    criteria: list[SubmittedCriterion]
    letter: str
    letter_ar: str | None = None
    attachments: dict[str, str]
    appeal_of: str | None = None


class PayerDecision(Strict):
    submission_id: str
    status: Literal["received", "approved", "denied"]
    reason_code: str | None = None
    reason: str | None = None
    level: Literal["first", "appeal"] = "first"


class LabeledCriterion(Strict):
    criterion_id: str
    section_ref: str
    status: CriterionStatus
    evidence: list[Evidence] = Field(default_factory=list)


class CaseLabel(Strict):
    case_id: str
    split: Literal["dev", "sealed", "unseen"]
    procedure: Procedure
    criteria: list[LabeledCriterion]
    planted_gaps: list[Gap] = Field(default_factory=list)
    expected_outcome: Outcome
    expected_final: Literal["approved", "escalated"]
    supplemental: list[LabeledCriterion] = Field(default_factory=list)
    hard_case_tags: list[str] = Field(default_factory=list)
    facts: dict[str, int | float | str | bool] = Field(default_factory=dict)
    notes: str = ""
