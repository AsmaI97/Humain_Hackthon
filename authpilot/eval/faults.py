"""Fault injection at scale. Each fault is a context manager; the harness runs every case with
the fault active and reports how many runs end in a safe state."""

from contextlib import contextmanager
from typing import Iterator

from authpilot import llm, payer_client
from authpilot.payer_client import PayerUnavailable
from authpilot.tools import search_policy


@contextmanager
def _patched(obj, name: str, value) -> Iterator[None]:
    old = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, old)


def _down(*args, **kwargs):
    raise PayerUnavailable("injected: payer unreachable")


@contextmanager
def payer_down() -> Iterator[None]:
    with _patched(payer_client, "submit", _down), _patched(payer_client, "status", _down):
        yield


@contextmanager
def corrupted_output() -> Iterator[None]:
    """Every criterion check comes back as an invalid tool call."""
    real = llm.complete

    def corrupt(*args, **kwargs):
        response = real(*args, **kwargs)
        if str(kwargs.get("purpose", "")).startswith("check:"):
            for block in response.content:
                if block.get("type") == "tool_use":
                    block["input"] = {"status": "probably", "confidence": 7}
        return response

    with _patched(llm, "complete", corrupt):
        yield


@contextmanager
def empty_retrieval() -> Iterator[None]:
    with _patched(search_policy, "search_sections", lambda policy, query, k: []):
        yield


FAULTS = {"payer_down": payer_down, "corrupted_output": corrupted_output, "empty_retrieval": empty_retrieval}
