"""Seeded cases for the unseen third procedure (GLP-1 for weight management).

This split exists only to test adaptation: the agent has no code for this procedure and its
policy is structured differently (criteria under "Eligibility requirements" and "Safety
requirements", no "Coverage criteria" section). It is never used for development or tuning.

Usage: python -m authpilot.data.unseen_generator
"""

import random
import shutil
from datetime import timedelta
from pathlib import Path

from authpilot import config
from authpilot.data.generator import (
    BASE_DATE, FEMALE_NAMES, LAST_NAMES, MALE_NAMES, MODE_STATUS, PAYER_ID, CaseBuilder, GeneratedCase,
    _add_filler_docs, _num, _vitals, case_files,
)
from authpilot.schemas import CaseLabel, Gap, LabeledCriterion, Order

CRITERIA = {"glp.bmi": "3.1", "glp.lifestyle": "3.2", "glp.mtc_screen": "4.1"}
SUPPORTED = {
    "glp.bmi": {"missing", "ambiguous"},
    "glp.lifestyle": {"missing", "ambiguous", "contradictory"},
    "glp.mtc_screen": {"missing", "distractor"},
}
GAPS = {
    ("glp.bmi", "missing"): "No BMI is documented.",
    ("glp.bmi", "ambiguous"): "Weight is described but BMI is not recorded.",
    ("glp.lifestyle", "missing"): "No diet and exercise program is documented.",
    ("glp.lifestyle", "ambiguous"): "Dieting is mentioned without a structured program or duration.",
    ("glp.lifestyle", "contradictory"): "Records conflict on participation in a weight-management program.",
    ("glp.mtc_screen", "missing"): "Thyroid cancer history screening is not documented.",
}
CASE_PLAN = ["clean"] * 4 + ["missing"] * 3 + ["ambiguous", "contradictory", "distractor"]
PROVIDERS = ["Dr. Huda Rahman, Endocrinology", "Dr. Kamal Aziz, Obesity Medicine"]


def _bmi(cb: CaseBuilder, note, mode: str) -> None:
    cid, rng = "glp.bmi", cb.rng
    if mode == "missing":
        return
    if mode == "ambiguous":
        note.add("Exam:", "Patient reports steady weight gain over two years; BMI not recorded today.", cid)
        return
    if rng.random() < 0.6:
        bmi = round(rng.uniform(30.5, 41.0), 1)
        cb.facts["bmi"] = bmi
        note.add("Exam:", rng.choice([f"BMI {bmi} kg/m2 recorded at today's visit.",
                                      f"Measured BMI today: {bmi}."]), cid)
    else:
        bmi = round(rng.uniform(27.2, 29.8), 1)
        cb.facts["bmi"] = bmi
        cb.facts["comorbidity"] = "hypertension"
        note.add("Exam:", f"BMI {bmi} kg/m2; established hypertension treated with amlodipine.", cid)


def _lifestyle(cb: CaseBuilder, note, mode: str) -> None:
    cid, rng = "glp.lifestyle", cb.rng
    if mode == "missing":
        return
    if mode == "ambiguous":
        note.add("History:", "Has tried dieting on and off over the years.", cid)
        return
    months = rng.randint(6, 12)
    cb.facts["lifestyle_months"] = months
    program = cb.doc("nutrition_summary", "NUTRITION PROGRAM SUMMARY", rng.randint(3, 20),
                     "Registered Dietitian", ["Program:"])
    program.add("Program:", rng.choice([
        f"Completed {_num(rng, months)} months of a supervised reduced-calorie diet and exercise program with under 5% weight loss.",
        f"Enrolled in structured lifestyle intervention (diet and physical activity) for {months} months; weight plateaued.",
    ]), cid)
    if mode == "contradictory":
        note.add("History:", "Patient has never joined a structured weight-management program.", cid)


def _mtc(cb: CaseBuilder, note, mode: str) -> None:
    cid = "glp.mtc_screen"
    if mode == "missing":
        return
    note.add("History:", cb.rng.choice([
        "No personal or family history of medullary thyroid carcinoma or MEN2.",
        "Denies personal or family history of medullary thyroid cancer and multiple endocrine neoplasia type 2.",
    ]), cid)
    if mode == "distractor":
        note.add("History:", "Her aunt was treated for papillary thyroid cancer.")


