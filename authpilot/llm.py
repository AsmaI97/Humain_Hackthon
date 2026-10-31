"""The single LLM entry point: complete().

Modes (config.LLM_MODE, overridable per call):
- live:   call the Anthropic SDK, then save the request/response pair to the replay cache.
- replay: answer only from that cache. A miss raises CacheMissError. Never calls the API or the stub.
- stub:   scripted responses for unit tests, fault injection and frontend work. No key and no network.

Model names come from AGENT_MODEL, CHEAP_MODEL and ESCALATION_MODEL. The API key is read from
the environment and is never written to the cache, the audit log, or a log line.
"""

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from authpilot import audit, config, secrets

log = logging.getLogger("authpilot.llm")


class LLMError(Exception):
    pass


class TransientLLMError(LLMError):
    """Timeouts, connection problems, rate limits and 5xx responses. Safe to retry."""


class CacheMissError(LLMError):
    """Replay mode has no saved response for this request. It does not call the API or the stub."""


CacheMiss = CacheMissError


@dataclass
class LLMResponse:
    content: list[dict[str, Any]]
    stop_reason: str | None
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    latency_ms: float = 0.0
    source: str = "live"

    def tool_input(self, name: str) -> dict[str, Any] | None:
        for block in self.content:
            if block.get("type") == "tool_use" and block.get("name") == name:
                return block.get("input")
        return None

    def text(self) -> str:
        return "".join(block.get("text", "") for block in self.content if block.get("type") == "text")


def build_request(
    messages: list[dict[str, Any]],
    model: str,
    tools: list[dict[str, Any]] | None = None,
    system: str | None = None,
    tool_choice: dict[str, Any] | None = None,
    temperature: float = 0.0,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    request: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens or config.LLM_MAX_TOKENS,
        "temperature": temperature,
        "messages": messages,
    }
    if system:
        request["system"] = system
    if tools:
        request["tools"] = tools
    if tool_choice:
        request["tool_choice"] = tool_choice
    return request


