import pytest

from authpilot import audit, config, llm


@pytest.fixture(autouse=True)
def _live_calls_use_a_fake_key(monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "unit-test-not-a-real-key")
from authpilot.policies import find_policy
from authpilot.prompts import EXTRACT_TOOL, extraction_messages, tool_spec

FAKE_RESPONSE = {
    "content": [{"type": "tool_use", "id": "t1", "name": "echo", "input": {"x": 1}}],
    "stop_reason": "tool_use",
    "model": "fake-model",
    "usage": {"input_tokens": 10, "output_tokens": 3},
}
MESSAGES = [{"role": "user", "content": "hello"}]


class FakeLive:
    def __init__(self, failures=0):
        self.calls = 0
        self.failures = failures

    def __call__(self, request):
        self.calls += 1
        if self.calls <= self.failures:
            raise llm.TransientLLMError("timeout")
        return FAKE_RESPONSE


def test_stub_mode_answers_extraction_offline():
    policy = find_policy("payer_a", "72148")
    response = llm.complete(extraction_messages(policy), tools=[tool_spec(EXTRACT_TOOL)],
                            tool_choice={"type": "tool", "name": EXTRACT_TOOL})
    assert response.source == "stub"
    refs = [c["section_ref"] for c in response.tool_input(EXTRACT_TOOL)["criteria"]]
    assert refs == ["2.1", "2.2", "2.3", "2.4"]


def test_live_then_replay_uses_cache(monkeypatch):
    fake = FakeLive()
    monkeypatch.setattr(llm, "live_caller", fake)
    first = llm.complete(MESSAGES, mode="live")
    assert first.source == "live" and fake.calls == 1
    assert config.LLM_CACHE_PATH.exists()

    llm.reset_cache()
    second = llm.complete(MESSAGES, mode="replay")
    assert second.source == "cache"
    assert second.content == first.content
    assert fake.calls == 1


def test_replay_miss_raises_and_is_logged():
    with pytest.raises(llm.CacheMissError):
        llm.complete(MESSAGES, mode="replay", case_id="c1")
    assert audit.read_events("c1")[-1]["event_type"] == "error"


def test_transient_errors_retry_with_exponential_backoff(monkeypatch):
    sleeps = []
    monkeypatch.setattr(llm, "sleep", sleeps.append)
    monkeypatch.setattr(config, "LLM_BACKOFF_S", 1.0)
    fake = FakeLive(failures=2)
    monkeypatch.setattr(llm, "live_caller", fake)
    response = llm.complete(MESSAGES, mode="live")
    assert response.tool_input("echo") == {"x": 1}
    assert fake.calls == 3
    assert sleeps == [1.0, 2.0]


def test_retries_exhausted_raises(monkeypatch):
    monkeypatch.setattr(config, "LLM_MAX_RETRIES", 2)
    fake = FakeLive(failures=10)
    monkeypatch.setattr(llm, "live_caller", fake)
    with pytest.raises(llm.TransientLLMError):
        llm.complete(MESSAGES, mode="live")
    assert fake.calls == 3


def test_calls_are_logged_with_tokens_and_latency(monkeypatch):
    monkeypatch.setattr(llm, "live_caller", FakeLive())
    llm.complete(MESSAGES, mode="live", case_id="c2", purpose="unit")
    event = audit.read_events("c2")[-1]
    assert event["event_type"] == "llm_call"
    assert event["payload"]["input_tokens"] == 10
    assert event["payload"]["purpose"] == "unit"
    assert "latency_ms" in event["payload"]


def test_request_key_is_stable_and_sensitive(monkeypatch):
    a = llm.build_request(MESSAGES, "m1")
    assert llm.request_key(a) == llm.request_key(llm.build_request(MESSAGES, "m1"))
    assert llm.request_key(a) != llm.request_key(llm.build_request(MESSAGES, "m2"))
    assert llm.request_key(a) != llm.request_key(llm.build_request(MESSAGES, "m1", temperature=0.5))
    assert llm.request_key(a) != llm.request_key(llm.build_request([{"role": "user", "content": "other"}], "m1"))
    assert llm.request_key(a) != llm.request_key(llm.build_request(MESSAGES, "m1", tools=[{"name": "echo"}]))
    before = llm.request_key(a)
    monkeypatch.setattr(config, "PROMPT_VERSION", "p-other")
    assert llm.request_key(a) != before


def test_live_without_api_key_fails_cleanly(monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    with pytest.raises(llm.LLMError, match="ANTHROPIC_API_KEY"):
        llm.complete(MESSAGES, mode="live")


def test_models_come_from_config(monkeypatch):
    seen = {}

    def capture(request):
        seen["model"] = request["model"]
        return FAKE_RESPONSE

    monkeypatch.setattr(config, "AGENT_MODEL", "model-from-env")
    monkeypatch.setattr(llm, "live_caller", capture)
    llm.complete(MESSAGES, mode="live")
    assert seen["model"] == "model-from-env"
