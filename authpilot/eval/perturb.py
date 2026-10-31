"""Perturbations of the dev cases. Each returns modified (order, chart, label) triples whose labels
are recomputed for the change, plus an optional policy directory to use while running them.

- threshold: lumbar MRI policy 6 weeks -> 8 weeks; therapy under 8 weeks becomes not met.
- reworded: both policies rewritten with the same criteria, new wording, layout and numbering.
- noisy: documents reordered, non-evidence text abbreviated, irrelevant text and a document added.
- removed_evidence: in fully met cases, the documents holding one criterion's evidence are removed.
- unseen: the third procedure (GLP-1), never used in development.
"""

import random
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from authpilot import config, ehr, policies
from authpilot.eval.harness import load_split
from authpilot.schemas import CaseLabel, Chart, Evidence, Gap, LabeledCriterion
from authpilot.tools import check_criteria

REWORDED_DIR = Path(__file__).resolve().parent / "policies_reworded"
REWORDED_REFS = {
    "lumbar_mri": {"2.1": "3.2", "2.2": "3.4", "2.3": "3.1", "2.4": "3.3"},
    "biologic": {"2.1": "3.3", "2.2": "3.4", "2.3": "3.2", "2.4": "3.1"},
}
THRESHOLD_FROM, THRESHOLD_TO = "at least 6 weeks of conservative therapy", "at least 8 weeks of conservative therapy"
NOISE_LINE = "Chart reviewed for completeness; see prior encounters for additional context."
ABBREVIATIONS = [("Patient", "Pt"), ("patient", "pt"), ("without", "w/o"), ("with", "w/"), ("history", "hx")]
HANDOUT = ("PATIENT EDUCATION HANDOUT\nDate: 2026-09-01\nAuthor: Clinic Education Team\n\nGeneral:\n"
           "Keep a list of your medicines and bring it to every visit. Call the clinic if you have "
           "questions about scheduling. Free parking is available on level 2.\n")


@contextmanager
def policy_dir(path: Path | None) -> Iterator[None]:
    """Run with policies from another directory; caches are cleared on entry and exit."""
    if path is None:
        yield
        return
    old = config.POLICIES_DIR
    config.POLICIES_DIR = path
    policies.clear_cache()
    check_criteria.clear_criteria_cache()
    try:
        yield
    finally:
        config.POLICIES_DIR = old
        policies.clear_cache()
        check_criteria.clear_criteria_cache()


def _relabel(label: CaseLabel, statuses: dict[str, str], evidence: dict[str, list[Evidence]] | None = None,
             refs: dict[str, str] | None = None, note: str = "") -> CaseLabel:
    """New label with the given per-section statuses (keyed by the original section_ref)."""
    criteria, gaps = [], []
    for c in label.criteria:
        status = statuses.get(c.section_ref, c.status)
        ev = (evidence or {}).get(c.section_ref, c.evidence) if status != "not_met" else []
        ref = (refs or {}).get(c.section_ref, c.section_ref)
        criteria.append(LabeledCriterion(criterion_id=c.criterion_id, section_ref=ref, status=status, evidence=ev))
        if status != "met":
            gaps.append(Gap(criterion_id=c.criterion_id, description=f"{c.criterion_id} {status} after perturbation"))
    all_met = not gaps
    outcome = label.expected_outcome if all_met else "needs_evidence"
    if all_met and label.expected_outcome == "needs_evidence":
        outcome = "approve"
    changed = any(statuses.get(c.section_ref, c.status) != c.status for c in label.criteria)
    final = label.expected_final if not changed else ("approved" if all_met else "escalated")
    return label.model_copy(update={"criteria": criteria, "planted_gaps": gaps, "expected_outcome": outcome,
                                    "expected_final": final, "supplemental": [] if changed else label.supplemental,
                                    "notes": f"{label.notes}; perturbation={note}"})


