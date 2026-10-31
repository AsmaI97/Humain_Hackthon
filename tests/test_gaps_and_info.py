import json

import pytest

from authpilot import config, ehr, store
from authpilot.schemas import Status
from authpilot.tools._common import ToolRefused
from authpilot.tools.check_criteria import check_criteria
from authpilot.tools.request_missing_info import request_missing_info
from helpers import clean_case, start, supplied_gap_case, unsupplied_gap_case


def test_clean_case_has_no_gaps_and_request_is_refused():
    case_id = start(clean_case())
    check_criteria(case_id)
    assert store.get_case(case_id).gaps == []
    with pytest.raises(ToolRefused, match="no open gaps"):
        request_missing_info(case_id)


def test_gaps_match_planted_gaps_for_missing_case():
    case = supplied_gap_case()
    case_id = start(case)
    check_criteria(case_id)
    found = {g.criterion_id.split(":")[-1] for g in store.get_case(case_id).gaps}
    planted = {c.section_ref for c in case[2].criteria if c.status != "met"}
    assert found == planted


def test_request_sends_message_and_clinic_supplies_documents():
    case = supplied_gap_case()
    order, chart, label = case
    case_id = start(case)
    check_criteria(case_id)
    request = request_missing_info(case_id)

    state = store.get_case(case_id)
    assert state.loop_counts.gap_loops == 1 and state.status is Status.needs_evidence
    assert request.new_doc_ids and not set(request.new_doc_ids) & set(chart)
    assert set(request.new_doc_ids) <= set(ehr.load_chart(order.patient_id))
    assert order.ordering_provider in request.message
    outbox = [json.loads(l) for l in (config.RUNTIME_DIR / "outbox.jsonl").read_text().splitlines()]
    assert outbox[-1]["request_id"] == request.request_id

    check_criteria(case_id)
    assert store.get_case(case_id).gaps == []


def test_clinic_without_documents_returns_nothing():
    case_id = start(unsupplied_gap_case())
    check_criteria(case_id)
    assert request_missing_info(case_id).new_doc_ids == []


def test_gap_loop_cap_is_enforced():
    case_id = start(unsupplied_gap_case())
    check_criteria(case_id)
    for _ in range(config.MAX_GAP_LOOPS):
        request_missing_info(case_id)
    with pytest.raises(ToolRefused, match="cap"):
        request_missing_info(case_id)
    assert store.get_case(case_id).loop_counts.gap_loops == config.MAX_GAP_LOOPS
