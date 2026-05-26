"""Dashboard SQLite database — event recording and state persistence.

All writes are protected by a threading.Lock. A threading.Event signals
new events to the SSE endpoint. If this module fails to initialize, all
public functions silently no-op so dispatch/planner are never affected.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("dashboard.db")

STUDIO_DIR = Path(__file__).parent.parent
DB_PATH = STUDIO_DIR / "dashboard.db"

_conn: Optional[sqlite3.Connection] = None
_lock = threading.Lock()
_new_event = threading.Event()

SCHEMA = """
CREATE TABLE IF NOT EXISTS dispatches (
    id          TEXT PRIMARY KEY,
    goal        TEXT,
    yaml_path   TEXT,
    status      TEXT DEFAULT 'active',
    created_at  TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
    id          TEXT PRIMARY KEY,
    dispatch_id TEXT REFERENCES dispatches(id),
    agent       TEXT,
    action      TEXT,
    input       TEXT,
    status      TEXT DEFAULT 'planned',
    result      TEXT,
    error       TEXT,
    started_at  TEXT,
    finished_at TEXT,
    total_input_tokens  INTEGER DEFAULT 0,
    total_output_tokens INTEGER DEFAULT 0,
    total_cost_usd      REAL DEFAULT 0.0,
    total_latency_ms    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS plan_steps (
    task_id     TEXT REFERENCES tasks(id),
    id          TEXT,
    description TEXT,
    instruction TEXT,
    expected_outcome TEXT,
    status      TEXT DEFAULT 'planned',
    result      TEXT,
    error       TEXT,
    retry_count INTEGER DEFAULT 0,
    provider    TEXT,
    model       TEXT,
    input_tokens  INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cost_usd    REAL DEFAULT 0.0,
    latency_ms  INTEGER DEFAULT 0,
    updated_at  TEXT,
    PRIMARY KEY (task_id, id)
);

CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp  TEXT,
    event_type TEXT,
    dispatch_id TEXT,
    task_id    TEXT,
    step_id    TEXT,
    phase      TEXT,
    data       TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> sqlite3.Connection:
    global _conn
    if _conn is not None:
        return _conn
    _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    _conn.executescript(SCHEMA)
    _conn.commit()
    logger.info("Dashboard DB initialized at %s", DB_PATH)
    return _conn


def _get_conn() -> sqlite3.Connection:
    if _conn is None:
        return init_db()
    return _conn


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------

def record_dispatch(dispatch_id: str, goal: str, yaml_path: str):
    try:
        conn = _get_conn()
        with _lock:
            conn.execute(
                "INSERT OR REPLACE INTO dispatches (id, goal, yaml_path, status, created_at) VALUES (?, ?, ?, 'active', ?)",
                (dispatch_id, goal, yaml_path, _now()))
            conn.commit()
        emit_event("dispatch_started", dispatch_id=dispatch_id)
    except Exception as e:
        logger.debug("record_dispatch failed: %s", e)


def record_task(task_id: str, dispatch_id: str, agent: str, action: str, input_text: str = ""):
    try:
        conn = _get_conn()
        with _lock:
            conn.execute(
                "INSERT OR REPLACE INTO tasks (id, dispatch_id, agent, action, input, status) VALUES (?, ?, ?, ?, ?, 'planned')",
                (task_id, dispatch_id, agent, action, input_text[:500]))
            conn.commit()
    except Exception as e:
        logger.debug("record_task failed: %s", e)


def record_step(task_id: str, step_id: str, description: str = "",
                instruction: str = "", expected_outcome: str = ""):
    try:
        conn = _get_conn()
        with _lock:
            conn.execute(
                "INSERT OR REPLACE INTO plan_steps (task_id, id, description, instruction, expected_outcome, status, updated_at) VALUES (?, ?, ?, ?, ?, 'planned', ?)",
                (task_id, step_id, description, instruction[:500], expected_outcome, _now()))
            conn.commit()
    except Exception as e:
        logger.debug("record_step failed: %s", e)


def update_task_status(task_id: str, status: str,
                       result: Optional[str] = None, error: Optional[str] = None):
    try:
        conn = _get_conn()
        with _lock:
            if status == "in_progress":
                conn.execute(
                    "UPDATE tasks SET status=?, started_at=? WHERE id=?",
                    (status, _now(), task_id))
            elif status in ("done", "blocked", "failed"):
                conn.execute(
                    "UPDATE tasks SET status=?, result=?, error=?, finished_at=? WHERE id=?",
                    (status, result[:500] if result else None,
                     error[:500] if error else None, _now(), task_id))
            else:
                conn.execute("UPDATE tasks SET status=? WHERE id=?", (status, task_id))
            conn.commit()
    except Exception as e:
        logger.debug("update_task_status failed: %s", e)


def update_step(task_id: str, step_id: str, status: str,
                result: Optional[str] = None, error: Optional[str] = None,
                provider_result: Any = None):
    try:
        conn = _get_conn()
        with _lock:
            fields = {"status": status, "updated_at": _now()}
            if result:
                fields["result"] = result[:500]
            if error:
                fields["error"] = error[:500]
            if provider_result:
                fields["provider"] = getattr(provider_result, "provider", "")
                fields["model"] = getattr(provider_result, "model", "")
                fields["input_tokens"] = getattr(provider_result, "input_tokens", 0)
                fields["output_tokens"] = getattr(provider_result, "output_tokens", 0)
                fields["cost_usd"] = getattr(provider_result, "cost_usd", 0.0)
                fields["latency_ms"] = getattr(provider_result, "latency_ms", 0)

            set_clause = ", ".join(f"{k}=?" for k in fields)
            values = list(fields.values()) + [task_id, step_id]
            conn.execute(
                f"UPDATE plan_steps SET {set_clause} WHERE task_id=? AND id=?",
                values)
            conn.commit()

            if provider_result:
                _accumulate_task_cost(task_id, provider_result)
    except Exception as e:
        logger.debug("update_step failed: %s", e)


def _accumulate_task_cost(task_id: str, pr: Any):
    try:
        conn = _get_conn()
        conn.execute("""
            UPDATE tasks SET
                total_input_tokens = total_input_tokens + ?,
                total_output_tokens = total_output_tokens + ?,
                total_cost_usd = total_cost_usd + ?,
                total_latency_ms = total_latency_ms + ?
            WHERE id = ?
        """, (getattr(pr, "input_tokens", 0), getattr(pr, "output_tokens", 0),
              getattr(pr, "cost_usd", 0.0), getattr(pr, "latency_ms", 0), task_id))
        conn.commit()
    except Exception as e:
        logger.debug("_accumulate_task_cost failed: %s", e)


def finish_dispatch(dispatch_id: str, status: str = "done"):
    try:
        conn = _get_conn()
        with _lock:
            conn.execute(
                "UPDATE dispatches SET status=?, finished_at=? WHERE id=?",
                (status, _now(), dispatch_id))
            conn.commit()
        emit_event("dispatch_done", dispatch_id=dispatch_id)
    except Exception as e:
        logger.debug("finish_dispatch failed: %s", e)


# ---------------------------------------------------------------------------
# Event stream
# ---------------------------------------------------------------------------

def emit_event(event_type: str, dispatch_id: Optional[str] = None,
               task_id: Optional[str] = None, step_id: Optional[str] = None,
               phase: Optional[str] = None, data: Optional[dict] = None):
    try:
        conn = _get_conn()
        data_json = json.dumps(data, ensure_ascii=False) if data else None
        with _lock:
            conn.execute(
                "INSERT INTO events (timestamp, event_type, dispatch_id, task_id, step_id, phase, data) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (_now(), event_type, dispatch_id, task_id, step_id, phase, data_json))
            conn.commit()
        _new_event.set()
    except Exception as e:
        logger.debug("emit_event failed: %s", e)


# ---------------------------------------------------------------------------
# Read operations (for API layer)
# ---------------------------------------------------------------------------

def get_dispatches() -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM dispatches ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def get_tasks(dispatch_id: Optional[str] = None, status: Optional[str] = None) -> list[dict]:
    conn = _get_conn()
    sql = "SELECT * FROM tasks WHERE 1=1"
    params: list = []
    if dispatch_id:
        sql += " AND dispatch_id=?"
        params.append(dispatch_id)
    if status:
        sql += " AND status=?"
        params.append(status)
    sql += " ORDER BY started_at DESC NULLS LAST"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def get_task_detail(task_id: str) -> Optional[dict]:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        return None
    task = dict(row)
    steps = conn.execute(
        "SELECT * FROM plan_steps WHERE task_id=? ORDER BY id", (task_id,)).fetchall()
    task["steps"] = [dict(s) for s in steps]
    return task


def get_events_since(last_id: int = 0, limit: int = 100) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM events WHERE id > ? ORDER BY id LIMIT ?",
        (last_id, limit)).fetchall()
    return [dict(r) for r in rows]


def get_stats() -> dict:
    conn = _get_conn()
    row = conn.execute("""
        SELECT
            COUNT(*) as total_tasks,
            SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) as done,
            SUM(CASE WHEN status='in_progress' THEN 1 ELSE 0 END) as in_progress,
            SUM(CASE WHEN status IN ('blocked','failed') THEN 1 ELSE 0 END) as failed,
            SUM(total_input_tokens) as total_input_tokens,
            SUM(total_output_tokens) as total_output_tokens,
            SUM(total_cost_usd) as total_cost_usd,
            SUM(total_latency_ms) as total_latency_ms
        FROM tasks
    """).fetchone()
    return dict(row) if row else {}