def request_key(request: dict[str, Any], prompt_version: str | None = None) -> str:
    """Hash of model, prompt version, messages, tools and temperature.

    system and tool_choice are included as well: they change the answer, and the prompt
    version alone does not capture a different system prompt at the same version.
    """
    identity = {
        "model": request["model"],
        "prompt_version": config.PROMPT_VERSION if prompt_version is None else prompt_version,
        "messages": request["messages"],
        "tools": request.get("tools") or [],
        "temperature": request["temperature"],
        "system": request.get("system"),
        "tool_choice": request.get("tool_choice"),
    }
    return hashlib.sha256(json.dumps(identity, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _scrub(exc: BaseException) -> None:
    if not exc.args:
        return
    exc.args = tuple(secrets.redact_text(arg) if isinstance(arg, str) else arg for arg in exc.args)


# Cache ------------------------------------------------------------------------------------

_cache: dict[str, dict[str, Any]] | None = None
_cache_path: Path | None = None


def _read_entries() -> list[dict[str, Any]]:
    path = Path(config.LLM_CACHE_PATH)
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entries.append(json.loads(line))
    return entries


def _load_cache() -> dict[str, dict[str, Any]]:
    global _cache, _cache_path
    path = Path(config.LLM_CACHE_PATH)
    if _cache is None or _cache_path != path:
        _cache, _cache_path = {}, path
        for entry in _read_entries():
            if "key" in entry and "response" in entry:
                _cache[entry["key"]] = entry
    return _cache


def _store(key: str, request: dict[str, Any], response: dict[str, Any], prompt_version: str) -> None:
    entry = secrets.redact({
        "key": key,
        "produced_by": "live",
        "model": request["model"],
        "prompt_version": prompt_version,
        "request": request,
        "response": response,
    })
    cache = _load_cache()
    cache[key] = entry
    path = Path(config.LLM_CACHE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")


def reset_cache() -> None:
    global _cache, _cache_path
    _cache, _cache_path = None, None


def require_live_cache() -> None:
    """Replay is valid for evaluation only when every saved pair came from a live run
    that used the current prompt version and one of the configured models."""
    entries = _read_entries()
    if not entries:
        raise SystemExit(
            "Refusing to run in replay mode: the replay cache is empty. "
            "Run once in live mode so the cache is produced by a live call with the same "
            "model and prompt version."
        )
    allowed = {config.AGENT_MODEL, config.CHEAP_MODEL, config.ESCALATION_MODEL}
    seen_models = set()
    for entry in entries:
        if entry.get("produced_by") != "live":
            raise SystemExit(
                "Refusing to run in replay mode: the cache was not produced by a live run. "
                "Replay does not fall back to the stub or to a new API call."
            )
        if entry.get("prompt_version") != config.PROMPT_VERSION:
            raise SystemExit(
                "Refusing to run in replay mode: cache prompt version "
                f"{entry.get('prompt_version')!r} does not match {config.PROMPT_VERSION!r}."
            )
        model = entry.get("model")
        if model not in allowed:
            raise SystemExit(
                f"Refusing to run in replay mode: cache model {model!r} does not match the "
                "configured AGENT_MODEL, CHEAP_MODEL or ESCALATION_MODEL."
            )
        seen_models.add(model)
    if config.AGENT_MODEL not in seen_models:
        raise SystemExit(
            "Refusing to run in replay mode: the cache has no live responses for "
            f"AGENT_MODEL {config.AGENT_MODEL!r}."
        )


# Live API ---------------------------------------------------------------------------------


_LIVE_KEY_ERROR = (
    "ANTHROPIC_API_KEY is not set. Live mode cannot start. "
    "Replay and stub modes work without a key."
)


def _call_anthropic(request: dict[str, Any]) -> dict[str, Any]:
    import anthropic

    if not config.ANTHROPIC_API_KEY:
        raise LLMError(_LIVE_KEY_ERROR)
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, timeout=config.LLM_TIMEOUT_S, max_retries=0)
    skipped = {"temperature", "api_key", "anthropic_api_key"}
    kwargs = {k: v for k, v in request.items() if k not in skipped}
    if config.LLM_SEND_TEMPERATURE:
        kwargs["extra_body"] = {"temperature": request["temperature"]}
    try:
        resp = client.messages.create(**kwargs)
    except (anthropic.APITimeoutError, anthropic.APIConnectionError, anthropic.RateLimitError,
            anthropic.InternalServerError) as exc:
        _scrub(exc)
        raise TransientLLMError(secrets.redact_text(str(exc))) from None
    except anthropic.APIStatusError as exc:
        # claude-sonnet-5-5 rejects forced tool_choice types "tool" and "any", and it
        # accepts "auto". Retry once on that model before the caller falls back.
        choice = kwargs.get("tool_choice") or {}
        if (exc.status_code == 400 and choice.get("type") in {"any", "tool"}
                and "tool_choice" in str(exc)):
            retried = dict(kwargs)
            retried["tool_choice"] = {"type": "auto"}
            try:
                resp = client.messages.create(**retried)
            except anthropic.APIStatusError as retry_exc:
                _scrub(retry_exc)
                raise LLMError(secrets.redact_text(f"{retry_exc.status_code}: {retry_exc}")) from None
        else:
            _scrub(exc)
            raise LLMError(secrets.redact_text(f"{exc.status_code}: {exc}")) from None
    return {
        "content": [block.model_dump(mode="json", exclude_none=True) for block in resp.content],
        "stop_reason": resp.stop_reason,
        "model": resp.model,
        "usage": {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens},
    }


# Stub -------------------------------------------------------------------------------------

_fault_name: str | None = None


def _fault_path(name: str) -> Path:
    return config.ROOT_DIR / "tests" / "stubs" / f"{name}.json"


def set_stub_fault(name: str | None) -> None:
    """Serve tests/stubs/<name>.json instead of the offline heuristic. None clears it."""
    global _fault_name
    if name and not _fault_path(name).is_file():
        raise LLMError(f"unknown stub fault {name!r}; expected tests/stubs/{name}.json")
    _fault_name = name or None


def _active_fault() -> str:
    if _fault_name:
        return _fault_name
    return os.getenv("LLM_FAULT", "").strip()


def _fault_response(spec: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    kind = spec.get("error")
    if kind == "timeout":
        raise TransientLLMError(spec.get("message") or "injected timeout")
    if kind == "api":
        raise LLMError(spec.get("message") or "injected API error")
    if kind:
        raise LLMError(f"unknown stub fault error {kind!r}")
    tool = spec.get("apply_to_tool")
    chosen = (request.get("tool_choice") or {}).get("name")
    if tool and chosen != tool:
        from authpilot import stub_llm
        return stub_llm.respond(request)
    response = spec.get("response")
    if not isinstance(response, dict) or "content" not in response:
        raise LLMError(f"stub fault file for {tool or 'response'} is missing a response")
    return response


def _stub_caller(request: dict[str, Any]) -> dict[str, Any]:
    fault = _active_fault()
    if fault:
        path = _fault_path(fault)
        if not path.is_file():
            raise LLMError(f"unknown stub fault {fault!r}; expected {path}")
        return _fault_response(json.loads(path.read_text(encoding="utf-8")), request)
    from authpilot import stub_llm
    return stub_llm.respond(request)


# Swappable for tests and fault injection.
live_caller: Callable[[dict[str, Any]], dict[str, Any]] = _call_anthropic
stub_caller: Callable[[dict[str, Any]], dict[str, Any]] = _stub_caller
sleep: Callable[[float], None] = time.sleep


def _call_with_retries(caller: Callable[[dict[str, Any]], dict[str, Any]], request: dict[str, Any]) -> dict[str, Any]:
    attempts = config.LLM_MAX_RETRIES + 1
    for attempt in range(attempts):
        try:
            return caller(request)
        except TransientLLMError:
            if attempt == attempts - 1:
                raise
            sleep(config.LLM_BACKOFF_S * (2 ** attempt))
    raise AssertionError("unreachable")


def complete(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    model: str | None = None,
    temperature: float = 0.0,
    system: str | None = None,
    tool_choice: dict[str, Any] | None = None,
    max_tokens: int | None = None,
    mode: str | None = None,
    case_id: str = "-",
    purpose: str = "",
) -> LLMResponse:
    mode = mode or config.LLM_MODE
    if mode not in config.LLM_MODES:
        raise LLMError(f"unknown LLM mode {mode!r}. LLM_MODE must be one of {config.LLM_MODES}.")
    if mode == "live" and not config.ANTHROPIC_API_KEY:
        raise LLMError(_LIVE_KEY_ERROR)
    model = model or config.AGENT_MODEL
    prompt_version = config.PROMPT_VERSION
    request = build_request(messages, model, tools, system, tool_choice, temperature, max_tokens)
    key = request_key(request, prompt_version)
    started = time.perf_counter()
    try:
        if mode == "stub":
            raw, source = _call_with_retries(stub_caller, request), "stub"
        elif mode == "replay":
            entry = _load_cache().get(key)
            if entry is None:
                raise CacheMissError(
                    f"no cached response for model {model!r}, prompt {prompt_version}, key {key[:12]}. "
                    "Replay mode does not call the API or the stub."
                )
            raw, source = entry["response"], "cache"
        else:
            raw, source = _call_with_retries(live_caller, request), "live"
            _store(key, request, raw, prompt_version)
    except LLMError as exc:
        _scrub(exc)
        audit.log_event(case_id, "llm", "error", {
            "purpose": purpose, "model": model, "mode": mode, "prompt_version": prompt_version,
            "key": key, "error": secrets.redact_text(f"{type(exc).__name__}: {exc}"),
        })
        raise

    response = LLMResponse(
        content=raw["content"],
        stop_reason=raw.get("stop_reason"),
        model=raw.get("model", model),
        usage=dict(raw.get("usage", {})),
        latency_ms=round((time.perf_counter() - started) * 1000, 2),
        source=source,
    )
    audit.log_event(case_id, "llm", "llm_call", {
        "purpose": purpose, "model": model, "served_by": response.model, "mode": mode,
        "prompt_version": prompt_version, "source": source, "key": key,
        "latency_ms": response.latency_ms, **response.usage,
    })
    log.info(
        "llm call mode=%s model=%s source=%s latency_ms=%s input_tokens=%s output_tokens=%s",
        mode, model, source, response.latency_ms,
        response.usage.get("input_tokens", 0), response.usage.get("output_tokens", 0),
    )
    return response
