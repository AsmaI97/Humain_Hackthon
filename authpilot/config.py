"""Environment-driven settings. Nothing model- or threshold-related is hard-coded elsewhere.

The API key is loaded from the environment (a local .env is read once, here). It is never logged.
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

PACKAGE_DIR = ROOT_DIR / "authpilot"
DATA_DIR = PACKAGE_DIR / "data"
POLICIES_DIR = DATA_DIR / "policies"
CASES_DIR = DATA_DIR / "cases"
RUNTIME_DIR = Path(os.getenv("AUTHPILOT_RUNTIME_DIR", ROOT_DIR / "runtime"))
AUDIT_DB_PATH = Path(os.getenv("AUDIT_DB_PATH", RUNTIME_DIR / "audit.sqlite3"))
LLM_CACHE_PATH = Path(os.getenv("LLM_CACHE_PATH", ROOT_DIR / "cache" / "llm_cache.jsonl"))
CASE_STORE_DIR = Path(os.getenv("CASE_STORE_DIR", RUNTIME_DIR / "cases"))
RESULTS_DIR = ROOT_DIR / "results"

def _setting(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip()


ANTHROPIC_API_KEY = _setting("ANTHROPIC_API_KEY")

LLM_MODES = ("live", "replay", "stub")


def resolve_llm_mode(raw: str | None) -> str:
    mode = (raw or "").strip() or "replay"
    if mode not in LLM_MODES:
        raise ValueError(
            f"LLM_MODE must be one of {LLM_MODES}, got {mode!r}. "
            "Use live to call the API and fill the replay cache."
        )
    return mode


LLM_MODE = resolve_llm_mode(os.getenv("LLM_MODE"))

AGENT_MODEL = _setting("AGENT_MODEL", "claude-sonnet-5-5")
CHEAP_MODEL = _setting("CHEAP_MODEL", "claude-haiku-5-5")
ESCALATION_MODEL = _setting("ESCALATION_MODEL", "claude-opus-5-5")

LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "60"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "3"))
LLM_BACKOFF_S = float(os.getenv("LLM_BACKOFF_S", "1.0"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1024"))
# Current models reject temperature as an extra field. The value still identifies the cache key.
# Set LLM_SEND_TEMPERATURE=1 only for an endpoint that accepts it.
LLM_SEND_TEMPERATURE = os.getenv("LLM_SEND_TEMPERATURE", "0") == "1"

# Letter languages: "en" or "en,ar". The Arabic version is built by code from the verified
# English statements (quotes stay verbatim), so it needs no model call.
LETTER_LANGUAGES = [lang.strip() for lang in os.getenv("LETTER_LANGUAGES", "en,ar").split(",") if lang.strip()]

PROMPT_VERSION = "p3.0"
RETRIEVAL_K = 3
RETRIEVAL_WIDE_K = 6
RETRIEVAL_MIN_SCORE = float(os.getenv("RETRIEVAL_MIN_SCORE", "1.0"))

CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.7"))

# Ablation switches (evaluation turns these off one at a time).
USE_RETRIEVAL = True
VERIFY_CITATIONS = True

MAX_GAP_LOOPS = 2
MAX_APPEALS = 2
MAX_TOOL_CALLS = 12
MAX_INVALID_OUTPUT_RETRIES = 2

DEV_SEED = 1001
SEALED_SEED = 2002
UNSEEN_SEED = 3003
DEV_CASES = 60
SEALED_CASES = 40
UNSEEN_CASES = 10
EVAL_SEED = 4004

# "inprocess" runs the mock payer inside this process; set a URL to use a running server.
PAYER_URL = os.getenv("PAYER_URL", "inprocess")
PAYER_TIMEOUT_S = float(os.getenv("PAYER_TIMEOUT_S", "10"))
PAYER_MAX_RETRIES = int(os.getenv("PAYER_MAX_RETRIES", "2"))
PAYER_BACKOFF_S = float(os.getenv("PAYER_BACKOFF_S", "0.5"))


def configured_model_name() -> str:
    """Model name recorded on audit rows and results. Stub runs keep the heuristic's name."""
    if LLM_MODE == "stub":
        from authpilot.stub_llm import STUB_MODEL
        return STUB_MODEL
    return AGENT_MODEL


def result_provenance() -> dict:
    """llm mode, model name and prompt version, stamped onto every saved results file."""
    if LLM_MODE == "stub":
        from authpilot.stub_llm import STUB_MODEL
        model = STUB_MODEL
        return {
            "llm_mode": LLM_MODE,
            "model": model,
            "agent_model": model,
            "cheap_model": model,
            "escalation_model": None,
            "prompt_version": PROMPT_VERSION,
        }
    return {
        "llm_mode": LLM_MODE,
        "model": AGENT_MODEL,
        "agent_model": AGENT_MODEL,
        "cheap_model": CHEAP_MODEL,
        "escalation_model": ESCALATION_MODEL,
        "prompt_version": PROMPT_VERSION,
    }


def log_api_key_status() -> None:
    """Log whether a key is set. The message is only 'API key present: yes' or 'no'."""
    logger = logging.getLogger("authpilot")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.propagate = False
    logger.info("API key present: %s", "yes" if ANTHROPIC_API_KEY else "no")
    if LLM_MODE == "live" and not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Live mode cannot start. "
            "Replay and stub modes work without a key."
        )


log_api_key_status()
