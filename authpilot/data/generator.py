"""Seeded synthetic case generator.

Every case is built from phrase templates. Sentences that carry evidence are tagged with the
criterion they support, and their character offsets are recorded while the document text is
rendered, so every label span equals chart[doc_id][start:end] by construction.

Every evidence phrasing has a dev pool and a disjoint sealed pool (cb.pick), and the sealed split
also uses its own document titles, section headings and drug names. A method that memorizes the
dev wording therefore cannot score well on the sealed split by pattern matching alone.

All randomness comes from one random.Random(seed) per split. Nothing here reads global state.
"""

import argparse
import json
import random
import shutil
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from authpilot import config
from authpilot.schemas import CaseLabel, Chart, Evidence, Gap, LabeledCriterion, Order

PAYER_ID = "payer_a"
BASE_DATE = date(2026, 10, 1)

PROCEDURES = {
    "lumbar_mri": {
        "code": "72148",
        "name": "MRI lumbar spine without contrast",
        "criteria": {
            "mri.conservative_therapy": "2.1",
            "mri.red_flags": "2.2",
            "mri.neuro_exam": "2.3",
            "mri.no_recent_imaging": "2.4",
        },
    },
    "biologic": {
        "code": "J0135",
        "name": "Adalimumab 40 mg subcutaneous injection",
        "criteria": {
            "bio.ra_diagnosis": "2.1",
            "bio.mtx_failure": "2.2",
            "bio.tb_screening": "2.3",
            "bio.disease_activity": "2.4",
        },
    },
}

SUPPORTED_MODES = {
    "mri.conservative_therapy": {"missing", "ambiguous", "contradictory", "distractor"},
    "mri.red_flags": {"missing", "ambiguous", "contradictory", "distractor"},
    "mri.neuro_exam": {"missing", "ambiguous", "distractor"},
    "mri.no_recent_imaging": {"missing", "contradictory", "distractor"},
    "bio.ra_diagnosis": {"missing", "ambiguous", "distractor"},
    "bio.mtx_failure": {"missing", "ambiguous", "contradictory", "distractor"},
    "bio.tb_screening": {"missing", "ambiguous", "distractor"},
    "bio.disease_activity": {"missing", "ambiguous", "distractor"},
}

MODE_STATUS = {
    "met": "met",
    "distractor": "met",
    "missing": "not_met",
    "ambiguous": "unclear",
    "contradictory": "unclear",
}

GAP_TEXT = {
    "mri.conservative_therapy": {
        "missing": "No documentation of conservative therapy and its duration.",
        "ambiguous": "Conservative therapy is mentioned but its duration is not documented.",
        "contradictory": "Records conflict on whether conservative therapy was completed.",
    },
    "mri.red_flags": {
        "missing": "Red-flag symptom screening is not documented.",
        "ambiguous": "A possible red-flag symptom is mentioned and needs clarification.",
        "contradictory": "Records conflict on the presence of red-flag symptoms.",
    },
    "mri.neuro_exam": {
        "missing": "No lower extremity neurological examination is documented.",
        "ambiguous": "The neurological examination is documented as incomplete.",
    },
    "mri.no_recent_imaging": {
        "missing": "No imaging history is documented.",
        "contradictory": "Records conflict on whether a lumbar MRI was done in the last 12 months.",
    },
    "bio.ra_diagnosis": {
        "missing": "No rheumatologist-confirmed rheumatoid arthritis diagnosis is documented.",
        "ambiguous": "The rheumatology impression does not commit to rheumatoid arthritis.",
    },
    "bio.mtx_failure": {
        "missing": "No methotrexate trial is documented.",
        "ambiguous": "Methotrexate is mentioned without dose, duration or outcome.",
        "contradictory": "Records conflict on whether methotrexate was ever prescribed.",
    },
    "bio.tb_screening": {
        "missing": "No tuberculosis screening result is documented.",
        "ambiguous": "The tuberculosis screening result is indeterminate.",
    },
    "bio.disease_activity": {
        "missing": "No DAS28 score is documented.",
        "ambiguous": "Disease activity is described without a DAS28 score.",
    },
}

# Share of each case type in a split. "clean" absorbs rounding.
CASE_MIX = {
    "missing": 0.25,
    "ambiguous": 0.15,
    "contradictory": 0.15,
    "distractor": 0.10,
    "appeal": 0.05,
}
CASE_TYPES = ("clean", *CASE_MIX)

NUMBER_WORDS = {
    3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine",
    10: "ten", 11: "eleven", 12: "twelve",
}

FEMALE_NAMES = ["Amal", "Dana", "Hala", "Layla", "Noor", "Sara", "Yara", "Reem", "Lina", "Mona"]
MALE_NAMES = ["Basil", "Faisal", "Karim", "Majed", "Rami", "Tariq", "Ziad", "Hadi", "Nabil", "Sami"]
LAST_NAMES = [
    "Alnour", "Bakri", "Darwish", "Fahad", "Hamdan", "Jaber",
    "Khalil", "Mansour", "Nasser", "Qasim", "Saleh", "Zaid",
]
PRIMARY_PROVIDERS = [
    "Dr. Lina Haddad, Family Medicine",
    "Dr. Omar Faris, Family Medicine",
    "Dr. Rana Sabbagh, Orthopedics",
    "Dr. Hisham Qadri, Orthopedics",
]
RHEUMATOLOGISTS = [
    "Dr. Salma Idris, Rheumatology",
    "Dr. Youssef Amin, Rheumatology",
    "Dr. Nadia Karam, Rheumatology",
]

