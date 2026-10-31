import json
import re
from collections import Counter, defaultdict

import pytest

from authpilot import config
from authpilot.data import generator
from authpilot.schemas import CaseLabel, Order

HARD_CASE_TAGS = {"missing", "ambiguous", "contradictory", "distractor", "appeal_scenario"}


@pytest.fixture(scope="module", params=["dev", "sealed"])
def split_cases(request):
    return request.param, generator.generate_split(request.param)


def _serialized(cases):
    return [generator.case_files(case) for case in cases]


def test_same_seed_is_byte_identical():
    a = _serialized(generator.generate_cases(20, seed=7, split="dev"))
    b = _serialized(generator.generate_cases(20, seed=7, split="dev"))
    assert a == b


def test_different_seeds_differ():
    a = _serialized(generator.generate_cases(20, seed=7, split="dev"))
    b = _serialized(generator.generate_cases(20, seed=8, split="dev"))
    assert a != b


def test_dev_and_sealed_use_different_seeds():
    assert config.DEV_SEED != config.SEALED_SEED


def test_split_sizes(split_cases):
    split, cases = split_cases
    assert len(cases) == {"dev": 60, "sealed": 40}[split]
    assert len({case.label.case_id for case in cases}) == len(cases)


def test_every_label_span_is_verbatim(split_cases):
    _, cases = split_cases
    checked = 0
    for case in cases:
        for criterion in case.label.criteria:
            for ev in criterion.evidence:
                assert case.chart[ev.doc_id][ev.start : ev.end] == ev.span_text
                assert ev.verify(case.chart)
                checked += 1
    assert checked > 0


def test_labels_are_internally_consistent(split_cases):
    _, cases = split_cases
    for case in cases:
        gap_ids = {gap.criterion_id for gap in case.label.planted_gaps}
        for criterion in case.label.criteria:
            if criterion.status == "met":
                assert criterion.evidence and criterion.criterion_id not in gap_ids
            else:
                assert criterion.criterion_id in gap_ids
            if criterion.status == "not_met":
                assert not criterion.evidence
        all_met = all(c.status == "met" for c in case.label.criteria)
        if case.label.expected_outcome == "needs_evidence":
            assert not all_met
        else:
            assert all_met


def test_expected_final_matches_what_the_clinic_can_supply(split_cases):
    _, cases = split_cases
    for case in cases:
        open_ids = {c.criterion_id for c in case.label.criteria if c.status != "met"}
        supplied = {c.criterion_id for c in case.label.supplemental}
        assert supplied <= {c.criterion_id for c in case.label.criteria if c.status == "not_met"}
        expected = "escalated" if open_ids - supplied else "approved"
        assert case.label.expected_final == expected, case.label.case_id


def test_supplemental_documents_are_new_and_spans_verbatim(split_cases):
    _, cases = split_cases
    for case in cases:
        docs = case.supplemental["documents"]
        assert not set(docs) & set(case.chart)
        for criterion in case.label.supplemental:
            assert criterion.status == "met" and criterion.evidence
            for ev in criterion.evidence:
                assert ev.verify(docs)
            assert case.supplemental["provides"][criterion.section_ref]


def test_payer_rules_accept_every_labeled_met_evidence(split_cases):
    from authpilot.payer_mock.reviewer import CONTENT_RULES
    from authpilot.policies import find_policy

    _, cases = split_cases
    for case in cases:
        policy = find_policy(case.order.payer_id, case.order.procedure_code)
        for criterion in [*case.label.criteria, *case.label.supplemental]:
            rule = CONTENT_RULES.get((policy.policy_id, criterion.section_ref))
            if criterion.status != "met" or rule is None:
                continue
            text = policy.section(criterion.section_ref).text
            assert any(rule(e.span_text, text, case.order.request_date) for e in criterion.evidence), \
                (case.label.case_id, criterion.criterion_id)


def test_procedures_are_balanced(split_cases):
    _, cases = split_cases
    counts = Counter(case.label.procedure for case in cases)
    assert counts["lumbar_mri"] == counts["biologic"]


def test_each_hard_case_type_present(split_cases):
    _, cases = split_cases
    tags = {tag for case in cases for tag in case.label.hard_case_tags}
    assert HARD_CASE_TAGS <= tags


def test_appeal_scenario_is_biologic_with_flowsheet_evidence(split_cases):
    _, cases = split_cases
    appeal = [c for c in cases if c.label.expected_outcome == "deny_then_appeal_approve"]
    assert appeal
    for case in appeal:
        assert case.label.procedure == "biologic"
        das = next(c for c in case.label.criteria if c.criterion_id == "bio.disease_activity")
        assert all("flowsheet" in ev.doc_id for ev in das.evidence)


def test_chart_sizes(split_cases):
    _, cases = split_cases
    for case in cases:
        assert 3 <= len(case.chart) <= 6


_NUMBER_WORDS = "|".join(generator.NUMBER_WORDS.values())
_DRUGS = "|".join(n.split()[0] for pool in generator.NSAIDS.values() for n in pool)


def _template(sentence: str) -> str:
    s = sentence.lower()
    s = re.sub(r"\d{4}-\d{2}-\d{2}", "<date>", s)
    s = re.sub(rf"\b({_DRUGS})\b", "<drug>", s)
    s = re.sub(r"\d+(?:\.\d+)?", "#", s)
    s = re.sub(rf"\b({_NUMBER_WORDS})\b", "#", s)
    return re.sub(r"\b(left|right)\b", "<side>", s)


def _evidence_templates(cases) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    for case in cases:
        for criterion in [*case.label.criteria, *case.label.supplemental]:
            for ev in criterion.evidence:
                out[criterion.criterion_id].add(_template(ev.span_text))
    return out


def test_sealed_evidence_wording_never_appears_in_dev():
    dev = _evidence_templates(generator.generate_split("dev"))
    sealed = _evidence_templates(generator.generate_split("sealed"))
    dev_all = set().union(*dev.values())
    shared = {t for templates in sealed.values() for t in templates if t in dev_all}
    assert not shared


def test_dev_has_several_phrasings_per_criterion():
    dev = _evidence_templates(generator.generate_split("dev"))
    assert len(dev) == 8
    for criterion_id, templates in dev.items():
        assert len(templates) >= 3, criterion_id


def test_sealed_uses_its_own_document_titles():
    dev_titles = {text.splitlines()[0] for c in generator.generate_split("dev") for text in c.chart.values()}
    sealed_titles = {text.splitlines()[0] for c in generator.generate_split("sealed") for text in c.chart.values()}
    assert not dev_titles & sealed_titles


@pytest.mark.parametrize("split", ["dev", "sealed"])
def test_committed_files_match_generator(split):
    split_dir = config.CASES_DIR / split
    if not split_dir.exists():
        pytest.skip("cases not generated yet; run make data")
    cases = generator.generate_split(split)
    assert len(list(split_dir.iterdir())) == len(cases)
    for case in cases:
        case_dir = split_dir / case.label.case_id.replace(f"{split}_", "case_")
        for name, body in generator.case_files(case).items():
            assert (case_dir / name).read_text(encoding="utf-8") == body
        Order.model_validate(json.loads((case_dir / "order.json").read_text()))
        CaseLabel.model_validate(json.loads((case_dir / "labels.json").read_text()))
