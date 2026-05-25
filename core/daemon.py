"""StudioDaemon — top-level coordinator for autonomous agent operation.

Interface #4: Hierarchical coordination via daemon + message bus.

The daemon is the "Studio Director" runtime. It:
1. Watches for new dispatch YAML files (PjM output)
2. Launches dispatch_loop() per file
3. Processes cross-agent messages (inbox routing)
4. Checks replan triggers and invokes PjM.replan()
5. Manages agent lifecycle (tick each agent's loop())

NOT YET IMPLEMENTED. This file defines the interface and contracts.

Usage (when implemented):
    python3 -m core.daemon                    # foreground
    python3 -m core.daemon --daemonize        # background
    python3 -m core.daemon --once             # single tick (for cron)

Dependencies:
    - core/dispatch.py (dispatch_loop, _check_replan_triggers)
    - core/agent.py (StudioAgent.loop, .replan, .on_qa_feedback)
    - core/search.py (agentic_search — for PjM replan context)
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("daemon")

# Where PjM drops new dispatch YAML files for the daemon to pick up
DISPATCH_INBOX = Path("~/Projects/gopoo-studio-project/studio/tasks/").expanduser()

# How often the daemon ticks (seconds)
TICK_INTERVAL = 30

# Agent departments to tick on each round
ACTIVE_DEPARTMENTS = [
    "art", "engineering", "qa", "design", "studio", "pjm", "pm",
    "go-dev", "cd", "marketing",
]


class StudioDaemon:
    """Top-level coordinator. Runs as a long-lived process.

    Responsibilities:
    - Watch DISPATCH_INBOX for new .yaml files with status != all-done
    - For each active dispatch, run dispatch_loop() in a thread
    - Route cross-agent messages (check all agent inboxes)
    - Trigger PjM replan when conditions are met
    - Call agent.loop() for each department on schedule

    Does NOT:
    - Make creative decisions (that's the agents' job)
    - Modify task inputs (that's PjM replan or agent.on_qa_feedback)
    - Override safety boundaries (that's core/safety.py)
    """

    def __init__(self, studio_dir: str = "."):
        self.studio_dir = Path(studio_dir)
        self._active_dispatches: Dict[Path, "threading.Thread"] = {}
        self._agents: Dict[str, "StudioAgent"] = {}

    def run(self, once: bool = False):
        """Main daemon loop.

        Args:
            once: if True, run a single tick and exit (for cron mode)
        """
        # TODO: implement
        # while True:
        #     self._tick()
        #     if once:
        #         break
        #     time.sleep(TICK_INTERVAL)
        raise NotImplementedError

    def _tick(self):
        """Single daemon tick. Called every TICK_INTERVAL seconds.

        Order of operations:
        1. Scan for new dispatch YAMLs
        2. Check active dispatches for replan triggers
        3. Route pending messages across agent inboxes
        4. Tick each agent's loop() for background work
        """
        # TODO: implement
        # self._scan_dispatches()
        # self._check_replans()
        # self._route_messages()
        # self._tick_agents()
        raise NotImplementedError

    def _scan_dispatches(self):
        """Find new dispatch YAML files and start dispatch_loop() threads.

        Scan DISPATCH_INBOX for .yaml files. For each file not already
        tracked in _active_dispatches, check if it has pending tasks.
        If so, start a dispatch_loop() thread.

        Implementation notes:
            - Use dispatch.load_dispatch() to check task statuses
            - Skip files where all_done() is True
            - Track thread per yaml_path in _active_dispatches
            - Clean up finished threads
        """
        raise NotImplementedError

    def _check_replans(self):
        """Check replan triggers for all active dispatches.

        For each active dispatch, call _check_replan_triggers().
        If triggered, call _apply_replan().

        Implementation notes:
            - Import from core.dispatch
            - Only check dispatches that have been running > 5 minutes
              (avoid premature replanning)
        """
        raise NotImplementedError

    def _route_messages(self):
        """Process cross-agent messages from all inboxes.

        For each department, check_inbox(). For messages that need
        routing (e.g. asset_delivery from Art → Engineering), deliver
        to the target agent's receive_message().

        Message types and routing:
            asset_request:      → Art (generate asset)
            asset_delivery:     → Engineering (integrate asset)
            build_ready:        → QA (review build)
            bug_report:         → Engineering (fix bug)
            quality_gate_result:→ Studio (report) + upstream (retry)
            wiki_insight:       → target dept (cross-pollinate knowledge)
            escalation:         → Studio Director (human attention needed)
            priority_update:    → PjM (replan may be needed)
        """
        raise NotImplementedError

    def _tick_agents(self):
        """Call loop() for each active department agent.

        This is how agents do background work: check their inbox,
        run curate(), process pending ingest tasks, etc.

        Implementation notes:
            - Instantiate agents lazily, cache in _agents dict
            - Catch exceptions per agent (one failing shouldn't stop others)
            - Log slow agents (>10s per tick)
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    import argparse
    p = argparse.ArgumentParser(description="Studio Director daemon")
    p.add_argument("--once", action="store_true", help="Single tick, then exit")
    p.add_argument("--daemonize", action="store_true", help="Run in background")
    p.add_argument("--studio-dir", type=str, default=".",
                   help="Path to game-studio-agents root")
    args = p.parse_args()

    daemon = StudioDaemon(studio_dir=args.studio_dir)

    if args.daemonize:
        # TODO: implement proper daemonization (or use systemd/launchd)
        raise NotImplementedError("Daemonize not yet implemented")

    daemon.run(once=args.once)


if __name__ == "__main__":
    main()
