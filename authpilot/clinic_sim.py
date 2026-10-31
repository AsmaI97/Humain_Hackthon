"""Simulated clinic. When asked for missing documentation it sends whatever it holds for the
requested policy sections, and nothing otherwise. Deterministic."""

from authpilot import ehr
from authpilot.schemas import Chart, Gap


def respond(patient_id: str, gaps: list[Gap]) -> Chart:
    held = ehr.load_supplemental(patient_id)
    refs = {gap.criterion_id.split(":")[-1] for gap in gaps}
    current = ehr.load_chart(patient_id)
    doc_ids = sorted({doc_id for ref in refs for doc_id in held["provides"].get(ref, [])})
    new_docs = {doc_id: held["documents"][doc_id] for doc_id in doc_ids if doc_id not in current}
    if new_docs:
        ehr.append_documents(patient_id, new_docs)
    return new_docs