BACK_PAIN = [
    "low back pain radiating to the left leg",
    "chronic lower back pain with right-sided sciatica",
    "lumbar pain with intermittent radicular symptoms",
    "axial low back pain and numbness down the left leg",
]
SOCIAL = [
    "Works as an office administrator.",
    "Non-smoker, drinks alcohol rarely.",
    "Lives with family and is independent in daily activities.",
    "Works in warehouse logistics with frequent lifting.",
]
MRI_PLAN = [
    "Plan: MRI lumbar spine without contrast to evaluate for nerve root compression.",
    "Ordering lumbar spine MRI without contrast given persistent radicular symptoms.",
    "Will obtain MRI of the lumbar spine without contrast to guide further management.",
]
NSAIDS = {
    "dev": ["naproxen 500 mg twice daily", "ibuprofen 600 mg three times daily", "meloxicam 15 mg daily"],
    "sealed": ["diclofenac 75 mg twice daily", "celecoxib 200 mg daily", "etodolac 400 mg twice daily"],
}
FILLER_MEDS = ["Lisinopril 10 mg daily.", "Atorvastatin 20 mg nightly.", "Vitamin D 1000 IU daily."]
PORTAL_MESSAGES = [
    "Patient asks whether the appointment can be moved to the morning.",
    "Patient confirms that insurance details are unchanged.",
    "Patient requests a copy of the visit summary.",
]

SEALED_TITLES = {
    "PROGRESS NOTE": "CLINIC VISIT NOTE",
    "PHYSICAL THERAPY DISCHARGE SUMMARY": "PT DISCHARGE NOTE",
    "PHYSICAL THERAPY INITIAL EVALUATION": "PT INTAKE ASSESSMENT",
    "IMAGING HISTORY": "RADIOLOGY HISTORY",
    "OUTSIDE RECORDS SUMMARY": "EXTERNAL RECORDS",
    "NURSING TRIAGE NOTE": "TRIAGE INTAKE",
    "RHEUMATOLOGY CONSULTATION": "RHEUMATOLOGY CLINIC NOTE",
    "LABORATORY RESULTS": "LAB REPORT",
    "MEDICATION HISTORY": "PHARMACY FILL HISTORY",
    "REFERRAL NOTE": "REFERRAL REQUEST",
    "RHEUMATOLOGY FLOWSHEET": "DISEASE ACTIVITY FLOWSHEET",
    "PATIENT PORTAL MESSAGE": "SECURE MESSAGE",
    "MEDICATION LIST": "CURRENT MEDICATIONS",
    "PROGRESS NOTE ADDENDUM": "CLINIC NOTE ADDENDUM",
    "RHEUMATOLOGY ADDENDUM": "RHEUMATOLOGY NOTE ADDENDUM",
}

# Probability that the clinic can supply a missing document when the agent asks for it.
SUPPLEMENT_RATE = 0.7
SEALED_HEADINGS = {
    "Subjective:": "HPI:",
    "Objective:": "Exam:",
    "Assessment and Plan:": "Impression/Plan:",
    "Evaluation:": "Intake:",
    "Summary:": "Discharge:",
    "Prior studies:": "Studies on file:",
    "Records received:": "Received:",
    "Triage:": "Intake notes:",
    "History:": "Background:",
    "Exam:": "Findings:",
    "Assessment:": "Impression:",
    "Plan:": "Next steps:",
    "Results:": "Values:",
    "Medications:": "Fills:",
    "Reason for referral:": "Question:",
    "Measures:": "Scores:",
    "Message:": "Body:",
    "Active medications:": "Medications:",
}


@dataclass
class DocBuilder:
    kind: str
    title: str
    when: date
    author: str
    sections: dict[str, list[tuple[str, str | None]]] = field(default_factory=dict)

    def add(self, section: str, sentence: str, criterion_id: str | None = None) -> None:
        self.sections.setdefault(section, []).append((sentence, criterion_id))

    def is_empty(self) -> bool:
        return not any(self.sections.values())

    def render(self, rng: random.Random, patient_line: str, titles: dict[str, str],
               headings: dict[str, str]) -> tuple[str, list[tuple[str, int, int]]]:
        """Return document text and (criterion_id, start, end) spans. The first sentence of
        each section stays in place; the rest are shuffled to vary ordering."""
        title = titles.get(self.title, self.title)
        text = f"{title}\nDate: {self.when.isoformat()}\nAuthor: {self.author}\n{patient_line}\n"
        spans: list[tuple[str, int, int]] = []
        for heading, items in self.sections.items():
            if not items:
                continue
            head, rest = items[:1], items[1:]
            rng.shuffle(rest)
            text += f"\n{headings.get(heading, heading)}\n"
            for i, (sentence, criterion_id) in enumerate(head + rest):
                if i:
                    text += " "
                start = len(text)
                text += sentence
                if criterion_id:
                    spans.append((criterion_id, start, len(text)))
            text += "\n"
        return text, spans


