"""Prompts, tool schemas and the Pydantic models that validate model output.

The XML-style tags are part of the contract: the offline stub model parses them too.
"""

from datetime import date
from typing import Literal

from pydantic import Field, field_validator

from authpilot.policies import Policy, PolicySection
from authpilot.schemas import sentence_count, Chart, Criterion, CriterionStatus, Strict

# Criteria extraction ------------------------------------------------------------------------

EXTRACT_TOOL = "record_criteria"

EXTRACT_SYSTEM = (
    "You read payer medical policies. Identify the coverage criteria a request must satisfy. "
    "Return only sections that state a criterion the patient record must document, using the "
    "section reference exactly as written in the policy. Do not invent criteria."
)

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "criteria": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "section_ref": {"type": "string", "description": "Policy section number, e.g. 2.1"},
                    "name": {"type": "string", "description": "Short name of the criterion"},
                },
                "required": ["section_ref", "name"],
            },
        }
    },
    "required": ["criteria"],
}


class ExtractedCriterion(Strict):
    section_ref: str
    name: str = Field(min_length=1, max_length=120)


class CriteriaExtraction(Strict):
    criteria: list[ExtractedCriterion] = Field(min_length=1)


def extraction_messages(policy: Policy) -> list[dict]:
    sections = "\n".join(
        f'<section ref="{s.ref}" heading="{s.heading}">{s.text}</section>' for s in policy.sections
    )
    content = (
        f'<policy id="{policy.policy_id}">\n{sections}\n</policy>\n'
        f"List every coverage criterion by calling {EXTRACT_TOOL}."
    )
    return [{"role": "user", "content": content}]


# Criterion check --------------------------------------------------------------------------

CHECK_TOOL = "record_criterion_result"

CHECK_SYSTEM = (
    "You are a prior authorization reviewer. Decide whether one payer policy criterion is "
    "documented in the patient chart.\n"
    "Rules:\n"
    "- Use only the chart. Never assume facts that are not written there.\n"
    "- status=met only when the chart explicitly satisfies every part of the criterion, "
    "including thresholds, dates and time windows relative to the request date.\n"
    "- status=not_met when the chart has no documentation for the criterion, or documents "
    "that it is not satisfied.\n"
    "- status=unclear when documentation is vague, incomplete, indeterminate or contradictory.\n"
    "- Ignore statements about other people (family members, spouses), past episodes outside "
    "the policy window, and plans or orders that have not happened yet.\n"
    "- Every evidence item must quote one sentence copied exactly, character for character, "
    "from a single chart document, with that document's id. Cite contradicting text too.\n"
    "- reasoning: at most two sentences. confidence: 0 to 1."
)

CHECK_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["met", "not_met", "unclear"]},
        "evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "doc_id": {"type": "string"},
                    "quote": {"type": "string", "description": "Exact text copied from the document"},
                },
                "required": ["doc_id", "quote"],
            },
        },
        "reasoning": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["status", "evidence", "reasoning", "confidence"],
}


class Quote(Strict):
    doc_id: str
    quote: str = Field(min_length=1)


class CriterionAssessment(Strict):
    status: CriterionStatus
    evidence: list[Quote] = Field(default_factory=list)
    reasoning: str = Field(max_length=400)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("reasoning")
    @classmethod
    def _max_two_sentences(cls, value: str) -> str:
        if sentence_count(value) > 2:
            raise ValueError("reasoning must be at most 2 sentences")
        return value


def format_chart(chart: Chart) -> str:
    docs = "\n".join(f'<document id="{doc_id}">\n{text}</document>' for doc_id, text in chart.items())
    return f"<chart>\n{docs}\n</chart>"


def check_messages(
    criterion: Criterion,
    policy_context: list[PolicySection],
    chart: Chart,
    request_date: date,
    procedure: str,
) -> list[dict]:
    context = "\n".join(f'<section ref="{s.ref}">{s.text}</section>' for s in policy_context)
    content = (
        f"<request_date>{request_date.isoformat()}</request_date>\n"
        f"<procedure>{procedure}</procedure>\n"
        f'<criterion id="{criterion.id}" section_ref="{criterion.section_ref}">{criterion.text}</criterion>\n'
        f"<policy_context>\n{context}\n</policy_context>\n"
        f"{format_chart(chart)}\n"
        f"Assess the criterion and call {CHECK_TOOL}."
    )
    return [{"role": "user", "content": content}]


def retry_messages(assistant_content: list[dict], tool_name: str, error: str) -> list[dict]:
    """Feed a validation error back to the model as a tool_result so it can correct itself."""
    tool_use_id = next(
        (b.get("id") for b in assistant_content if b.get("type") == "tool_use" and b.get("name") == tool_name),
        None,
    )
    note = f"Invalid {tool_name} input: {error}. Call {tool_name} again with valid input."
    if tool_use_id is None:
        return [
            {"role": "assistant", "content": assistant_content or [{"type": "text", "text": "(no tool call)"}]},
            {"role": "user", "content": note},
        ]
    return [
        {"role": "assistant", "content": assistant_content},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_use_id, "content": note, "is_error": True}]},
    ]


# Letter drafting --------------------------------------------------------------------------

LETTER_TOOL = "record_letter"

