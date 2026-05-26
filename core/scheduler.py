"""Global task scheduler — agent pools + priority queue + resource allocation.

Sits between the daemon and dispatch.run_task(). Manages:
- Agent instance pools (configurable size per type)
- Cross-demand priority scheduling (P0 > P1 > P2 > P3)
- Shared resource locks (semaphore-based)
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from core.dispatch import (
    ResourceManager, load_dispatch, get_ready_tasks,
    mark_status, run_task,
)

logger = logging.getLogger("scheduler")

STUDIO_DIR = Path(__file__).parent.parent


def load_pool_config() -> dict:
    cfg_path = STUDIO_DIR / "config.yaml"
    if cfg_path.exists():
        cfg = yaml.safe_load(cfg_path.read_text())
        return cfg.get("agent_pools", {})
    return {}


def load_resource_config() -> dict:
    cfg_path = STUDIO_DIR / "config.yaml"
    if cfg_path.exists():
        cfg = yaml.safe_load(cfg_path.read_text())
        return cfg.get("resources", {"comfyui": 1, "unity_mcp": 1})
    return {"comfyui": 1, "unity_mcp": 1}


# ---------------------------------------------------------------------------
# Agent Pool
# ---------------------------------------------------------------------------

class AgentPool:

    def __init__(self, agent_type: str, pool_size: int):
        self.agent_type = agent_type
        self.pool_size = pool_size
        self._instances: Dict[str, Optional[str]] = {}
        self._lock = threading.Lock()

        for i in range(pool_size):
            instance_id = f"{agent_type}_{i}"
            self._instances[instance_id] = None

        try:
            from core.db import record_agent_instance
            for iid in self._instances:
                record_agent_instance(iid, agent_type)
        except Exception:
            pass

    def acquire(self) -> Optional[str]:
        with self._lock:
            for iid, task_id in self._instances.items():
                if task_id is None:
                    return iid
        return None

    def mark_busy(self, instance_id: str, task_id: str, demand_id: str = ""):
        with self._lock:
            self._instances[instance_id] = task_id
        try:
            from core.db import update_agent_instance
            update_agent_instance(instance_id, "busy",
                                  current_task_id=task_id, current_demand_id=demand_id)
        except Exception:
            pass

    def release(self, instance_id: str):
        with self._lock:
            self._instances[instance_id] = None
        try:
            from core.db import update_agent_instance
            update_agent_instance(instance_id, "idle")
        except Exception:
            pass

    def idle_count(self) -> int:
        with self._lock:
            return sum(1 for v in self._instances.values() if v is None)

    def utilization(self) -> float:
        busy = self.pool_size - self.idle_count()
        return busy / self.pool_size if self.pool_size > 0 else 0.0

    def get_state(self) -> dict:
        with self._lock:
            return {
                "agent_type": self.agent_type,
                "total": self.pool_size,
                "busy": sum(1 for v in self._instances.values() if v is not None),
                "idle": sum(1 for v in self._instances.values() if v is None),
                "instances": {k: v for k, v in self._instances.items()},
            }


# ---------------------------------------------------------------------------
# Queued Task
# ---------------------------------------------------------------------------

@dataclass
class QueuedTask:
    raw: dict
    yaml_path: Path
    demand_id: str
    priority: int
    agent_type: str
    action: str
    task_id: str
    queued_at: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Active Demand
# ---------------------------------------------------------------------------

@dataclass
class ActiveDemand:
    demand_id: str
    title: str
    priority: int
    dispatch_paths: List[Path]
    status: str = "active"


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

class Scheduler:

    def __init__(self):
        pool_config = load_pool_config()
        resource_config = load_resource_config()

        self._pools: Dict[str, AgentPool] = {
            agent_type: AgentPool(agent_type, size)
            for agent_type, size in pool_config.items()
        }
        self._resources = ResourceManager(resource_config)
        self._demands: Dict[str, ActiveDemand] = {}
        self._executor = ThreadPoolExecutor(max_workers=sum(pool_config.values()) or 12)
        self._active_futures: Dict[str, Any] = {}
        self._lock = threading.Lock()

        logger.info("Scheduler initialized: pools=%s resources=%s",
                     {k: v.pool_size for k, v in self._pools.items()}, resource_config)

    def submit_demand(self, demand_id: str, title: str, priority: int,
                      dispatch_paths: List[Path]):
        demand = ActiveDemand(
            demand_id=demand_id, title=title, priority=priority,
            dispatch_paths=[Path(p).resolve() for p in dispatch_paths],
        )
        with self._lock:
            self._demands[demand_id] = demand

        try:
            from core.db import record_demand, record_dispatch, record_task, link_demand_dispatch
            record_demand(demand_id, title, priority=priority)
            for i, dp in enumerate(demand.dispatch_paths):
                data = load_dispatch(dp)
                dispatch_id = dp.stem
                record_dispatch(dispatch_id, data.get("goal", ""), str(dp))
                link_demand_dispatch(demand_id, dispatch_id, seq=i)
                for t in data.get("tasks", []):
                    record_task(t["id"], dispatch_id, t["agent"], t["action"], t.get("input", "")[:500])
        except Exception as e:
            logger.debug("submit_demand db recording failed: %s", e)

        logger.info("Demand submitted: %s (P%d, %d dispatches)", demand_id, priority, len(dispatch_paths))

    def tick(self) -> int:
        ready = self._collect_ready_tasks()
        ready.sort(key=lambda t: (t.priority, t.queued_at))

        dispatched = 0
        for task in ready:
            if self._try_schedule(task):
                dispatched += 1

        return dispatched

    def _collect_ready_tasks(self) -> List[QueuedTask]:
        tasks = []
        with self._lock:
            demands = list(self._demands.values())

        for demand in demands:
            if demand.status != "active":
                continue
            for dp in demand.dispatch_paths:
                try:
                    data = load_dispatch(dp)
                except Exception:
                    continue
                for task in get_ready_tasks(data):
                    task_id = task["id"]
                    if task_id in self._active_futures:
                        continue
                    tasks.append(QueuedTask(
                        raw=task, yaml_path=dp,
                        demand_id=demand.demand_id,
                        priority=demand.priority,
                        agent_type=task["agent"],
                        action=task["action"],
                        task_id=task_id,
                    ))
        return tasks

    def _try_schedule(self, qt: QueuedTask) -> bool:
        pool = self._pools.get(qt.agent_type)
        if pool is None:
            pool = self._pools.setdefault(
                qt.agent_type, AgentPool(qt.agent_type, 1))

        instance_id = pool.acquire()
        if instance_id is None:
            return False

        if not self._resources.acquire(qt.agent_type, qt.action):
            return False

        pool.mark_busy(instance_id, qt.task_id, qt.demand_id)

        future = self._executor.submit(
            run_task, qt.raw, qt.yaml_path, self._resources)
        self._active_futures[qt.task_id] = future

        future.add_done_callback(
            lambda f: self._on_complete(f, qt, instance_id))

        try:
            from core.db import update_task_status, emit_event
            update_task_status(qt.task_id, "in_progress")
            emit_event("task_scheduled", task_id=qt.task_id,
                       data={"demand_id": qt.demand_id, "instance": instance_id,
                             "priority": qt.priority})
        except Exception:
            pass

        logger.info("Scheduled: %s → %s (demand=%s, P%d)",
                     qt.task_id, instance_id, qt.demand_id, qt.priority)
        return True

    def _on_complete(self, future, qt: QueuedTask, instance_id: str):
        pool = self._pools.get(qt.agent_type)
        if pool:
            pool.release(instance_id)
        self._resources.release(qt.agent_type, qt.action)
        self._active_futures.pop(qt.task_id, None)

        try:
            tid, result = future.result(timeout=5)
            is_error = result.startswith("ERROR:") or result.startswith("SAFETY_BLOCK:")
            if is_error:
                mark_status(qt.yaml_path, tid, "blocked", error=result)
                try:
                    from core.db import update_task_status, emit_event
                    update_task_status(tid, "blocked", error=result)
                    emit_event("task_blocked", task_id=tid,
                               data={"demand_id": qt.demand_id, "error": result[:200]})
                except Exception:
                    pass
            else:
                mark_status(qt.yaml_path, tid, "done", result=result)
                try:
                    from core.db import update_task_status, emit_event
                    update_task_status(tid, "done", result=result)
                    emit_event("task_done", task_id=tid,
                               data={"demand_id": qt.demand_id, "result": result[:200]})
                except Exception:
                    pass
        except Exception as e:
            mark_status(qt.yaml_path, qt.task_id, "blocked", error=str(e)[:300])
            logger.error("Task %s failed: %s", qt.task_id, e)

        logger.info("Completed: %s → %s released", qt.task_id, instance_id)

    def pause_demand(self, demand_id: str):
        with self._lock:
            d = self._demands.get(demand_id)
            if d:
                d.status = "paused"
        try:
            from core.db import emit_event
            emit_event("demand_paused", data={"demand_id": demand_id})
        except Exception:
            pass

    def resume_demand(self, demand_id: str):
        with self._lock:
            d = self._demands.get(demand_id)
            if d:
                d.status = "active"

    def cleanup_finished(self):
        with self._lock:
            for did, demand in list(self._demands.items()):
                if demand.status != "active":
                    continue
                all_done = True
                for dp in demand.dispatch_paths:
                    try:
                        data = load_dispatch(dp)
                        for t in data.get("tasks", []):
                            if t.get("status") not in ("done", "blocked"):
                                all_done = False
                                break
                    except Exception:
                        all_done = False
                    if not all_done:
                        break
                if all_done:
                    demand.status = "done"
                    try:
                        from core.db import finish_demand
                        finish_demand(did)
                    except Exception:
                        pass
                    logger.info("Demand completed: %s", did)

    def get_state(self) -> dict:
        return {
            "pools": {k: v.get_state() for k, v in self._pools.items()},
            "demands": {k: {"title": v.title, "priority": v.priority, "status": v.status}
                        for k, v in self._demands.items()},
            "active_tasks": list(self._active_futures.keys()),
        }

    def get_queue_depth(self, agent_type: str) -> int:
        ready = self._collect_ready_tasks()
        return sum(1 for t in ready if t.agent_type == agent_type)