class CaseBuilder:
    def __init__(self, rng: random.Random, order_date: date, patient_line: str, split: str):
        self.rng = rng
        self.order_date = order_date
        self.patient_line = patient_line
        self.split = split
        self.docs: dict[str, DocBuilder] = {}
        self.facts: dict[str, int | float | str | bool] = {}

    @property
    def sealed(self) -> bool:
        return self.split == "sealed"

    def pick(self, dev: list[str], sealed: list[str]) -> str:
        return self.rng.choice(sealed if self.sealed else dev)

    def doc(self, kind: str, title: str, days_before: int, author: str, sections: list[str]) -> DocBuilder:
        if kind not in self.docs:
            self.docs[kind] = DocBuilder(
                kind, title, self.order_date - timedelta(days=days_before), author,
                {heading: [] for heading in sections},
            )
        return self.docs[kind]

    def months_ago(self, months: int) -> date:
        return self.order_date - timedelta(days=months * 30 + self.rng.randint(0, 10))

    def finalize(self, start_index: int = 1) -> tuple[Chart, dict[str, list[Evidence]]]:
        titles = SEALED_TITLES if self.sealed else {}
        headings = SEALED_HEADINGS if self.sealed else {}
        kinds = [kind for kind, doc in self.docs.items() if not doc.is_empty()]
        self.rng.shuffle(kinds)
        chart: Chart = {}
        evidence: dict[str, list[Evidence]] = defaultdict(list)
        for i, kind in enumerate(kinds, start_index):
            doc_id = f"doc_{i:02d}_{kind}"
            text, spans = self.docs[kind].render(self.rng, self.patient_line, titles, headings)
            chart[doc_id] = text
            for criterion_id, start, end in spans:
                evidence[criterion_id].append(
                    Evidence(doc_id=doc_id, span_text=text[start:end], start=start, end=end)
                )
        return chart, evidence


def _num(rng: random.Random, n: int) -> str:
    return NUMBER_WORDS[n] if n in NUMBER_WORDS and rng.random() < 0.4 else str(n)


def _vitals(rng: random.Random) -> str:
    return (
        f"BP {rng.randint(112, 142)}/{rng.randint(70, 90)}, HR {rng.randint(62, 92)}, "
        f"temperature {rng.choice(['36.6', '36.8', '37.0'])} C."
    )


# Lumbar spine MRI criteria ---------------------------------------------------------------


def _mri_conservative_therapy(cb: CaseBuilder, note: DocBuilder, mode: str) -> None:
    cid, rng = "mri.conservative_therapy", cb.rng
    if mode == "missing":
        if rng.random() < 0.5:
            note.add("Assessment and Plan:", cb.pick(
                ["Consider a course of physical therapy if symptoms persist."],
                ["Will refer to physiotherapy if no improvement.",
                 "Discussed home stretches; formal therapy not yet tried."],
            ))
        return
    if mode == "ambiguous":
        note.add("Subjective:", cb.pick(
            ["Has tried physical therapy for several weeks with partial relief.",
             "Reports some physical therapy in the past; duration unknown.",
             "Completed a short course of PT recently without much change."],
            ["Did some PT at another clinic, unsure how long.",
             "Tried anti-inflammatories on and off without a consistent course.",
             "Physical therapy started at some point; no discharge summary available."],
        ), cid)
        return

    weeks = rng.randint(6, 12)
    cb.facts["therapy_weeks"] = weeks
    w = _num(rng, weeks)
    if mode == "contradictory":
        note.add("Subjective:", cb.pick(
            [f"Completed {w} weeks of physical therapy without improvement."],
            [f"Reports finishing {w} weeks of PT before this visit."],
        ), cid)
        pt = cb.doc("pt_note", "PHYSICAL THERAPY INITIAL EVALUATION", rng.randint(1, 5),
                    "Physical Therapy Department", ["Evaluation:"])
        pt.add("Evaluation:", cb.pick(
            ["Patient reports no prior physical therapy for this episode of back pain."],
            ["First PT visit today; patient has never attended therapy for this back pain."],
        ), cid)
        pt.add("Evaluation:", "Lumbar flexion limited by pain.")
        return

    if rng.random() < 0.6:
        cb.facts["therapy_type"] = "physical_therapy"
        visits, pain = weeks * 2, rng.randint(5, 8)
        sealed_pt = [
            f"Supervised PT x {weeks} wks ({visits} sessions), plateaued without durable relief.",
            f"Course of physiotherapy over {w} weeks ended with persistent radicular pain.",
            f"Status post {w} weeks of formal rehabilitation without functional improvement.",
            f"Pt finished a {weeks}-week rehab program; pain still {pain}/10 with sitting.",
        ]
        if weeks % 4 == 0:
            sealed_pt.append(f"Completed {_num(rng, weeks // 4)} months of physiotherapy with no lasting benefit.")
        pt = cb.doc("pt_note", "PHYSICAL THERAPY DISCHARGE SUMMARY", rng.randint(3, 14),
                    "Physical Therapy Department", ["Summary:"])
        pt.add("Summary:", cb.pick(
            [f"Patient completed {w} weeks of supervised physical therapy with minimal improvement in pain.",
             f"Discharged from PT after {w} weeks ({visits} visits); pain persists at {pain}/10.",
             f"A {weeks}-week course of physical therapy was completed without meaningful functional gain.",
             f"Attended physical therapy twice weekly for {w} weeks; symptoms unchanged at discharge."],
            sealed_pt,
        ), cid)
        pt.add("Summary:", "Home exercise program reviewed.")
    else:
        cb.facts["therapy_type"] = "nsaid"
        nsaid = rng.choice(NSAIDS[cb.split])
        note.add("Subjective:", cb.pick(
            [f"Trialed {nsaid} for {w} weeks without adequate relief.",
             f"Has taken {nsaid} for {w} weeks with no meaningful improvement."],
            [f"Failed {weeks} wks of scheduled {nsaid}.",
             f"On {nsaid} for the past {w} weeks with minimal benefit.",
             f"{weeks}-week NSAID trial ({nsaid}) gave no lasting relief."],
        ), cid)
    if mode == "distractor":
        note.add("Subjective:", cb.pick(
            ["Her sister completed twelve weeks of physical therapy for a similar problem."],
            ["Spouse is currently doing 10 weeks of PT for a knee injury."],
        ))


