import pytest

from authpilot import llm, store, stub_llm
from authpilot.prompts import LETTER_TOOL
from authpilot.schemas import Status
from authpilot.tools._common import ToolRefused
from authpilot.tools.check_criteria import check_criteria
from authpilot.tools.draft_letter import LetterReport, draft_letter, unsupported_numbers
from helpers import clean_case, start, unsupplied_gap_case


def _letter_reply(statements_for):
    def caller(request):
        if (request.get("tool_choice") or {}).get("name") == LETTER_TOOL:
            return {"content": [{"type": "tool_use", "id": "l1", "name": LETTER_TOOL,
                                 "input": {"statements": statements_for(request)}}],
                    "stop_reason": "tool_use", "model": "fake", "usage": {}}
        return stub_llm.respond(request)
    return caller


def test_letter_refused_while_gaps_are_open():
    case_id = start(unsupplied_gap_case())
    check_criteria(case_id)
    with pytest.raises(ToolRefused, match="not every criterion"):
        draft_letter(case_id)


def test_every_letter_statement_maps_to_verified_chart_spans():
    order, chart, label = case = clean_case()
    case_id = start(case)
    check_criteria(case_id)
    report = LetterReport()
    letter = draft_letter(case_id, report)
    state = store.get_case(case_id)
    assert state.status is Status.ready_for_approval
    assert len(state.letter_statements) == 4 and report.accepted == 4 and report.fallbacks == 0
    for statement in state.letter_statements:
        assert all(e.verify(chart) for e in statement.evidence)
        assert not unsupported_numbers(statement.text, [e.span_text for e in statement.evidence], set())
        assert statement.text in letter
    assert order.order_id in letter


def test_fabricated_statements_are_dropped_and_replaced_by_quotes(monkeypatch):
    order, chart, label = case = clean_case()
    case_id = start(case)
    check_criteria(case_id)
    results = store.get_case(case_id).results
    real = results[0].evidence[0]

    def statements(request):
        return [
            {"criterion_id": results[0].criterion_id, "text": "The patient completed 20 weeks of therapy.",
             "quotes": [{"doc_id": real.doc_id, "quote": real.span_text}]},
            {"criterion_id": results[1].criterion_id, "text": "All red flags were excluded.",
             "quotes": [{"doc_id": real.doc_id, "quote": "Invented quote."}]},
            {"criterion_id": "PA-RAD-014:9.9", "text": "Extra claim.", "quotes": [{"doc_id": real.doc_id, "quote": real.span_text}]},
        ]

    monkeypatch.setattr(llm, "stub_caller", _letter_reply(statements))
    report = LetterReport()
    draft_letter(case_id, report)
    reasons = sorted(d["reason"].split(":")[0] for d in report.dropped)
    assert reasons == ["criterion is not met or unknown", "no cited quote is verbatim in the chart", "numbers not in cited quotes"]
    assert report.fallbacks == 4
    for statement in store.get_case(case_id).letter_statements:
        assert all(e.verify(chart) for e in statement.evidence)
        assert "20 weeks" not in statement.text


def test_unsupported_numbers():
    assert unsupported_numbers("Completed 8 weeks.", ["Completed eight weeks."], set()) == ["8"]
    assert unsupported_numbers("Per section 2.1, 8 weeks.", ["8 weeks"], {"2.1"}) == []
