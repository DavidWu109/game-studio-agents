"""StudioDaemon — top-level coordinator with scheduler + dashboard API.

Drives the Scheduler in a tick loop and serves the dashboard API.

Usage:
    python3 -m core.daemon                    # foreground (scheduler + API)
    python3 -m core.daemon --once             # single tick, then exit
    python3 -m core.daemon --api-only         # dashboard API only, no scheduling
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from pathlib import Path
from typing import Dict, Optional

import yaml

logger = logging.getLogger("daemon")

DISPATCH_INBOX = Path("~/Projects/gopoo-studio-project/studio/tasks/").expanduser()
PLANS_DIR = Path(__file__).parent.parent / "plans"
TICK_INTERVAL = 10


class StudioDaemon:

    def __init__(self):
        from core.scheduler import Scheduler
        from core.db import init_db
        init_db()
        self._scheduler = Scheduler()
        self._scanned_files: set = set()

    def run(self, once: bool = False):
        logger.info("Daemon started (tick_interval=%ds)", TICK_INTERVAL)

        # Warm MCP session
        try:
            subprocess.run(["bash", "/tmp/mcp.sh", "init"],
                           capture_output=True, timeout=10)
        except Exception:
            pass

        while True:
            try:
                self._tick()
            except Exception as e:
                logger.error("Tick error: %s", e)
            if once:
                break
            time.sleep(TICK_INTERVAL)

    def _tick(self):
        self._scan_demands()
        scheduled = self._scheduler.tick()
        self._scheduler.cleanup_finished()
        if scheduled:
            logger.info("Tick: scheduled %d tasks", scheduled)

    def _scan_demands(self):
        """Scan for demand YAML files (new format) and legacy dispatch YAML."""
        for inbox in [DISPATCH_INBOX, PLANS_DIR]:
            if not inbox.exists():
                continue
            for f in inbox.glob("*.yaml"):
                if f in self._scanned_files:
                    continue
                self._scanned_files.add(f)
                try:
                    data = yaml.safe_load(f.read_text())
                except Exception:
                    continue
                if not data:
                    continue
                if "demand_id" in data:
                    self._load_demand(f, data)
                elif "tasks" in data:
                    self._load_legacy_dispatch(f, data)

    def _load_demand(self, path: Path, data: dict):
        demand_id = data["demand_id"]
        title = data.get("title", demand_id)
        priority = data.get("priority", 2)
        dispatch_entries = data.get("dispatches", [])

        dispatch_paths = []
        for entry in dispatch_entries:
            dp = entry.get("path", entry) if isinstance(entry, dict) else entry
            dp_path = Path(dp)
            if not dp_path.is_absolute():
                dp_path = path.parent / dp_path
            if dp_path.exists():
                dispatch_paths.append(dp_path)

        if dispatch_paths:
            self._scheduler.submit_demand(demand_id, title, priority, dispatch_paths)
            logger.info("Loaded demand: %s (P%d, %d dispatches)", demand_id, priority, len(dispatch_paths))

    def _load_legacy_dispatch(self, path: Path, data: dict):
        """Wrap a bare dispatch YAML as a P2 demand."""
        task_id = data.get("task_id", path.stem)
        goal = data.get("goal", task_id)

        all_done = all(t.get("status") in ("done", "blocked") for t in data.get("tasks", []))
        if all_done:
            return

        self._scheduler.submit_demand(
            demand_id=task_id,
            title=goal,
            priority=2,
            dispatch_paths=[path],
        )
        logger.info("Loaded legacy dispatch as P2 demand: %s", task_id)

    @property
    def scheduler(self):
        return self._scheduler


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

    p = argparse.ArgumentParser(description="Anvil Daemon — scheduler + dashboard")
    p.add_argument("--once", action="store_true", help="Single tick, then exit")
    p.add_argument("--api-only", action="store_true", help="Dashboard API only, no scheduling")
    p.add_argument("--port", type=int, default=8420, help="Dashboard API port")
    args = p.parse_args()

    daemon = StudioDaemon()

    if args.api_only:
        _start_api(daemon, args.port)
        return

    # Start API in background thread
    api_thread = threading.Thread(target=_start_api, args=(daemon, args.port), daemon=True)
    api_thread.start()

    daemon.run(once=args.once)


def _start_api(daemon: StudioDaemon, port: int):
    import uvicorn
    from core.api import app

    app.state.scheduler = daemon.scheduler
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


if __name__ == "__main__":
    main()