def _mri_red_flags(cb: CaseBuilder, note: DocBuilder, mode: str) -> None:
    cid, rng = "mri.red_flags", cb.rng
    if mode == "missing":
        return
    if mode == "ambiguous":
        note.add("Subjective:", cb.pick(
            ["Reports occasional numbness in the groin area; unclear whether this is new."],
            ["Mentions some tingling around the inner thighs, could not characterize further.",
             "Possible intermittent urinary urgency; patient vague on details."],
        ), cid)
        return
    note.add("Subjective:", cb.pick(
        ["Denies bowel or bladder incontinence, saddle anesthesia, fever, or unintentional weight loss.",
         "No red-flag symptoms: no saddle anesthesia, no urinary retention, no history of cancer.",
         "Red flags screened and negative (no cauda equina symptoms, fever or weight loss).",
         "Negative review for saddle anesthesia, urinary retention, fever and weight loss."],
        ["ROS: no B/B dysfunction, no saddle numbness, afebrile, weight stable.",
         "Cauda equina screen negative; afebrile, no history of malignancy.",
         "Specifically denies incontinence, perineal numbness, night sweats or weight loss."],
    ), cid)
    if mode == "contradictory":
        triage = cb.doc("nursing_triage", "NURSING TRIAGE NOTE", rng.randint(0, 3), "Triage Nurse", ["Triage:"])
        triage.add("Triage:", cb.pick(
            ["Patient reports new urinary incontinence since last week."],
            ["Patient states two episodes of bladder leakage this week.",
             "New-onset perineal numbness reported at triage."],
        ), cid)
        triage.add("Triage:", _vitals(rng))
    elif mode == "distractor":
        note.add("Subjective:", cb.pick(
            ["Family history: father treated for prostate cancer."],
            ["Aunt recently diagnosed with spinal metastases."],
        ))


def _mri_neuro_exam(cb: CaseBuilder, note: DocBuilder, mode: str) -> None:
    cid, rng = "mri.neuro_exam", cb.rng
    if mode == "missing":
        if rng.random() < 0.5:
            note.add("Objective:", cb.pick(
                ["Physical exam deferred to specialist visit."],
                ["No exam performed at this telehealth visit."],
            ))
        return
    if mode == "ambiguous":
        note.add("Objective:", cb.pick(
            ["Exam limited by pain; neurologic examination not completed."],
            ["Patient declined full exam due to pain; partial assessment only.",
             "Neuro exam attempted but unreliable because of guarding."],
        ), cid)
        return
    side = rng.choice(["left", "right"])
    degrees = rng.choice([30, 40, 45, 50])
    note.add("Objective:", cb.pick(
        ["Neurological exam: strength 5/5 in bilateral lower extremities, patellar and Achilles reflexes 2+ and symmetric, sensation intact.",
         f"Neuro: positive straight-leg raise on the {side} at {degrees} degrees, diminished sensation in the {side} L5 dermatome.",
         "Lower extremity neurologic examination: reflexes symmetric, no motor deficit, straight-leg raise negative.",
         "Neuro: patellar reflexes 2+ bilaterally, dorsiflexion strength 5/5, sensation grossly intact."],
        ["LE neuro: 5/5 throughout, DTRs symmetric, SLR negative bilaterally.",
         f"Focused neurologic exam shows {side} EHL weakness 4/5 and an absent {side} ankle jerk.",
         "Motor, sensory and reflex testing of both legs documented as normal."],
    ), cid)
    if mode == "distractor":
        note.add("Objective:", cb.pick(
            ["Neurologic exam at a 2019 emergency visit for a head injury was normal."],
            ["Cranial nerve exam at a 2020 neurology consult for migraine was normal."],
        ))


def _mri_no_recent_imaging(cb: CaseBuilder, note: DocBuilder, mode: str) -> None:
    cid, rng = "mri.no_recent_imaging", cb.rng
    if mode == "missing":
        return
    imaging = cb.doc("imaging_history", "IMAGING HISTORY", rng.randint(0, 5), "Radiology Records", ["Prior studies:"])
    if mode == "contradictory":
        imaging.add("Prior studies:", cb.pick(
            ["No prior lumbar spine imaging on record."],
            ["Imaging history: none on file."],
        ), cid)
        months = rng.randint(3, 10)
        cb.facts["last_mri_months_ago"] = months
        when = cb.months_ago(months).isoformat()
        outside = cb.doc("outside_records", "OUTSIDE RECORDS SUMMARY", rng.randint(0, 5),
                         "Health Information Management", ["Records received:"])
        outside.add("Records received:", cb.pick(
            [f"Lumbar spine MRI performed on {when} at an outside facility."],
            [f"Outside report: MRI L-spine {when}, mild disc bulge at L4-5."],
        ), cid)
        return
    variant = rng.randrange(3)
    if variant == 0:
        imaging.add("Prior studies:", cb.pick(
            ["No prior lumbar spine imaging on record."],
            ["No lumbar MRI found in the regional imaging exchange."],
        ), cid)
    elif variant == 1:
        months = rng.randint(14, 60)
        cb.facts["last_mri_months_ago"] = months
        when = cb.months_ago(months).isoformat()
        imaging.add("Prior studies:", cb.pick(
            [f"Last lumbar spine MRI: {when} ({months} months before this request).",
             f"Imaging review: lumbar MRI last done {when}, {months} months ago."],
            [f"Most recent lumbar MRI was {when}."],
        ), cid)
    else:
        when = cb.months_ago(rng.randint(2, 8)).isoformat()
        imaging.add("Prior studies:", cb.pick(
            [f"Lumbar radiographs only ({when}); no prior MRI."],
            [f"Only plain films of the lumbar spine on file ({when}); MRI never performed."],
        ), cid)
    if mode == "distractor":
        note.add("Subjective:", cb.pick(
            ["Her brother had a lumbar MRI last month for a disc herniation."],
            ["Her husband had an MRI of the spine in the spring."],
        ))


