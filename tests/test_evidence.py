from authpilot.evidence import check_citations, locate, unchecked_evidence

CHART = {
    "doc_01": "PROGRESS NOTE\nCompleted 8 weeks of physical therapy. Denies fever.",
    "doc_02": "LABS\nQuantiFERON negative.",
}


def test_locate_exact_quote_computes_offsets():
    ev = locate(CHART, "doc_01", "Denies fever.")
    assert ev is not None and ev.verify(CHART)
    assert CHART["doc_01"][ev.start:ev.end] == "Denies fever."


def test_locate_strips_surrounding_whitespace_only():
    assert locate(CHART, "doc_01", "  Denies fever.  ") is not None
    assert locate(CHART, "doc_01", "denies fever.") is None


def test_fabricated_or_misattributed_quotes_are_dropped():
    check = check_citations(CHART, [
        {"doc_id": "doc_01", "quote": "Completed 8 weeks of physical therapy."},
        {"doc_id": "doc_01", "quote": "Completed 12 weeks of physical therapy."},
        {"doc_id": "doc_02", "quote": "Denies fever."},
        {"doc_id": "doc_99", "quote": "Denies fever."},
    ])
    assert [e.span_text for e in check.valid] == ["Completed 8 weeks of physical therapy."]
    assert len(check.invalid) == 3 and check.total == 4


def test_duplicate_quotes_are_deduplicated():
    quote = {"doc_id": "doc_02", "quote": "QuantiFERON negative."}
    assert len(check_citations(CHART, [quote, quote]).valid) == 1


def test_unchecked_evidence_keeps_fabrications_for_ablation():
    evidence = unchecked_evidence(CHART, [{"doc_id": "doc_01", "quote": "Invented sentence."}])
    assert len(evidence) == 1 and not evidence[0].verify(CHART)
