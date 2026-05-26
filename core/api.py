"""Dashboard API — FastAPI server with REST + SSE endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from core.db import (
    init_db, get_dispatches, get_tasks, get_task_detail,
    get_events_since, get_stats, update_task_status, emit_event,
    get_demands, get_demand_detail, get_agent_instances, get_pool_utilization,
    _new_event,
)

logger = logging.getLogger("dashboard.api")

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Anvil Dashboard", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def startup():
    init_db()
    logger.info("Dashboard API started")


@app.get("/")
def index():
    html_path = STATIC_DIR / "dashboard.html"
    if html_path.exists():
        return FileResponse(html_path, media_type="text/html")
    return HTMLResponse("<h1>Anvil Dashboard</h1><p>dashboard.html not found</p>")


@app.get("/api/dispatches")
def api_dispatches():
    return get_dispatches()


@app.get("/api/tasks")
def api_tasks(dispatch_id: Optional[str] = None, status: Optional[str] = None):
    return get_tasks(dispatch_id=dispatch_id, status=status)


@app.get("/api/tasks/{task_id}")
def api_task_detail(task_id: str):
    detail = get_task_detail(task_id)
    if not detail:
        return {"error": "not found"}
    return detail


@app.get("/api/stats")
def api_stats():
    return get_stats()


@app.get("/api/events")
async def api_events(last_id: int = Query(0)):
    async def event_stream():
        current_id = last_id
        while True:
            events = get_events_since(current_id)
            for ev in events:
                current_id = ev["id"]
                yield f"id: {ev['id']}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"

            _new_event.clear()
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(_new_event.wait, 30), timeout=35
                )
            except asyncio.TimeoutError:
                yield f": keepalive\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/tasks/{task_id}/cancel")
def api_cancel_task(task_id: str):
    update_task_status(task_id, "blocked", error="cancelled by operator")
    emit_event("task_cancelled", task_id=task_id, data={"reason": "operator"})
    return {"ok": True, "task_id": task_id}


# ---------------------------------------------------------------------------
# v2 API — demands, pools, graph
# ---------------------------------------------------------------------------

@app.get("/api/v2/overview")
def api_v2_overview():
    scheduler = getattr(app.state, "scheduler", None)
    return {
        "pools": get_pool_utilization(),
        "demands": get_demands(status="active"),
        "resources": scheduler.get_state().get("active_tasks", []) if scheduler else [],
        "stats": get_stats(),
    }


@app.get("/api/v2/demands")
def api_v2_demands(status: Optional[str] = None):
    return get_demands(status=status)


@app.get("/api/v2/demands/{demand_id}")
def api_v2_demand_detail(demand_id: str):
    detail = get_demand_detail(demand_id)
    if not detail:
        return {"error": "not found"}
    return detail


@app.get("/api/v2/demands/{demand_id}/graph")
def api_v2_demand_graph(demand_id: str):
    detail = get_demand_detail(demand_id)
    if not detail:
        return {"error": "not found"}
    nodes = []
    edges = []
    for task in detail.get("tasks", []):
        nodes.append({
            "id": task["id"],
            "agent": task["agent"],
            "action": task.get("action", ""),
            "status": task["status"],
            "agent_instance": task.get("agent_instance_id"),
            "cost": task.get("total_cost_usd", 0),
        })
        deps = task.get("depends_on")
        if deps:
            if isinstance(deps, str):
                try:
                    deps = json.loads(deps)
                except Exception:
                    deps = [deps]
            for dep in deps:
                edges.append({"source": dep, "target": task["id"]})
    return {"demand_id": demand_id, "nodes": nodes, "edges": edges}


@app.get("/api/v2/agents/{agent_type}")
def api_v2_agent_detail(agent_type: str):
    instances = get_agent_instances(agent_type)
    scheduler = getattr(app.state, "scheduler", None)
    queue_depth = scheduler.get_queue_depth(agent_type) if scheduler else 0
    return {"agent_type": agent_type, "instances": instances, "queue_depth": queue_depth}


@app.post("/api/v2/demands")
def api_v2_create_demand(body: dict):
    scheduler = getattr(app.state, "scheduler", None)
    if not scheduler:
        return {"error": "scheduler not available"}

    title = body.get("title", "")
    priority = body.get("priority", 2)
    dispatches = body.get("dispatches", [])
    demand_id = body.get("demand_id", f"demand_{int(time.time())}")

    dispatch_paths = []
    for dp in dispatches:
        p = Path(dp)
        if not p.is_absolute():
            p = Path(__file__).parent.parent / p
        if p.exists():
            dispatch_paths.append(p)

    if not dispatch_paths:
        return {"error": "no valid dispatch paths"}

    scheduler.submit_demand(demand_id, title, priority, dispatch_paths)
    return {"ok": True, "demand_id": demand_id}


@app.post("/api/v2/demands/{demand_id}/pause")
def api_v2_pause_demand(demand_id: str):
    scheduler = getattr(app.state, "scheduler", None)
    if scheduler:
        scheduler.pause_demand(demand_id)
    return {"ok": True, "demand_id": demand_id}


if __name__ == "__main__":
    import uvicorn
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(app, host="0.0.0.0", port=8420)