def _build_lumbar_mri(cb: CaseBuilder, modes: dict[str, str], provider: str, age: int, sex: str) -> None:
    rng = cb.rng
    note = cb.doc("progress_note", "PROGRESS NOTE", rng.randint(1, 7), provider,
                  ["Subjective:", "Objective:", "Assessment and Plan:"])
    note.add("Subjective:", f"{age}-year-old {sex} with {rng.choice(BACK_PAIN)} for {rng.randint(8, 20)} weeks.")
    note.add("Subjective:", rng.choice(SOCIAL))
    note.add("Objective:", _vitals(rng))
    note.add("Assessment and Plan:", rng.choice(MRI_PLAN))
    _mri_conservative_therapy(cb, note, modes["mri.conservative_therapy"])
    _mri_red_flags(cb, note, modes["mri.red_flags"])
    _mri_neuro_exam(cb, note, modes["mri.neuro_exam"])
    _mri_no_recent_imaging(cb, note, modes["mri.no_recent_imaging"])


# Biologic (adalimumab for RA) criteria -----------------------------------------------------


def _bio_ra_diagnosis(cb: CaseBuilder, consult: DocBuilder, mode: str) -> None:
    cid, rng = "bio.ra_diagnosis", cb.rng
    if mode == "missing":
        referral = cb.doc("referral_note", "REFERRAL NOTE", rng.randint(30, 90),
                          rng.choice(PRIMARY_PROVIDERS[:2]), ["Reason for referral:"])
        referral.add("Reason for referral:", cb.pick(
            ["Possible inflammatory arthritis; referral to rheumatology placed."],
            ["Joint pain and morning stiffness, please evaluate for inflammatory arthritis."],
        ))
        consult.add("Assessment:", cb.pick(["Findings discussed with the patient."], ["Plan discussed in detail."]))
        return
    if mode == "ambiguous":
        consult.add("Assessment:", cb.pick(
            ["Rheumatology impression: inflammatory polyarthritis, rheumatoid arthritis versus psoriatic arthritis."],
            ["Undifferentiated inflammatory arthritis; RA not yet confirmed.",
             "Working diagnosis: early inflammatory arthritis, possibly RA."],
        ), cid)
        return
    consult.add("Assessment:", cb.pick(
        ["Assessment: seropositive rheumatoid arthritis (ICD-10 M05.79), confirmed by rheumatology.",
         "Rheumatology impression: rheumatoid arthritis meeting 2010 ACR/EULAR classification criteria.",
         "Diagnosis: rheumatoid arthritis, RF and anti-CCP positive, confirmed on rheumatology evaluation.",
         "Rheumatoid arthritis, seropositive, confirmed by rheumatology on examination and serology."],
        ["Impression: seropositive RA (M05.79), confirmed at this rheumatology visit.",
         "Seropositive erosive rheumatoid arthritis, diagnosis established by rheumatology today.",
         "Meets ACR/EULAR criteria for RA (score 8/10) on rheumatology assessment."],
    ), cid)
    if mode == "distractor":
        consult.add("History:", cb.pick(
            ["Mother has rheumatoid arthritis treated with adalimumab."],
            ["Sister has RA and is doing well on a biologic."],
        ))


def _bio_mtx_failure(cb: CaseBuilder, consult: DocBuilder, meds: DocBuilder, mode: str) -> None:
    cid, rng = "bio.mtx_failure", cb.rng
    if mode == "missing":
        return
    if mode == "ambiguous":
        consult.add("History:", cb.pick(
            ["Tried methotrexate in the past; dose and duration not available."],
            ["Prior methotrexate use reported by patient; records unavailable.",
             "Was on a weekly arthritis pill previously, likely methotrexate."],
        ), cid)
        return
    dose = rng.choice(["15", "17.5", "20", "25"])
    if mode != "contradictory" and rng.random() < 0.25:
        weeks = rng.randint(4, 10)
        cb.facts["mtx_intolerance"] = True
        consult.add("History:", cb.pick(
            [f"Methotrexate {dose} mg weekly was stopped after {_num(rng, weeks)} weeks because of transaminase elevation (intolerance)."],
            [f"MTX discontinued after {weeks} wks owing to persistent nausea and elevated LFTs."],
        ), cid)
    else:
        months = rng.randint(3, 9)
        cb.facts["mtx_months"] = months
        m = _num(rng, months)
        consult.add("History:", cb.pick(
            [f"Methotrexate {dose} mg weekly for {m} months with inadequate response.",
             f"Failed methotrexate after {m} months at {dose} mg weekly; joint counts unchanged.",
             f"Has been on methotrexate {dose} mg weekly for {m} months with persistent synovitis.",
             f"Took methotrexate {dose} mg every week for {m} months; disease still active."],
            [f"MTX {dose} mg/wk x {months} mo, inadequate response.",
             f"Despite {m} months of weekly methotrexate at {dose} mg, synovitis persists.",
             f"Methotrexate titrated to {dose} mg weekly; no meaningful improvement after {m} months."],
        ), cid)
    if mode == "contradictory":
        meds.add("Medications:", cb.pick(
            ["No prior conventional DMARD therapy on record."],
            ["Pharmacy fill history shows no methotrexate dispensed in the past 3 years."],
        ), cid)
    elif mode == "distractor":
        consult.add("History:", cb.pick(
            ["Her mother was treated with methotrexate for psoriasis."],
            ["Husband takes methotrexate for psoriatic arthritis."],
        ))


