"""Modes, cache identity, secret redaction, and stub faults.

The live test is marked `live` and skipped unless ANTHROPIC_API_KEY is set. Do not run it
until a real API call is intended (`pytest -m live`).
"""

import json
import os

import pytest

from authpilot import audit, config, llm
from authpilot.agent import auto_approver, run_case
from authpilot.eval import compare
from authpilot.eval.guard import dump_report, require_eval_mode
from authpilot.eval import run_all
from authpilot.payer_mock import app as payer_app
from authpilot.schemas import Status
from helpers import clean_case

MESSAGES = [{"role": "user", "content": "hello"}]
FAKE = {
    "content": [{"type": "tool_use", "id": "t1", "name": "echo", "input": {"x": 1}}],
    "stop_reason": "tool_use",
    "model": "fake-model",
    "usage": {"input_tokens": 4, "output_tokens": 2},
}


def _assert_clean(blob: str, secret: str, label: str) -> None:
    if "sk-ant" in blob:
        raise AssertionError(f"{label} contains the sk-ant key prefix")
    if secret and secret in blob:
        raise AssertionError(f"{label} contains the ANTHROPIC_API_KEY value")


def _calls():
    seen = {"live": 0, "stub": 0}

    def live(request):
        seen["live"] += 1
        return FAKE

    def stub(request):
        seen["stub"] += 1
        return FAKE

    return seen, live, stub


# Modes ------------------------------------------------------------------------------------


def test_unset_mode_defaults_to_replay():
    assert config.resolve_llm_mode(None) == "replay"
    assert config.resolve_llm_mode("  ") == "replay"
    assert config.resolve_llm_mode("live") == "live"
    with pytest.raises(ValueError, match="live"):
        config.resolve_llm_mode("record")


def test_stub_mode_answers_without_a_key(monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    response = llm.complete(MESSAGES, mode="stub", purpose="extract_criteria")
    assert response.source == "stub"
    assert response.content


def test_replay_hit_does_not_call_live_or_stub(monkeypatch):
    seen, live, stub = _calls()
    monkeypatch.setattr(llm, "live_caller", live)
    monkeypatch.setattr(llm, "stub_caller", stub)
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "unit-test-not-a-real-key")
    llm.complete(MESSAGES, mode="live")
    llm.reset_cache()
    replayed = llm.complete(MESSAGES, mode="replay")
    assert replayed.source == "cache"
    assert replayed.content == FAKE["content"]
    assert seen == {"live": 1, "stub": 0}


def test_live_always_calls_and_records_provenance(monkeypatch):
    seen, live, stub = _calls()
    monkeypatch.setattr(llm, "live_caller", live)
    monkeypatch.setattr(llm, "stub_caller", stub)
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "unit-test-not-a-real-key")
    llm.complete(MESSAGES, mode="live")
    llm.complete(MESSAGES, mode="live")
    assert seen == {"live": 2, "stub": 0}
    entry = json.loads(config.LLM_CACHE_PATH.read_text(encoding="utf-8").splitlines()[-1])
    assert entry["produced_by"] == "live"
    assert entry["model"] == config.AGENT_MODEL
    assert entry["prompt_version"] == config.PROMPT_VERSION
    assert entry["key"] == llm.request_key(llm.build_request(MESSAGES, config.AGENT_MODEL))


def test_replay_miss_raises_cache_miss_and_does_not_fall_back(monkeypatch):
    seen, live, stub = _calls()
    monkeypatch.setattr(llm, "live_caller", live)
    monkeypatch.setattr(llm, "stub_caller", stub)
    with pytest.raises(llm.CacheMissError, match="does not call the API or the stub"):
        llm.complete(MESSAGES, mode="replay", case_id="miss")
    assert seen == {"live": 0, "stub": 0}
    event = audit.read_events("miss")[-1]
    assert event["event_type"] == "error"
    assert event["llm_mode"] == "stub"
    assert event["prompt_version"] == config.PROMPT_VERSION
    assert event["model_name"]


