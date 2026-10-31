import pytest
from pydantic import ValidationError

from authpilot.schemas import CaseState, CriterionResult, Evidence, Order, Status

CHART = {"doc_01": "PROGRESS NOTE\nCompleted 8 weeks of physical therapy."}
SPAN = "Completed 8 weeks of physical therapy."
START = CHART["doc_01"].index(SPAN)


def _evidence(**overrides) -> Evidence:
    data = {"doc_id": "doc_01", "span_text": SPAN, "start": START, "end": START + len(SPAN)}
    data.update(overrides)
    return Evidence(**data)


def _result(**overrides) -> CriterionResult:
    data = {
        "criterion_id": "mri.conservative_therapy",
        "status": "met",
        "evidence": [_evidence()],
        "reasoning": "Eight weeks of PT is documented. This exceeds the 6 week minimum.",
        "confidence": 0.9,
    }
    data.update(overrides)
    return CriterionResult(**data)


def test_reasoning_allows_a_title_inside_two_sentences():
    _result(reasoning=(
        "The consult by Dr. Amin documents rheumatoid arthritis confirmed on evaluation. "
        "This satisfies a diagnosis made or confirmed by a rheumatologist."
    ))


def test_reasoning_rejects_three_sentences():
    with pytest.raises(ValidationError):
        _result(reasoning="One. Two. Three.")


def test_evidence_verify_true_for_exact_span():
    assert _evidence().verify(CHART)


def test_evidence_verify_false_for_wrong_offsets_or_doc():
    shifted = Evidence(doc_id="doc_01", span_text=SPAN, start=START + 1, end=START + 1 + len(SPAN))
    assert not shifted.verify(CHART)
    assert not _evidence(doc_id="doc_99").verify(CHART)


def test_evidence_rejects_inconsistent_offsets():
    with pytest.raises(ValidationError):
        _evidence(end=START + 3)


def test_reasoning_max_two_sentences():
    assert _result(reasoning="One. Two.").reasoning == "One. Two."
    with pytest.raises(ValidationError):
        _result(reasoning="One. Two. Three.")


def test_decimal_numbers_do_not_count_as_sentences():
    assert _result(reasoning="DAS28 is 5.1 which is above 3.2.").confidence == 0.9


@pytest.mark.parametrize("confidence", [-0.1, 1.01])
def test_confidence_out_of_range_rejected(confidence):
    with pytest.raises(ValidationError):
        _result(confidence=confidence)


def test_invalid_status_rejected():
    with pytest.raises(ValidationError):
        _result(status="probably")


def test_extra_fields_rejected():
    with pytest.raises(ValidationError):
        _result(extra_field="x")


def test_case_state_defaults():
    order = Order(
        order_id="ORD-1", patient_id="P1", payer_id="payer_a", procedure_code="72148",
        procedure_name="MRI lumbar spine without contrast", ordering_provider="Dr. Test",
        request_date="2026-10-01",
    )
    state = CaseState(case_id="c1", order=order)
    assert state.status is Status.intake
    assert state.loop_counts.gap_loops == 0
    assert state.results == [] and state.gaps == []