def _bio_tb_screening(cb: CaseBuilder, consult: DocBuilder, labs: DocBuilder, mode: str) -> None:
    cid, rng = "bio.tb_screening", cb.rng
    if mode == "missing":
        return
    months = rng.randint(1, 11)
    cb.facts["tb_months_ago"] = months
    collected = cb.months_ago(months).isoformat()
    if mode == "ambiguous":
        labs.add("Results:", cb.pick(
            [f"QuantiFERON-TB Gold Plus: indeterminate (collected {collected})."],
            [f"QFT-Plus {collected}: result could not be interpreted, repeat advised.",
             f"TB skin test placed {collected}; never read."],
        ), cid)
        return
    labs.add("Results:", cb.pick(
        [f"QuantiFERON-TB Gold Plus: negative (collected {collected}).",
         f"Interferon-gamma release assay negative on {collected}.",
         f"TB screening (IGRA) {collected}: negative.",
         f"QuantiFERON result negative, drawn {collected}."],
        [f"IGRA (QFT-Plus) {collected}: neg.",
         f"Latent TB screen negative ({collected}, interferon-gamma release assay).",
         f"Tuberculin skin test read at 0 mm on {collected}."],
    ), cid)
    if mode == "distractor":
        consult.add("History:", cb.pick(
            ["Spouse completed treatment for latent tuberculosis in 2019."],
            ["Grandfather had TB decades ago."],
        ))


def _bio_disease_activity(cb: CaseBuilder, consult: DocBuilder, mode: str, appeal: bool) -> None:
    cid, rng = "bio.disease_activity", cb.rng
    if mode == "missing":
        return
    if mode == "ambiguous":
        consult.add("Exam:", cb.pick(
            ["Disease remains active per patient report."],
            ["Patient feels the arthritis is flaring.", "Joints look active; score not calculated today."],
        ), cid)
        return
    das = round(rng.uniform(3.6, 6.8), 1)
    cb.facts["das28"] = das
    level = "high" if das > 5.1 else "moderate"
    if appeal:
        consult.add("Exam:", cb.pick(["Disease activity remains high despite therapy."],
                                     ["Activity remains uncontrolled."]))
        flowsheet = cb.doc("rheumatology_flowsheet", "RHEUMATOLOGY FLOWSHEET", rng.randint(1, 10),
                           "Rheumatology Clinic", ["Measures:"])
        flowsheet.add("Measures:", cb.pick(
            [f"DAS28-CRP {das} recorded at the most recent visit ({level} disease activity)."],
            [f"DAS28 {das} on the last flowsheet entry."],
        ), cid)
        flowsheet.add("Measures:", f"Patient global assessment {rng.randint(5, 9)}/10.")
        return
    consult.add("Exam:", cb.pick(
        [f"DAS28-CRP today: {das} ({level} disease activity).",
         f"Disease activity: DAS28-ESR {das}.",
         f"DAS28 score {das}, consistent with {level} disease activity.",
         f"DAS28-CRP {das} at today's visit."],
        [f"DAS28-ESR calculated at {das}.",
         f"Composite disease activity (DAS28) = {das}.",
         f"Today's DAS28 {das} ({level})."],
    ), cid)
    if mode == "distractor":
        consult.add("History:", cb.pick(
            ["DAS28 was 2.4 during a period of remission in 2021."],
            ["DAS28 of 2.1 was recorded during remission two years ago."],
        ))


def _build_biologic(cb: CaseBuilder, modes: dict[str, str], provider: str, age: int, sex: str, appeal: bool) -> None:
    rng = cb.rng
    consult = cb.doc("rheumatology_consult", "RHEUMATOLOGY CONSULTATION", rng.randint(1, 10), provider,
                     ["History:", "Exam:", "Assessment:", "Plan:"])
    consult.add("History:", f"{age}-year-old {sex} with {rng.randint(1, 10)} years of symmetric small-joint polyarthritis.")
    consult.add("Exam:", f"Tender joint count {rng.randint(4, 14)}, swollen joint count {rng.randint(2, 10)}.")
    consult.add("Plan:", "Start adalimumab 40 mg subcutaneously every other week pending prior authorization.")
    labs = cb.doc("lab_results", "LABORATORY RESULTS", rng.randint(2, 10), "Clinical Laboratory", ["Results:"])
    labs.add("Results:", f"CRP {round(rng.uniform(8, 40), 1)} mg/L.")
    labs.add("Results:", rng.choice(["Rheumatoid factor positive.", "Anti-CCP antibodies positive.", "ESR 38 mm/h."]))
    meds = cb.doc("medication_history", "MEDICATION HISTORY", rng.randint(0, 5), "Pharmacy", ["Medications:"])
    meds.add("Medications:", rng.choice(["Folic acid 1 mg daily.", "Prednisone 5 mg daily.", "Omeprazole 20 mg daily."]))
    _bio_ra_diagnosis(cb, consult, modes["bio.ra_diagnosis"])
    _bio_mtx_failure(cb, consult, meds, modes["bio.mtx_failure"])
    _bio_tb_screening(cb, consult, labs, modes["bio.tb_screening"])
    _bio_disease_activity(cb, consult, modes["bio.disease_activity"], appeal)


