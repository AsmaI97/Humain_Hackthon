import json

import pytest

from authpilot import audit, config, ehr
from authpilot.policies import find_policy, parse_policy
from authpilot.tools.get_patient_record import TOOL_SPEC as RECORD_SPEC
from authpilot.tools.get_patient_record import get_patient_record
from authpilot.tools.search_policy import TOOL_SPEC as SEARCH_SPEC
from authpilot.tools.search_policy import search_policy


@pytest.mark.parametrize("code,policy_id", [("72148", "PA-RAD-014"), ("J0135", "PA-RX-207")])
def test_policies_parse_into_numbered_sections(code, policy_id):
    policy = find_policy("payer_a", code)
    assert policy.policy_id == policy_id
    refs = [s.ref for s in policy.sections]
    for ref in ["1.1", "2", "2.1", "2.2", "2.3", "2.4", "3.1", "5.1"]:
        assert ref in refs
    assert policy.section("2.1").heading == "Coverage criteria"
    assert not policy.section("2.1").text.startswith("2.1")


def test_parse_policy_joins_wrapped_lines():
    policy = parse_policy("---\npolicy_id: X\n---\n## 2. Criteria\n\n2.1 First line\ncontinues here.\n")
    assert policy.section("2.1").text == "First line continues here."


def test_unknown_policy_raises():
    with pytest.raises(KeyError):
        find_policy("payer_a", "99999")


@pytest.mark.parametrize("code,query,expected", [
    ("J0135", "tuberculosis screening negative result", "2.3"),
    ("J0135", "methotrexate dose duration intolerance", "2.2"),
    ("72148", "neurological examination reflexes strength", "2.3"),
    ("72148", "physical therapy NSAIDs duration", "2.1"),
])
def test_bm25_ranks_the_matching_section_near_the_top(code, query, expected):
    hits = search_policy("payer_a", code, query)
    assert expected in [h.ref for h in hits[:2]]
    assert hits == sorted(hits, key=lambda h: -h.score)


def test_search_with_no_matching_terms_returns_nothing():
    assert search_policy("payer_a", "72148", "zzzz qqqq") == []


def test_search_is_logged():
    search_policy("payer_a", "72148", "red flag", case_id="c1")
    types = [e["event_type"] for e in audit.read_events("c1")]
    assert types == ["tool_call", "tool_result"]


def test_get_patient_record_matches_chart_file():
    chart = json.loads((config.CASES_DIR / "dev" / "case_002" / "chart.json").read_text())
    record = get_patient_record("PD0002")
    assert record.as_chart() == chart
    assert [d.doc_id for d in record.documents] == list(chart)


def test_get_patient_record_unknown_patient():
    with pytest.raises(KeyError):
        get_patient_record("NOPE")


def test_chart_override_is_used():
    ehr.set_chart_override("PD0002", {"doc_01": "Replaced."})
    assert get_patient_record("PD0002").as_chart() == {"doc_01": "Replaced."}


@pytest.mark.parametrize("spec", [RECORD_SPEC, SEARCH_SPEC])
def test_tool_specs_have_object_schemas(spec):
    assert spec["input_schema"]["type"] == "object"
    assert spec["input_schema"]["properties"]
