"""Mock payer API. Run standalone with: uvicorn authpilot.payer_mock.app:app --port 8100

POST /submit is idempotent on idempotency_key: resubmitting the same key returns the original
submission instead of creating a second one.
"""

from fastapi import FastAPI, HTTPException

from authpilot.payer_mock.reviewer import review
from authpilot.schemas import PayerDecision, SubmissionPackage

app = FastAPI(title="AuthPilot mock payer")


@app.get("/health")
def health() -> dict[str, str]:
    from authpilot import config
    return {"mode": config.LLM_MODE}

_decisions: dict[str, PayerDecision] = {}
_by_key: dict[str, str] = {}
_packages: dict[str, SubmissionPackage] = {}


@app.post("/submit", response_model=PayerDecision)
def submit(package: SubmissionPackage) -> PayerDecision:
    if package.idempotency_key in _by_key:
        existing = _decisions[_by_key[package.idempotency_key]]
        return existing.model_copy(update={"status": "received"})
    level = "first"
    if package.appeal_of is not None:
        original = _decisions.get(package.appeal_of)
        if original is None or original.status != "denied":
            raise HTTPException(status_code=409, detail="appeal_of must reference a denied submission")
        level = "appeal"
    submission_id = f"SUB-{len(_decisions) + 1:05d}"
    status, code, reason = review(package, level)
    _decisions[submission_id] = PayerDecision(submission_id=submission_id, status=status,
                                              reason_code=code, reason=reason, level=level)
    _by_key[package.idempotency_key] = submission_id
    _packages[submission_id] = package
    return PayerDecision(submission_id=submission_id, status="received", level=level)


@app.get("/status/{submission_id}", response_model=PayerDecision)
def status(submission_id: str) -> PayerDecision:
    if submission_id not in _decisions:
        raise HTTPException(status_code=404, detail="unknown submission")
    return _decisions[submission_id]


@app.get("/submissions")
def submissions() -> dict[str, int]:
    return {"count": len(_decisions)}


@app.post("/reset")
def reset() -> dict[str, str]:
    _decisions.clear()
    _by_key.clear()
    _packages.clear()
    return {"status": "reset"}