def _add_filler_docs(cb: CaseBuilder) -> None:
    rng = cb.rng
    pool = ["patient_message", "medication_list", "nursing_triage"]
    rng.shuffle(pool)
    wanted = max(3 - len(cb.docs), 1 if rng.random() < 0.5 else 0)
    for kind in pool:
        if wanted <= 0 or len(cb.docs) >= 6:
            break
        if kind in cb.docs:
            continue
        if kind == "patient_message":
            doc = cb.doc(kind, "PATIENT PORTAL MESSAGE", rng.randint(0, 20), "Patient Portal", ["Message:"])
            doc.add("Message:", rng.choice(PORTAL_MESSAGES))
        elif kind == "medication_list":
            doc = cb.doc(kind, "MEDICATION LIST", rng.randint(0, 20), "Pharmacy", ["Active medications:"])
            for med in rng.sample(FILLER_MEDS, 2):
                doc.add("Active medications:", med)
        else:
            doc = cb.doc(kind, "NURSING TRIAGE NOTE", rng.randint(0, 3), "Triage Nurse", ["Triage:"])
            doc.add("Triage:", _vitals(rng))
            doc.add("Triage:", f"Pain score {rng.randint(3, 8)}/10.")
        wanted -= 1


# Case assembly ---------------------------------------------------------------------------


@dataclass
class GeneratedCase:
    order: Order
    chart: Chart
    label: CaseLabel
    supplemental: dict = field(default_factory=lambda: {"documents": {}, "provides": {}})


def _build_supplement(cb: CaseBuilder, procedure: str, provider: str, criterion_ids: list[str],
                      start_index: int) -> tuple[Chart, dict[str, list[Evidence]]]:
    """Documents the clinic can send later, written as if the missing evidence were met."""
    sub = CaseBuilder(cb.rng, cb.order_date, cb.patient_line, cb.split)
    if procedure == "lumbar_mri":
        note = sub.doc("progress_addendum", "PROGRESS NOTE ADDENDUM", 0, provider,
                       ["Subjective:", "Objective:", "Assessment and Plan:"])
        writers = {
            "mri.conservative_therapy": lambda: _mri_conservative_therapy(sub, note, "met"),
            "mri.red_flags": lambda: _mri_red_flags(sub, note, "met"),
            "mri.neuro_exam": lambda: _mri_neuro_exam(sub, note, "met"),
            "mri.no_recent_imaging": lambda: _mri_no_recent_imaging(sub, note, "met"),
        }
    else:
        consult = sub.doc("rheumatology_addendum", "RHEUMATOLOGY ADDENDUM", 0, provider,
                          ["History:", "Exam:", "Assessment:", "Plan:"])
        labs = sub.doc("lab_results", "LABORATORY RESULTS", 0, "Clinical Laboratory", ["Results:"])
        meds = sub.doc("medication_history", "MEDICATION HISTORY", 0, "Pharmacy", ["Medications:"])
        writers = {
            "bio.ra_diagnosis": lambda: _bio_ra_diagnosis(sub, consult, "met"),
            "bio.mtx_failure": lambda: _bio_mtx_failure(sub, consult, meds, "met"),
            "bio.tb_screening": lambda: _bio_tb_screening(sub, consult, labs, "met"),
            "bio.disease_activity": lambda: _bio_disease_activity(sub, consult, "met", appeal=False),
        }
    for cid in criterion_ids:
        writers[cid]()
    cb.facts.update(sub.facts)
    return sub.finalize(start_index=start_index)


def _plan_case_types(rng: random.Random, n: int) -> list[str]:
    counts = {case_type: round(share * n) for case_type, share in CASE_MIX.items()}
    counts["clean"] = n - sum(counts.values())
    types = [case_type for case_type in CASE_TYPES for _ in range(counts[case_type])]
    rng.shuffle(types)
    return types


