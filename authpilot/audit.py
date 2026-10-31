"""Append-only audit log in SQLite. There is deliberately no update or delete API.

Every event carries the current run id (set with start_run) so one agent run can be replayed
as a timeline even when the same case is run several times.
"""

import json
import sqlite3
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Literal

from authpilot import config, secrets

EventType = Literal["tool_call", "tool_result", "llm_call", "decision", "error", "fallback", "human_action"]
EVENT_TYPES = ("tool_call", "tool_result", "llm_call", "decision", "error", "fallback", "human_action")

_run_id: ContextVar[str] = ContextVar("audit_run_id", default="")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    case_id TEXT NOT NULL,
    actor TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    run_id TEXT NOT NULL DEFAULT '',
    llm_mode TEXT NOT NULL DEFAULT '',
    model_name TEXT NOT NULL DEFAULT '',
    prompt_version TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_audit_case ON audit(case_id);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit
BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit
BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
"""


@contextmanager
def _connect(db_path: Path | None) -> Iterator[sqlite3.Connection]:
    path = Path(db_path or config.AUDIT_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(_SCHEMA)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(audit)")}
        for column, typedef in (
            ("run_id", "TEXT NOT NULL DEFAULT ''"),
            ("llm_mode", "TEXT NOT NULL DEFAULT ''"),
            ("model_name", "TEXT NOT NULL DEFAULT ''"),
            ("prompt_version", "TEXT NOT NULL DEFAULT ''"),
        ):
            if column not in columns:
                conn.execute(f"ALTER TABLE audit ADD COLUMN {column} {typedef}")
        with conn:
            yield conn
    finally:
        conn.close()


def start_run(run_id: str | None = None) -> str:
    run_id = run_id or uuid.uuid4().hex[:12]
    _run_id.set(run_id)
    return run_id


def current_run() -> str:
    return _run_id.get()


def log_event(
    case_id: str,
    actor: str,
    event_type: EventType,
    payload: dict[str, Any],
    db_path: Path | None = None,
) -> int:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unknown event_type {event_type!r}")
    ts = datetime.now(timezone.utc).isoformat()
    body = json.dumps(secrets.redact(payload), sort_keys=True, default=str)
    with _connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO audit (ts, case_id, actor, event_type, payload_json, run_id, llm_mode, model_name, "
            "prompt_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ts, case_id, actor, event_type, body, _run_id.get(), config.LLM_MODE,
             config.configured_model_name(), config.PROMPT_VERSION),
        )
        return int(cur.lastrowid)


def read_events(case_id: str | None = None, db_path: Path | None = None,
                run_id: str | None = None) -> list[dict[str, Any]]:
    query = ("SELECT id, ts, case_id, actor, event_type, payload_json, run_id, "
             "llm_mode, model_name, prompt_version FROM audit")
    clauses, params = [], []
    if case_id is not None:
        clauses.append("case_id = ?")
        params.append(case_id)
    if run_id is not None:
        clauses.append("run_id = ?")
        params.append(run_id)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY id"
    with _connect(db_path) as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    return [
        {
            "id": row["id"],
            "ts": row["ts"],
            "case_id": row["case_id"],
            "actor": row["actor"],
            "event_type": row["event_type"],
            "payload": json.loads(row["payload_json"]),
            "run_id": row["run_id"],
            "llm_mode": row["llm_mode"],
            "model_name": row["model_name"],
            "prompt_version": row["prompt_version"],
        }
        for row in rows
    ]