LETTER_SYSTEM = (
    "You draft medical-necessity letters for prior authorization. Write one short statement per "
    "criterion, in plain clinical English, addressed to the payer reviewer.\n"
    "Rules:\n"
    "- Each statement may only restate facts contained in the evidence quotes you cite.\n"
    "- Every number or date in a statement must appear in its cited quotes.\n"
    "- Cite at least one quote per statement, copied exactly from the evidence provided.\n"
    "- Do not add diagnoses, durations, results or opinions that are not in the quotes."
)

LETTER_SCHEMA = {
    "type": "object",
    "properties": {
        "statements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "criterion_id": {"type": "string"},
                    "text": {"type": "string"},
                    "quotes": CHECK_SCHEMA["properties"]["evidence"],
                },
                "required": ["criterion_id", "text", "quotes"],
            },
        }
    },
    "required": ["statements"],
}


class DraftStatement(Strict):
    criterion_id: str
    text: str = Field(min_length=1, max_length=500)
    quotes: list[Quote] = Field(min_length=1)


class LetterDraft(Strict):
    statements: list[DraftStatement]


def letter_messages(procedure: str, request_date: date, items: list[tuple[Criterion, str, list]]) -> list[dict]:
    """items: (criterion, short name, verified evidence spans)."""
    blocks = []
    for criterion, name, evidence in items:
        quotes = "\n".join(f'<evidence doc_id="{e.doc_id}">{e.span_text}</evidence>' for e in evidence)
        blocks.append(
            f'<criterion id="{criterion.id}" section_ref="{criterion.section_ref}" name="{name}">\n'
            f"{criterion.text}\n{quotes}\n</criterion>"
        )
    content = (
        f"<request_date>{request_date.isoformat()}</request_date>\n"
        f"<procedure>{procedure}</procedure>\n"
        + "\n".join(blocks)
        + f"\nWrite one statement per criterion and call {LETTER_TOOL}."
    )
    return [{"role": "user", "content": content}]


# Appeal drafting --------------------------------------------------------------------------

APPEAL_TOOL = "record_appeal"

APPEAL_SYSTEM = (
    "You draft appeals of prior authorization denials. Address the payer's stated denial reason "
    "directly, for the denied criterion only, using only the evidence quotes provided.\n"
    "Rules:\n"
    "- Each statement may only restate facts contained in the evidence quotes you cite.\n"
    "- Every number or date in a statement must appear in its cited quotes.\n"
    "- Cite at least one quote per statement, copied exactly from the evidence provided.\n"
    "- Do not argue beyond the record."
)


def appeal_messages(denial_code: str, denial_reason: str, procedure: str, request_date: date,
                    items: list[tuple[Criterion, str, list]]) -> list[dict]:
    letter = letter_messages(procedure, request_date, items)[0]["content"]
    content = (f'<denial code="{denial_code}">{denial_reason}</denial>\n'
               + letter.replace(f"call {LETTER_TOOL}", f"call {APPEAL_TOOL}"))
    return [{"role": "user", "content": content}]


# Single-prompt baseline (evaluation only) -------------------------------------------------

SINGLE_TOOL = "record_all_criteria"

SINGLE_SYSTEM = (
    "You review prior authorization requests. Read the payer policy and the patient chart, find "
    "every coverage criterion in the policy, and decide for each one whether the chart documents it. "
    + CHECK_SYSTEM.split("Rules:\n", 1)[1]
)

SINGLE_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"section_ref": {"type": "string"}, **CHECK_SCHEMA["properties"]},
                "required": ["section_ref", *CHECK_SCHEMA["required"]],
            },
        }
    },
    "required": ["results"],
}


class SingleResult(CriterionAssessment):
    section_ref: str


class SingleAssessment(Strict):
    results: list[SingleResult]


def single_messages(policy: Policy, chart: Chart, request_date: date, procedure: str) -> list[dict]:
    sections = "\n".join(
        f'<section ref="{s.ref}" heading="{s.heading}">{s.text}</section>' for s in policy.sections
    )
    content = (
        f"<request_date>{request_date.isoformat()}</request_date>\n"
        f"<procedure>{procedure}</procedure>\n"
        f'<policy id="{policy.policy_id}">\n{sections}\n</policy>\n'
        f"{format_chart(chart)}\n"
        f"Assess every coverage criterion and call {SINGLE_TOOL}."
    )
    return [{"role": "user", "content": content}]


ToolName = Literal["record_criteria", "record_criterion_result", "record_letter", "record_appeal",
                   "record_all_criteria"]


def tool_spec(name: ToolName) -> dict:
    if name == EXTRACT_TOOL:
        return {"name": EXTRACT_TOOL, "description": "Record the policy's coverage criteria.", "input_schema": EXTRACT_SCHEMA}
    if name == LETTER_TOOL:
        return {"name": LETTER_TOOL, "description": "Record the letter statements.", "input_schema": LETTER_SCHEMA}
    if name == APPEAL_TOOL:
        return {"name": APPEAL_TOOL, "description": "Record the appeal statements.", "input_schema": LETTER_SCHEMA}
    if name == SINGLE_TOOL:
        return {"name": SINGLE_TOOL, "description": "Record the assessment of every criterion.",
                "input_schema": SINGLE_SCHEMA}
    return {"name": CHECK_TOOL, "description": "Record the assessment of one criterion.", "input_schema": CHECK_SCHEMA}