def _plan_procedures(rng: random.Random, types: list[str]) -> list[str]:
    n = len(types)
    appeal_idx = [i for i, t in enumerate(types) if t == "appeal"]
    other_idx = [i for i, t in enumerate(types) if t != "appeal"]
    biologic = set(appeal_idx) | set(rng.sample(other_idx, n // 2 - len(appeal_idx)))
    return ["biologic" if i in biologic else "lumbar_mri" for i in range(n)]


def _plan_modes(rng: random.Random, procedure: str, case_type: str) -> dict[str, str]:
    criteria = list(PROCEDURES[procedure]["criteria"])
    modes = {cid: "met" for cid in criteria}
    if case_type in ("clean", "appeal"):
        return modes
    candidates = [cid for cid in criteria if case_type in SUPPORTED_MODES[cid]]
    targets = [rng.choice(candidates)]
    if case_type == "missing" and rng.random() < 0.25:
        targets.append(rng.choice([cid for cid in candidates if cid != targets[0]]))
    for cid in targets:
        modes[cid] = case_type
    return modes


def _expected_outcome(case_type: str, modes: dict[str, str]) -> str:
    if case_type == "appeal":
        return "deny_then_appeal_approve"
    if all(MODE_STATUS[mode] == "met" for mode in modes.values()):
        return "approve"
    return "needs_evidence"


def _generate_case(rng: random.Random, split: str, index: int, procedure: str, case_type: str) -> GeneratedCase:
    case_id = f"{split}_{index:03d}"
    prefix = split[0].upper()
    patient_id = f"P{prefix}{index:04d}"
    sex = rng.choice(["female", "male"])
    first = rng.choice(FEMALE_NAMES if sex == "female" else MALE_NAMES)
    patient_name = f"{first} {rng.choice(LAST_NAMES)}"
    age = rng.randint(28, 72)
    order_date = BASE_DATE + timedelta(days=rng.randint(0, 28))
    provider = rng.choice(RHEUMATOLOGISTS if procedure == "biologic" else PRIMARY_PROVIDERS)
    spec = PROCEDURES[procedure]

    order = Order(
        order_id=f"ORD-{prefix}-{index:04d}",
        patient_id=patient_id,
        payer_id=PAYER_ID,
        procedure_code=spec["code"],
        procedure_name=spec["name"],
        ordering_provider=provider,
        request_date=order_date,
    )

    modes = _plan_modes(rng, procedure, case_type)
    cb = CaseBuilder(rng, order_date, f"Patient: {patient_name} ({patient_id})", split)
    cb.facts["order_date"] = order_date.isoformat()
    if procedure == "lumbar_mri":
        _build_lumbar_mri(cb, modes, provider, age, sex)
    else:
        _build_biologic(cb, modes, provider, age, sex, appeal=case_type == "appeal")
    _add_filler_docs(cb)
    chart, evidence = cb.finalize()

    missing = [cid for cid, mode in modes.items() if mode == "missing"]
    supplied = [cid for cid in missing if rng.random() < SUPPLEMENT_RATE]
    supplemental = {"documents": {}, "provides": {}}
    supplemental_labels = []
    if supplied:
        sup_chart, sup_evidence = _build_supplement(cb, procedure, provider, supplied, len(chart) + 1)
        supplemental["documents"] = sup_chart
        for cid in supplied:
            found = sup_evidence.get(cid, [])
            if not found:
                raise AssertionError(f"{case_id}: supplement for {cid} has no evidence")
            section_ref = spec["criteria"][cid]
            supplemental["provides"][section_ref] = sorted({ev.doc_id for ev in found})
            supplemental_labels.append(
                LabeledCriterion(criterion_id=cid, section_ref=section_ref, status="met", evidence=found)
            )

    criteria = []
    gaps = []
    for cid, section_ref in spec["criteria"].items():
        mode = modes[cid]
        status = MODE_STATUS[mode]
        found = evidence.get(cid, [])
        if status == "not_met" and found:
            raise AssertionError(f"{case_id}: {cid} is missing but has evidence")
        if status != "not_met" and not found:
            raise AssertionError(f"{case_id}: {cid} is {status} but has no evidence")
        criteria.append(LabeledCriterion(criterion_id=cid, section_ref=section_ref, status=status, evidence=found))
        if status != "met":
            gaps.append(Gap(criterion_id=cid, description=GAP_TEXT[cid][mode]))

    tags = [] if case_type == "clean" else [case_type]
    if case_type == "appeal":
        tags = ["appeal_scenario"]
    targets = [cid for cid, mode in modes.items() if mode != "met"]
    unresolved = [cid for cid, mode in modes.items() if MODE_STATUS[mode] != "met" and cid not in supplied]
    label = CaseLabel(
        case_id=case_id,
        split=split,
        procedure=procedure,
        criteria=criteria,
        planted_gaps=gaps,
        expected_outcome=_expected_outcome(case_type, modes),
        expected_final="escalated" if unresolved else "approved",
        supplemental=supplemental_labels,
        hard_case_tags=tags,
        facts=cb.facts,
        notes=f"case_type={case_type}"
        + (f"; affected={','.join(targets)}" if targets else "")
        + (f"; clinic_can_supply={','.join(supplied)}" if supplied else ""),
    )
    return GeneratedCase(order=order, chart=chart, label=label, supplemental=supplemental)


def generate_cases(n: int, seed: int, split: str) -> list[GeneratedCase]:
    rng = random.Random(seed)
    types = _plan_case_types(rng, n)
    procedures = _plan_procedures(rng, types)
    return [_generate_case(rng, split, i, procedures[i], types[i]) for i in range(n)]


SPLITS = {
    "dev": (config.DEV_CASES, config.DEV_SEED),
    "sealed": (config.SEALED_CASES, config.SEALED_SEED),
}


def generate_split(split: str) -> list[GeneratedCase]:
    n, seed = SPLITS[split]
    return generate_cases(n, seed, split)


def _dump(data: object) -> str:
    return json.dumps(data, indent=2, ensure_ascii=True) + "\n"


def case_files(case: GeneratedCase) -> dict[str, str]:
    return {
        "order.json": _dump(case.order.model_dump(mode="json")),
        "chart.json": _dump(case.chart),
        "labels.json": _dump(case.label.model_dump(mode="json")),
        "supplemental.json": _dump(case.supplemental),
    }


def write_split(split: str, out_root: Path = config.CASES_DIR) -> Path:
    split_dir = Path(out_root) / split
    if split_dir.exists():
        shutil.rmtree(split_dir)
    for case in generate_split(split):
        case_dir = split_dir / case.label.case_id.replace(f"{split}_", "case_")
        case_dir.mkdir(parents=True)
        for name, body in case_files(case).items():
            (case_dir / name).write_text(body, encoding="utf-8")
    return split_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic AuthPilot cases.")
    parser.add_argument("--split", choices=["dev", "sealed", "all"], default="all")
    parser.add_argument("--out", type=Path, default=config.CASES_DIR)
    args = parser.parse_args()
    splits = ["dev", "sealed"] if args.split == "all" else [args.split]
    for split in splits:
        path = write_split(split, args.out)
        print(f"wrote {SPLITS[split][0]} {split} cases to {path}")


if __name__ == "__main__":
    main()
