from authpilot import ehr
from authpilot.schemas import Chart, Strict
from authpilot.tools._common import log_call, log_result, tool_spec


class GetPatientRecordInput(Strict):
    patient_id: str


class ChartDocument(Strict):
    doc_id: str
    text: str


class PatientRecord(Strict):
    patient_id: str
    documents: list[ChartDocument]

    def as_chart(self) -> Chart:
        return {doc.doc_id: doc.text for doc in self.documents}


def get_patient_record(patient_id: str, case_id: str = "-") -> PatientRecord:
    log_call(case_id, "get_patient_record", {"patient_id": patient_id})
    chart = ehr.load_chart(patient_id)
    record = PatientRecord(
        patient_id=patient_id,
        documents=[ChartDocument(doc_id=doc_id, text=text) for doc_id, text in chart.items()],
    )
    log_result(case_id, "get_patient_record", {"doc_ids": list(chart)})
    return record


TOOL_SPEC = tool_spec(
    "get_patient_record",
    "Fetch the patient's chart documents from the EHR, each with a stable doc_id.",
    GetPatientRecordInput,
)
