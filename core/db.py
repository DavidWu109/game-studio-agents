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

CREATE TABLE IF NOT EXISTS demands (
    id          TEXT PRIMARY KEY,
    title       TEXT,
    owner       TEXT,
    priority    INTEGER DEFAULT 2,
    deadline    TEXT,
    status      TEXT DEFAULT 'active',
    created_at  TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS demand_dispatches (
    demand_id   TEXT REFERENCES demands(id),
    dispatch_id TEXT REFERENCES dispatches(id),
    seq         INTEGER DEFAULT 0,
    PRIMARY KEY (demand_id, dispatch_id)
);

CREATE TABLE IF NOT EXISTS agent_instances (
    id          TEXT PRIMARY KEY,
    agent_type  TEXT,
    status      TEXT DEFAULT 'idle',
    current_task_id TEXT,
    current_demand_id TEXT,
    busy_since  TEXT,
    total_tasks_completed INTEGER DEFAULT 0
);
"""

MIGRATIONS = [
    "ALTER TABLE tasks ADD COLUMN demand_id TEXT",
    "ALTER TABLE tasks ADD COLUMN agent_instance_id TEXT",
    "ALTER TABLE tasks ADD COLUMN priority INTEGER DEFAULT 2",
    "ALTER TABLE tasks ADD COLUMN queued_at TEXT",
    "ALTER TABLE tasks ADD COLUMN depends_on TEXT",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> sqlite3.Connection:
    global _conn
    if _conn is not None:
        return _conn
    _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    _conn.executescript(SCHEMA)
    for migration in MIGRATIONS:
        try:
            _conn.execute(migration)
        except sqlite3.OperationalError:
            pass
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


# ---------------------------------------------------------------------------
# Demand CRUD (v2)
# ---------------------------------------------------------------------------

def record_demand(demand_id: str, title: str, owner: str = "",
                  priority: int = 2, deadline: Optional[str] = None):
    try:
        conn = _get_conn()
        with _lock:
            conn.execute(
                "INSERT OR REPLACE INTO demands (id, title, owner, priority, deadline, status, created_at) VALUES (?, ?, ?, ?, ?, 'active', ?)",
                (demand_id, title, owner, priority, deadline, _now()))
            conn.commit()
        emit_event("demand_created", data={"demand_id": demand_id, "title": title, "priority": priority})
    except Exception as e:
        logger.debug("record_demand failed: %s", e)


def link_demand_dispatch(demand_id: str, dispatch_id: str, seq: int = 0):
    try:
        conn = _get_conn()
        with _lock:
            conn.execute(
                "INSERT OR REPLACE INTO demand_dispatches (demand_id, dispatch_id, seq) VALUES (?, ?, ?)",
                (demand_id, dispatch_id, seq))
            conn.commit()
    except Exception as e:
        logger.debug("link_demand_dispatch failed: %s", e)


def get_demands(status: Optional[str] = None) -> list[dict]:
    conn = _get_conn()
    if status:
        rows = conn.execute(
            "SELECT * FROM demands WHERE status=? ORDER BY priority, created_at", (status,)).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM demands ORDER BY priority, created_at").fetchall()
    result = []
    for r in rows:
        d = dict(r)
        progress = conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN t.status='done' THEN 1 ELSE 0 END) as done,
                SUM(CASE WHEN t.status='in_progress' THEN 1 ELSE 0 END) as in_progress,
                SUM(CASE WHEN t.status IN ('blocked','failed') THEN 1 ELSE 0 END) as failed,
                SUM(t.total_cost_usd) as cost
            FROM tasks t
            JOIN demand_dispatches dd ON t.dispatch_id = dd.dispatch_id
            WHERE dd.demand_id = ?
        """, (d["id"],)).fetchone()
        d["progress"] = dict(progress) if progress else {}
        result.append(d)
    return result


def get_demand_detail(demand_id: str) -> Optional[dict]:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM demands WHERE id=?", (demand_id,)).fetchone()
    if not row:
        return None
    demand = dict(row)
    dispatches = conn.execute(
        "SELECT d.* FROM dispatches d JOIN demand_dispatches dd ON d.id = dd.dispatch_id WHERE dd.demand_id=? ORDER BY dd.seq",
        (demand_id,)).fetchall()
    demand["dispatches"] = [dict(d) for d in dispatches]
    tasks = conn.execute("""
        SELECT t.* FROM tasks t
        JOIN demand_dispatches dd ON t.dispatch_id = dd.dispatch_id
        WHERE dd.demand_id = ?
        ORDER BY t.started_at NULLS LAST
    """, (demand_id,)).fetchall()
    demand["tasks"] = [dict(t) for t in tasks]
    return demand


def finish_demand(demand_id: str, status: str = "done"):
    try:
        conn = _get_conn()
        with _lock:
            conn.execute(
                "UPDATE demands SET status=?, finished_at=? WHERE id=?",
                (status, _now(), demand_id))
            conn.commit()
        emit_event("demand_done", data={"demand_id": demand_id, "status": status})
    except Exception as e:
        logger.debug("finish_demand failed: %s", e)


# ---------------------------------------------------------------------------
# Agent instance CRUD (v2)
# ---------------------------------------------------------------------------

def record_agent_instance(instance_id: str, agent_type: str):
    try:
        conn = _get_conn()
        with _lock:
            conn.execute(
                "INSERT OR IGNORE INTO agent_instances (id, agent_type, status) VALUES (?, ?, 'idle')",
                (instance_id, agent_type))
            conn.commit()
    except Exception as e:
        logger.debug("record_agent_instance failed: %s", e)


def update_agent_instance(instance_id: str, status: str,
                          current_task_id: Optional[str] = None,
                          current_demand_id: Optional[str] = None):
    try:
        conn = _get_conn()
        with _lock:
            if status == "busy":
                conn.execute(
                    "UPDATE agent_instances SET status=?, current_task_id=?, current_demand_id=?, busy_since=? WHERE id=?",
                    (status, current_task_id, current_demand_id, _now(), instance_id))
            elif status == "idle":
                conn.execute("""
                    UPDATE agent_instances SET status='idle', current_task_id=NULL,
                    current_demand_id=NULL, busy_since=NULL,
                    total_tasks_completed = total_tasks_completed + 1
                    WHERE id=?""", (instance_id,))
            else:
                conn.execute("UPDATE agent_instances SET status=? WHERE id=?", (status, instance_id))
            conn.commit()
    except Exception as e:
        logger.debug("update_agent_instance failed: %s", e)


def get_agent_instances(agent_type: Optional[str] = None) -> list[dict]:
    conn = _get_conn()
    if agent_type:
        rows = conn.execute(
            "SELECT * FROM agent_instances WHERE agent_type=? ORDER BY id", (agent_type,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM agent_instances ORDER BY agent_type, id").fetchall()
    return [dict(r) for r in rows]


def get_pool_utilization() -> dict:
    conn = _get_conn()
    rows = conn.execute("""
        SELECT agent_type,
            COUNT(*) as total,
            SUM(CASE WHEN status='busy' THEN 1 ELSE 0 END) as busy,
            SUM(CASE WHEN status='idle' THEN 1 ELSE 0 END) as idle
        FROM agent_instances
        GROUP BY agent_type
    """).fetchall()
    return {r["agent_type"]: {"total": r["total"], "busy": r["busy"], "idle": r["idle"]} for r in rows}
