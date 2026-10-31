"""Guards for make eval and make compare.

Stub mode is refused. Replay is allowed only when the cache was produced by a live run
with the same model and prompt version. Live mode requires a key and does not call the API
from this check.
"""

import json

from authpilot import config, llm, secrets


def require_eval_mode() -> None:
    mode = config.LLM_MODE
    if mode == "stub":
        raise SystemExit(
            "Refusing to run in stub mode. make eval and make compare require live mode, "
            "or replay mode when the cache was produced by a live run with the same model "
            "and prompt version. Stub results are not real."
        )
    if mode == "live":
        if not config.ANTHROPIC_API_KEY:
            raise SystemExit("Refusing to run in live mode because ANTHROPIC_API_KEY is not set.")
        return
    if mode == "replay":
        llm.require_live_cache()
        return
    raise SystemExit(f"Refusing to run: LLM_MODE must be live or replay, got {mode!r}.")


def dump_report(report: dict) -> str:
    """Stamp provenance onto a results file and strip anything that could hold a secret."""
    meta = dict(report.get("meta") or {})
    meta.update(config.result_provenance())
    report["meta"] = meta
    return json.dumps(secrets.redact(report), indent=2) + "\n"
