"""Gap detection: every criterion that is not met becomes a gap. Deterministic, no model call."""

from authpilot.schemas import Criterion, CriterionResult, Gap

_STATUS_TEXT = {
    "not_met": "not documented or not satisfied.",
    "unclear": "documentation is unclear or conflicting.",
}


def criterion_name(criterion: Criterion) -> str:
    return criterion.text.split(". ")[0].strip()


def detect_gaps(criteria: list[Criterion], results: list[CriterionResult]) -> list[Gap]:
    by_id = {c.id: c for c in criteria}
    gaps = []
    for result in results:
        if result.status == "met":
            continue
        criterion = by_id[result.criterion_id]
        gaps.append(Gap(
            criterion_id=result.criterion_id,
            description=f"Policy {criterion.section_ref} ({criterion_name(criterion)}): "
                        f"{_STATUS_TEXT[result.status]} {result.reasoning}".strip(),
        ))
    return gaps
