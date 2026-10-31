import pytest
from fastapi.testclient import TestClient

from authpilot.payer_mock.app import app
from authpilot.schemas import Evidence, SubmissionPackage, SubmittedCriterion
from helpers import appeal_case, clean_case

client = TestClient(app)


def _package(case, key="k1", drop_ref=None, appeal_of=None, tamper=None):
    order, chart, label = case
    criteria, attachments = [], {}
    for c in label.criteria:
        if c.section_ref == drop_ref:
            continue
        evidence = c.evidence
        if tamper and c.section_ref == tamper[0]:
            evidence = [Evidence(doc_id=evidence[0].doc_id, span_text=tamper[1], start=0, end=len(tamper[1]))]
        criteria.append(SubmittedCriterion(section_ref=c.section_ref, status=c.status, evidence=evidence))
        attachments.update({e.doc_id: chart[e.doc_id] for e in c.evidence})
    return SubmissionPackage(case_id=label.case_id, idempotency_key=key, order=order, criteria=criteria,
                             letter="letter", attachments=attachments, appeal_of=appeal_of)


def test_health_reports_the_llm_mode():
    assert client.get("/health").json() == {"mode": "stub"}


def _submit(package):
    received = client.post("/submit", json=package.model_dump(mode="json"))
    assert received.status_code == 200
    assert received.json()["status"] == "received"
    return client.get(f"/status/{received.json()['submission_id']}").json()


def test_complete_package_is_approved():
    assert _submit(_package(clean_case()))["status"] == "approved"


def test_missing_criterion_is_denied_with_policy_reason_code():
    decision = _submit(_package(clean_case(), drop_ref="2.2"))
    assert decision["status"] == "denied" and decision["reason_code"] == "RF-SCREEN"


def test_evidence_not_in_attachments_is_denied():
    decision = _submit(_package(clean_case(), tamper=("2.3", "Neuro exam normal.")))
    assert decision["status"] == "denied" and decision["reason_code"] == "NEURO-EXAM"


def test_content_rule_rejects_das28_claim_without_a_score():
    order, chart, label = case = clean_case("biologic")
    consult = next(d for d in chart if "consult" in d)
    history_line = chart[consult].split("History:\n")[1].split("\n")[0]
    sentence = history_line.split(". ")[0].rstrip(".") + "."
    assert sentence in chart[consult]
    decision = _submit(_package(case, tamper=("2.4", sentence)))
    assert decision["status"] == "denied" and decision["reason_code"] == "DAS28-SCORE"
    assert "does not satisfy" in decision["reason"]


def test_flowsheet_evidence_denied_first_level_then_approved_on_appeal():
    case = appeal_case()
    first = _submit(_package(case, key="first"))
    assert first["status"] == "denied" and first["reason_code"] == "DAS28-SCORE" and first["level"] == "first"
    appeal = _submit(_package(case, key="appeal", appeal_of=first["submission_id"]))
    assert appeal["status"] == "approved" and appeal["level"] == "appeal"


def test_submission_is_idempotent():
    package = _package(clean_case(), key="same")
    first = client.post("/submit", json=package.model_dump(mode="json")).json()
    second = client.post("/submit", json=package.model_dump(mode="json")).json()
    assert first["submission_id"] == second["submission_id"]
    assert client.get("/submissions").json()["count"] == 1


def test_unknown_submission_and_invalid_appeal():
    assert client.get("/status/SUB-99999").status_code == 404
    approved = _submit(_package(clean_case(), key="ok"))
    bad = _package(clean_case(), key="bad-appeal", appeal_of=approved["submission_id"])
    assert client.post("/submit", json=bad.model_dump(mode="json")).status_code == 409


@pytest.mark.parametrize("payload", [{}, {"case_id": "x"}])
def test_malformed_submission_rejected(payload):
    assert client.post("/submit", json=payload).status_code == 422
