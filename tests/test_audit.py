import sqlite3

import pytest

from authpilot import audit


@pytest.fixture
def db(tmp_path):
    return tmp_path / "audit.sqlite3"


def test_events_round_trip_in_order(db):
    first = audit.log_event("c1", "agent", "tool_call", {"tool": "get_patient_record"}, db_path=db)
    second = audit.log_event("c1", "agent", "decision", {"status": "checking"}, db_path=db)
    audit.log_event("c2", "agent", "error", {"msg": "x"}, db_path=db)

    events = audit.read_events("c1", db_path=db)
    assert [e["id"] for e in events] == [first, second]
    assert events[0]["payload"] == {"tool": "get_patient_record"}
    assert events[1]["event_type"] == "decision"
    assert len(audit.read_events(db_path=db)) == 3


def test_unknown_event_type_rejected(db):
    with pytest.raises(ValueError):
        audit.log_event("c1", "agent", "gossip", {}, db_path=db)


@pytest.mark.parametrize("statement", ["UPDATE audit SET actor = 'x'", "DELETE FROM audit"])
def test_log_is_append_only(db, statement):
    audit.log_event("c1", "agent", "tool_call", {}, db_path=db)
    conn = sqlite3.connect(db)
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute(statement)
    conn.close()
    assert len(audit.read_events("c1", db_path=db)) == 1


def test_every_entry_records_mode_model_and_prompt(db):
    from authpilot import config
    audit.log_event("c1", "agent", "decision", {"status": "checking"}, db_path=db)
    event = audit.read_events("c1", db_path=db)[0]
    assert event["llm_mode"] == config.LLM_MODE == "stub"
    assert event["model_name"] == "stub-heuristic-v1"
    assert event["prompt_version"] == config.PROMPT_VERSION


def test_module_has_no_mutation_api():
    public = {name for name in dir(audit) if not name.startswith("_")}
    assert not {name for name in public if "delete" in name or "update" in name}