def test_live_without_a_key_fails_before_any_call(monkeypatch):
    seen, live, _stub = _calls()
    monkeypatch.setattr(llm, "live_caller", live)
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    with pytest.raises(llm.LLMError, match="ANTHROPIC_API_KEY is not set"):
        llm.complete(MESSAGES, mode="live")
    assert seen["live"] == 0


def test_replay_works_without_a_key(monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "unit-test-not-a-real-key")
    monkeypatch.setattr(llm, "live_caller", lambda request: FAKE)
    llm.complete(MESSAGES, mode="live")
    llm.reset_cache()
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    assert llm.complete(MESSAGES, mode="replay").source == "cache"


def test_startup_log_reports_presence_only():
    import logging

    records = []

    class Grab(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    logger = logging.getLogger("authpilot")
    handler = Grab()
    logger.addHandler(handler)
    try:
        config.log_api_key_status()
    finally:
        logger.removeHandler(handler)
    assert records[-1] in {"API key present: yes", "API key present: no"}
    _assert_clean("\n".join(records), os.environ.get("ANTHROPIC_API_KEY", ""), "startup log")


def test_env_example_has_names_and_no_key():
    lines = (config.ROOT_DIR / ".env.example").read_text(encoding="utf-8").splitlines()
    assert "ANTHROPIC_API_KEY=your-api-key-here" in lines
    assert "LLM_MODE=replay" in lines
    assert "AGENT_MODEL=claude-sonnet-5-5" in lines
    assert "CHEAP_MODEL=claude-haiku-5-5" in lines
    assert "ESCALATION_MODEL=claude-opus-5-5" in lines
    assert "sk-ant" not in "\n".join(lines)


def test_env_file_is_gitignored():
    ignored = (config.ROOT_DIR / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in ignored
    assert ".env.*" in ignored
    assert "!.env.example" in ignored


# Cache identity and secrets ---------------------------------------------------------------


def test_cache_key_changes_with_each_identity_field(monkeypatch):
    base = llm.build_request(MESSAGES, "model-a", tools=[{"name": "echo"}], temperature=0.0)
    key = llm.request_key(base, "p3.0")
    assert key != llm.request_key(llm.build_request(MESSAGES, "model-b", tools=[{"name": "echo"}]), "p3.0")
    assert key != llm.request_key(base, "p9.9")
    assert key != llm.request_key(llm.build_request([{"role": "user", "content": "x"}], "model-a",
                                                    tools=[{"name": "echo"}]), "p3.0")
    assert key != llm.request_key(llm.build_request(MESSAGES, "model-a", tools=[{"name": "other"}]), "p3.0")
    assert key != llm.request_key(llm.build_request(MESSAGES, "model-a", tools=[{"name": "echo"}],
                                                    temperature=0.4), "p3.0")
    monkeypatch.setattr(config, "PROMPT_VERSION", "p3.0")
    assert llm.request_key(base) == key


def test_generated_logs_cache_and_results_never_contain_the_key(tmp_path, monkeypatch):
    import logging

    real = os.environ.get("ANTHROPIC_API_KEY", "")
    sentinel = "sk-ant-unit-test-sentinel"
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", real or sentinel)
    if not real:
        monkeypatch.setenv("ANTHROPIC_API_KEY", sentinel)
    planted = sentinel if not real else f"{sentinel} {real}"
    logged: list[str] = []

    class Grab(logging.Handler):
        def emit(self, record):
            logged.append(record.getMessage())

    logger = logging.getLogger("authpilot")
    handler = Grab()
    logger.addHandler(handler)

    def leaky(request):
        return {
            "content": [{"type": "text", "text": planted}],
            "stop_reason": "end_turn",
            "model": "fake-model",
            "usage": {"input_tokens": 1, "output_tokens": 1},
            "api_key": planted,
        }

    monkeypatch.setattr(llm, "live_caller", leaky)
    llm.complete([{"role": "user", "content": planted}], mode="live", case_id="secret")
    audit.log_event("secret", "agent", "error", {"note": planted})

    def boom(request):
        raise llm.LLMError("failed " + planted)

    monkeypatch.setattr(llm, "live_caller", boom)
    with pytest.raises(llm.LLMError):
        llm.complete(MESSAGES, mode="live", case_id="secret")
    logger.removeHandler(handler)

    report_path = tmp_path / "report.json"
    report_path.write_text(dump_report({
        "meta": {"split": "dev", "llm_mode": "live", "note": planted},
        "summaries": {"agent": {"criterion_accuracy": 1.0, "comment": planted}},
    }), encoding="utf-8")

    secret = os.environ.get("ANTHROPIC_API_KEY", "")
    blobs = {
        "log": "\n".join(logged),
        "cache": config.LLM_CACHE_PATH.read_text(encoding="utf-8"),
        "audit": config.AUDIT_DB_PATH.read_bytes().decode("latin-1"),
        "results": report_path.read_text(encoding="utf-8"),
    }
    for event in audit.read_events("secret"):
        blobs["audit event"] = json.dumps(event)
        _assert_clean(blobs["audit event"], secret, "audit event")
    for label, blob in blobs.items():
        _assert_clean(blob, secret, label)
    assert "[redacted]" in blobs["cache"]
    assert "[redacted]" in blobs["results"]
    assert any(line.startswith("llm call mode=") for line in logged)


# Evaluation guards ------------------------------------------------------------------------


def test_eval_and_compare_refuse_stub(monkeypatch):
    import sys

    monkeypatch.setattr(config, "LLM_MODE", "stub")
    with pytest.raises(SystemExit, match="stub"):
        require_eval_mode()
    with pytest.raises(SystemExit, match="stub"):
        compare.main()
    monkeypatch.setattr(sys, "argv", ["run_all", "--split", "dev", "--limit", "1"])
    with pytest.raises(SystemExit, match="stub"):
        run_all.main()


def test_replay_eval_requires_a_live_cache_with_the_same_model(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LLM_MODE", "replay")
    monkeypatch.setattr(config, "AGENT_MODEL", "model-from-env")
    cache = tmp_path / "cache.jsonl"
    monkeypatch.setattr(config, "LLM_CACHE_PATH", cache)
    with pytest.raises(SystemExit, match="empty"):
        require_eval_mode()

    cache.write_text(json.dumps({
        "key": "k", "produced_by": "stub", "model": "model-from-env",
        "prompt_version": config.PROMPT_VERSION, "response": FAKE,
    }) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="not produced by a live run"):
        require_eval_mode()

    cache.write_text(json.dumps({
        "key": "k", "produced_by": "live", "model": "other-model",
        "prompt_version": config.PROMPT_VERSION, "response": FAKE,
    }) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="does not match"):
        require_eval_mode()

    cache.write_text(json.dumps({
        "key": "k", "produced_by": "live", "model": "model-from-env",
        "prompt_version": "p-old", "response": FAKE,
    }) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="prompt version"):
        require_eval_mode()

    cache.write_text(json.dumps({
        "key": "k", "produced_by": "live", "model": "model-from-env",
        "prompt_version": config.PROMPT_VERSION, "response": FAKE,
    }) + "\n", encoding="utf-8")
    require_eval_mode()


def test_compare_reports_a_regression_without_calling_the_api(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LLM_MODE", "live")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "unit-test-not-a-real-key")
    monkeypatch.setattr(config, "RESULTS_DIR", tmp_path)
    out = tmp_path / "eval"
    out.mkdir()
    seen = {"calls": 0}
    monkeypatch.setattr(llm, "live_caller", lambda request: seen.__setitem__("calls", seen["calls"] + 1))

    def report(accuracy: float, stamp: str) -> dict:
        return {
            "meta": {"split": "dev", "llm_mode": "live", "agent_model": "model-a", "model": "model-a",
                     "prompt_version": config.PROMPT_VERSION, "run_at": stamp},
            "summaries": {"agent": {"criterion_accuracy": accuracy}},
            "perturbations": {},
            "faults": {},
        }

    (out / "20260101T000000Z_dev_live.json").write_text(json.dumps(report(0.9, "t1")), encoding="utf-8")
    (out / "20260102T000000Z_dev_live.json").write_text(json.dumps(report(0.4, "t2")), encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        compare.main()
    assert exc.value.code == 1
    assert seen["calls"] == 0


# Stub faults ------------------------------------------------------------------------------


def _run_with_fault(name: str):
    llm.set_stub_fault(name)
    try:
        order, _, label = clean_case()
        state, _ = run_case(label.case_id, order, approver=auto_approver("test-reviewer"))
        return state
    finally:
        llm.set_stub_fault(None)


def _rules(case_id: str) -> list[str]:
    return [event["payload"]["rule"] for event in audit.read_events(case_id) if event["event_type"] == "fallback"]


def _nothing_submitted(state) -> None:
    assert state.submission_id is None and state.submissions == []
    assert payer_app.submissions()["count"] == 0


@pytest.mark.parametrize("fault", ["invalid_json", "schema_invalid", "empty"])
def test_invalid_output_faults_escalate(fault):
    state = _run_with_fault(fault)
    assert state.status is Status.escalated
    assert "model output invalid after retries" in state.escalation_reason
    _nothing_submitted(state)
    assert "invalid_output_escalate" in _rules(state.case_id)


def test_bad_span_fault_drops_the_claim():
    state = _run_with_fault("bad_span")
    assert state.status is Status.escalated
    assert state.results and all(result.evidence == [] for result in state.results)
    assert "evidence_not_found" in _rules(state.case_id)
    _nothing_submitted(state)


def test_timeout_fault_retries_then_queues(monkeypatch):
    sleeps = []
    monkeypatch.setattr(llm, "sleep", sleeps.append)
    monkeypatch.setattr(config, "LLM_BACKOFF_S", 1.0)
    monkeypatch.setattr(config, "LLM_MAX_RETRIES", 2)
    llm.set_stub_fault("timeout")
    try:
        with pytest.raises(llm.TransientLLMError, match="injected timeout"):
            llm.complete(MESSAGES, mode="stub")
        assert sleeps == [1.0, 2.0]
        state = _run_with_fault("timeout")
    finally:
        llm.set_stub_fault(None)
    assert state.queued_reason and "LLM unavailable" in state.queued_reason
    assert "llm_error_queue" in _rules(state.case_id)
    _nothing_submitted(state)


def test_api_error_fault_queues_without_retrying_the_same_call(monkeypatch):
    sleeps = []
    monkeypatch.setattr(llm, "sleep", sleeps.append)
    llm.set_stub_fault("api_error")
    try:
        with pytest.raises(llm.LLMError, match="injected API error") as exc:
            llm.complete(MESSAGES, mode="stub")
        assert type(exc.value) is llm.LLMError
        assert sleeps == []
        state = _run_with_fault("api_error")
    finally:
        llm.set_stub_fault(None)
    assert state.queued_reason and "LLM unavailable" in state.queued_reason
    assert "llm_error_switch_model" in _rules(state.case_id)
    _nothing_submitted(state)


@pytest.mark.live
def test_live_mode_calls_anthropic_when_the_key_is_set():
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        pytest.skip("ANTHROPIC_API_KEY is not set")
    response = llm.complete(
        [{"role": "user", "content": "Reply with the single word pong."}],
        model=config.CHEAP_MODEL,
        max_tokens=16,
        mode="live",
        purpose="live_test",
    )
    assert response.source == "live"
    assert response.usage.get("input_tokens", 0) >= 0