def threshold(split: str = "dev", limit: int | None = None) -> tuple[list, Path, set[str]]:
    tmp = Path(tempfile.mkdtemp(prefix="authpilot_policy_t8_"))
    for path in config.POLICIES_DIR.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        if "PA-RAD-014" in text:
            assert THRESHOLD_FROM in text
            text = text.replace(THRESHOLD_FROM, THRESHOLD_TO).replace("version: 2026.1", "version: 2026.1-t8")
        (tmp / path.name).write_text(text, encoding="utf-8")
    cases, affected = [], set()
    for order, chart, label in load_split(split, limit):
        if label.procedure != "lumbar_mri":
            continue
        weeks = label.facts.get("therapy_weeks")
        therapy = next(c for c in label.criteria if c.section_ref == "2.1")
        statuses = {}
        # A contradictory case ("6 weeks of PT" vs "no PT") fails an 8-week rule under either reading.
        if therapy.status in ("met", "unclear") and isinstance(weeks, int) and weeks < 8:
            statuses["2.1"] = "not_met"
            affected.add(label.case_id)
        cases.append((order, chart, _relabel(label, statuses, note="threshold_8_weeks")))
    return cases, tmp, affected


def reworded(split: str = "dev", limit: int | None = None) -> tuple[list, Path]:
    cases = []
    for order, chart, label in load_split(split, limit):
        refs = REWORDED_REFS[label.procedure]
        cases.append((order, chart, _relabel(label, {}, refs=refs, note="reworded_policy")))
    return cases, REWORDED_DIR


def _base_chart(patient_id: str) -> Chart:
    ehr.clear_patient(patient_id)
    return ehr.load_chart(patient_id)


def _reanchor(chart: Chart, evidence: list[Evidence]) -> list[Evidence]:
    out = []
    for ev in evidence:
        start = chart[ev.doc_id].find(ev.span_text)
        if start < 0:
            raise AssertionError(f"evidence lost in perturbation: {ev.span_text!r}")
        out.append(Evidence(doc_id=ev.doc_id, span_text=ev.span_text, start=start, end=start + len(ev.span_text)))
    return out


def noisy(split: str = "dev", limit: int | None = None) -> list:
    cases = []
    for i, (order, _, label) in enumerate(load_split(split, limit)):
        rng = random.Random(config.EVAL_SEED + i)
        chart = _base_chart(order.patient_id)
        spans = [e.span_text for c in label.criteria for e in c.evidence]
        noisy_chart: Chart = {}
        for doc_id, text in chart.items():
            lines = text.split("\n")
            new_lines = []
            for j, line in enumerate(lines):
                if j >= 4 and line and not any(span in line for span in spans):
                    for old, new in ABBREVIATIONS:
                        line = line.replace(old + " ", new + " ")
                new_lines.append(line)
                if j == 3:
                    new_lines.append(NOISE_LINE)
            noisy_chart[doc_id] = "\n".join(new_lines)
        noisy_chart["doc_90_education_handout"] = HANDOUT
        items = list(noisy_chart.items())
        rng.shuffle(items)
        noisy_chart = dict(items)
        evidence = {c.section_ref: _reanchor(noisy_chart, c.evidence) for c in label.criteria}
        cases.append((order, noisy_chart, _relabel(label, {}, evidence=evidence, note="noisy_chart")))
    return cases


def removed_evidence(split: str = "dev", limit: int | None = None) -> tuple[list, set[str]]:
    cases, removed_refs = [], set()
    for i, (order, _, label) in enumerate(load_split(split, limit)):
        if any(c.status != "met" for c in label.criteria) or "appeal_scenario" in label.hard_case_tags:
            continue
        rng = random.Random(config.EVAL_SEED + 100 + i)
        target = rng.choice(label.criteria)
        drop = {e.doc_id for e in target.evidence}
        chart = {d: t for d, t in _base_chart(order.patient_id).items() if d not in drop}
        statuses, evidence = {}, {}
        for c in label.criteria:
            kept = [e for e in c.evidence if e.doc_id in chart]
            evidence[c.section_ref] = kept
            if not kept:
                statuses[c.section_ref] = "not_met"
                removed_refs.add(f"{label.case_id}:{c.section_ref}")
        cases.append((order, chart, _relabel(label, statuses, evidence=evidence, note=f"removed_{sorted(drop)}")))
    return cases, removed_refs


def unseen(limit: int | None = None) -> list:
    return load_split("unseen", limit)


def cleanup(path: Path) -> None:
    if path and path.exists() and path != REWORDED_DIR and str(path).startswith(tempfile.gettempdir()):
        shutil.rmtree(path, ignore_errors=True)
