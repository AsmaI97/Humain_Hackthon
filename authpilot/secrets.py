"""Strip secret material before it is written to disk or a log line.

The Anthropic key is read from the environment at redact time. This module never logs it.
"""

import os
import re

_SK_ANT = re.compile(r"sk-ant[A-Za-z0-9_\-]*")
_SENSITIVE_KEYS = {
    "api_key", "apikey", "api-key", "authorization", "x-api-key",
    "anthropic_api_key", "anthropic-api-key",
}


def _secret() -> str:
    return os.environ.get("ANTHROPIC_API_KEY") or ""


def redact_text(text: str, secret: str | None = None) -> str:
    secret = _secret() if secret is None else secret
    if secret and secret in text:
        text = text.replace(secret, "[redacted]")
    if "sk-ant" in text:
        text = _SK_ANT.sub("[redacted]", text)
    return text


def redact(value, secret: str | None = None):
    """Return a copy with secret-bearing strings and sensitive fields removed."""
    secret = _secret() if secret is None else secret
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if str(key).lower().replace("_", "-") in _SENSITIVE_KEYS or str(key).lower() in _SENSITIVE_KEYS:
                cleaned[key] = "[redacted]"
            else:
                cleaned[key] = redact(item, secret)
        return cleaned
    if isinstance(value, list):
        return [redact(item, secret) for item in value]
    if isinstance(value, str):
        return redact_text(value, secret)
    return value
