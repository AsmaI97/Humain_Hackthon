import pytest

from authpilot import config, ehr, llm, store
from authpilot.payer_mock import app as payer_app
from authpilot.tools import check_criteria


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(config, "AUDIT_DB_PATH", tmp_path / "audit.sqlite3")
    monkeypatch.setattr(config, "CASE_STORE_DIR", tmp_path / "cases")
    monkeypatch.setattr(config, "LLM_CACHE_PATH", tmp_path / "llm_cache.jsonl")
    monkeypatch.setattr(config, "LLM_MODE", "stub")
    monkeypatch.setattr(config, "PAYER_URL", "inprocess")
    monkeypatch.delenv("LLM_FAULT", raising=False)
    llm.set_stub_fault(None)
    monkeypatch.setattr(llm, "sleep", lambda s: None)
    payer_app.reset()
    llm.reset_cache()
    store.clear()
    ehr.clear_overrides()
    check_criteria.clear_criteria_cache()
    yield
    llm.reset_cache()
    store.clear()
    ehr.clear_overrides()
    check_criteria.clear_criteria_cache()