def _plan_modes(rng: random.Random, case_type: str) -> dict[str, str]:
    modes = {cid: "met" for cid in CRITERIA}
    if case_type == "clean":
        return modes
    target = rng.choice([cid for cid in CRITERIA if case_type in SUPPORTED[cid]])
    modes[target] = case_type
    return modes


def _case(rng: random.Random, index: int, case_type: str) -> GeneratedCase:
    case_id = f"unseen_{index:03d}"
    patient_id = f"PU{index:04d}"
    sex = rng.choice(["female", "male"])
    name = f"{rng.choice(FEMALE_NAMES if sex == 'female' else MALE_NAMES)} {rng.choice(LAST_NAMES)}"
    order_date = BASE_DATE + timedelta(days=rng.randint(0, 28))
    provider = rng.choice(PROVIDERS)
    order = Order(order_id=f"ORD-U-{index:04d}", patient_id=patient_id, payer_id=PAYER_ID, procedure_code="J3490",
                  procedure_name="Semaglutide 2.4 mg weekly injection for chronic weight management",
                  ordering_provider=provider, request_date=order_date)
    modes = _plan_modes(rng, case_type)
    cb = CaseBuilder(rng, order_date, f"Patient: {name} ({patient_id})", "unseen")
    cb.facts["order_date"] = order_date.isoformat()
    note = cb.doc("weight_visit", "WEIGHT MANAGEMENT VISIT", rng.randint(1, 10), provider, ["History:", "Exam:", "Plan:"])
    note.add("History:", f"{rng.randint(25, 65)}-year-old {sex} seeking treatment for obesity.")
    note.add("Exam:", _vitals(rng))
    note.add("Plan:", "Start semaglutide 2.4 mg weekly with dose escalation, pending authorization.")
    _bmi(cb, note, modes["glp.bmi"])
    _lifestyle(cb, note, modes["glp.lifestyle"])
    _mtc(cb, note, modes["glp.mtc_screen"])
    _add_filler_docs(cb)
    chart, evidence = cb.finalize()

    criteria, gaps = [], []
    for cid, ref in CRITERIA.items():
        status = MODE_STATUS[modes[cid]]
        found = evidence.get(cid, [])
        if (status == "not_met") == bool(found):
            raise AssertionError(f"{case_id}: {cid} evidence does not match status {status}")
        criteria.append(LabeledCriterion(criterion_id=cid, section_ref=ref, status=status, evidence=found))
        if status != "met":
            gaps.append(Gap(criterion_id=cid, description=GAPS[(cid, modes[cid])]))
    all_met = not gaps
    label = CaseLabel(
        case_id=case_id, split="unseen", procedure="glp1", criteria=criteria, planted_gaps=gaps,
        expected_outcome="approve" if all_met else "needs_evidence",
        expected_final="approved" if all_met else "escalated",
        hard_case_tags=[] if case_type == "clean" else [case_type], facts=cb.facts,
        notes=f"case_type={case_type}",
    )
    return GeneratedCase(order=order, chart=chart, label=label)


def generate_unseen() -> list[GeneratedCase]:
    rng = random.Random(config.UNSEEN_SEED)
    plan = list(CASE_PLAN)
    rng.shuffle(plan)
    return [_case(rng, i, case_type) for i, case_type in enumerate(plan)]


def write_unseen(out_root: Path = config.CASES_DIR) -> Path:
    split_dir = Path(out_root) / "unseen"
    if split_dir.exists():
        shutil.rmtree(split_dir)
    for case in generate_unseen():
        case_dir = split_dir / case.label.case_id.replace("unseen_", "case_")
        case_dir.mkdir(parents=True)
        for name, body in case_files(case).items():
            (case_dir / name).write_text(body, encoding="utf-8")
    return split_dir


if __name__ == "__main__":
    print(f"wrote {config.UNSEEN_CASES} unseen cases to {write_unseen()}")
