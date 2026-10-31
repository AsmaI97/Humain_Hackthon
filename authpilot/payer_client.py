"""HTTP client for the payer. PAYER_URL=inprocess runs the mock payer inside this process."""

from typing import Any

import httpx

from authpilot import config
from authpilot.schemas import PayerDecision, SubmissionPackage


class PayerError(Exception):
    pass


class PayerUnavailable(PayerError):
    """Connection failures, timeouts and 5xx responses."""


_client: Any = None
_client_url: str | None = None


def _get_client():
    global _client, _client_url
    if _client is None or _client_url != config.PAYER_URL:
        if config.PAYER_URL == "inprocess":
            from fastapi.testclient import TestClient

            from authpilot.payer_mock.app import app

            _client = TestClient(app)
        else:
            _client = httpx.Client(base_url=config.PAYER_URL, timeout=config.PAYER_TIMEOUT_S)
        _client_url = config.PAYER_URL
    return _client


def _request(method: str, path: str, **kwargs) -> dict:
    try:
        response = _get_client().request(method, path, **kwargs)
    except httpx.HTTPError as exc:
        raise PayerUnavailable(f"{method} {path}: {exc}") from exc
    if response.status_code >= 500:
        raise PayerUnavailable(f"{method} {path}: HTTP {response.status_code}")
    if response.status_code >= 400:
        raise PayerError(f"{method} {path}: HTTP {response.status_code} {response.text}")
    return response.json()


def submit(package: SubmissionPackage) -> PayerDecision:
    return PayerDecision.model_validate(_request("POST", "/submit", json=package.model_dump(mode="json")))


def status(submission_id: str) -> PayerDecision:
    return PayerDecision.model_validate(_request("GET", f"/status/{submission_id}"))


def reset() -> None:
    _request("POST", "/reset")
