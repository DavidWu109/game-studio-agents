"""StudioAgent — base class for all Game Studio agents.

Two-layer knowledge architecture:
- base/<dept>/     : universal knowledge (carries across projects)
- projects/<proj>/<dept>/ : project-specific knowledge

Each department agent inherits from this and implements its own
Generator/Executor/Evaluator/Synthesis for the AutoResearch loop.

Architecture Interfaces (not yet implemented, stubs below):

1. QA Feedback Loop (ReAct at dispatch level)
   - dispatch.py handles retry; agent exposes on_qa_feedback() hook
   - See: dispatch.py → QA_GATE_THRESHOLD, _handle_qa_feedback()

2. Dynamic Replan (Plan-and-Execute)
   - PjM agent exposes replan() method
   - dispatch.py calls it when replan_triggers fire
   - See: dispatch.py → REPLAN_TRIGGERS, _check_replan_triggers()

3. Agentic Search (search → evaluate → refine)
   - search.py exposes agentic_search() with LLM-in-the-loop
   - generator reads via load_relevant_lessons() instead of full file scan
   - See: search.py → agentic_search(), evaluate_results()

4. Daemon + Message Bus (Hierarchical coordination)
   - StudioDaemon in daemon.py watches dispatches + inbox
   - agent.loop() becomes the per-agent autonomous tick
   - See: daemon.py (to be created)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Message:
    from_agent: str
    to_agent: str
    type: str
    payload: dict
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class StudioAgent:
    """Base protocol for all Game Studio agents.

    Two-layer knowledge:
    - base:    universal lessons (true for any game)
    - project: game-specific knowledge (style, rules, architecture)

    Each layer has three stores:
    - raw/   : immutable source material (never modified)
    - wiki/  : declarative knowledge (what the agent knows)
    - skills/: procedural memory (what the agent knows how to do)

    Six operations:
    1. Ingest  — new source → wiki + skills
    2. Query   — answer from wiki, file good answers back
    3. Iterate — AutoResearch feedback loop
    4. Lint    — health-check wiki + skills
    5. Learn   — post-turn background review
    6. Curate  — periodic skill maintenance
    """

    def __init__(self, department: str, project: str = "", studio_dir: str = "."):
        self.department = department
        self.project = project
        self.studio_dir = Path(studio_dir)

        # Base layer (universal knowledge)
        self.base_dir = self.studio_dir / "base" / department
        self.base_wiki = self.base_dir / "wiki"
        self.base_skills = self.base_dir / "skills"

        # Project layer (game-specific knowledge)
        if project:
            self.project_dir = self.studio_dir / "projects" / project / department
            self.project_wiki = self.project_dir / "wiki"
            self.project_skills = self.project_dir / "skills"
            self.project_raw = self.project_dir / "raw"
        else:
            self.project_dir = None
            self.project_wiki = None
            self.project_skills = None
            self.project_raw = None
        self._iteration_history: List[float] = []

    # --- Knowledge Operations ---

    def ingest(self, source_path: str):
        """New source → read → extract → integrate into wiki + skills."""
        raise NotImplementedError

    def query(self, question: str) -> str:
        """Answer from wiki. File good answers back as pages."""
        raise NotImplementedError

    def lint(self) -> dict:
        """Health-check wiki and skills. Return report."""
        raise NotImplementedError

    # --- AutoResearch Loop ---

    def iterate(self, task: dict) -> Optional[Any]:
        """Closed feedback loop: generate → execute → evaluate → synthesize.

        Returns the output if passed threshold, None if ceiling hit.
        """
        max_iter = task.get("max_iterations", 6)
        threshold = task.get("pass_threshold", 8.0)
        lessons = self.load_lessons()
        self._iteration_history.clear()

        input_data = self.generate(task, lessons=lessons)

        for round_n in range(max_iter):
            logger.info("[%s] round %d/%d", self.department, round_n + 1, max_iter)

            output = self.execute(input_data, task)
            evaluation = self.evaluate(output, task.get("checklist", []))
            score = evaluation.get("score", 0)
            self._iteration_history.append(score)

            self.synthesize(evaluation)

            if score >= threshold:
                logger.info("[%s] passed at round %d (score=%.1f)", self.department, round_n + 1, score)
                self.log_action("iterate", f"Task {task.get('task_id', '?')} passed at round {round_n + 1}, score={score}")
                return output

            if self.is_plateauing(window=3):
                logger.warning("[%s] plateau detected at round %d", self.department, round_n + 1)
                self.escalate(f"Score plateau at {score:.1f} for task {task.get('task_id', '?')}")
                return None

            lessons = self.load_lessons()
            input_data = self.generate(task, evaluation=evaluation, lessons=lessons)

        logger.warning("[%s] max iterations reached", self.department)
        return None

    # --- Subclass hooks (each agent implements these) ---

    def generate(self, task: dict, evaluation: Optional[dict] = None, lessons: Optional[list] = None) -> Any:
        raise NotImplementedError

    def execute(self, input_data: Any, task: dict) -> Any:
        raise NotImplementedError

    def evaluate(self, output: Any, checklist: list) -> dict:
        raise NotImplementedError

    def synthesize(self, evaluation: dict):
        raise NotImplementedError

    def load_lessons(self) -> list:
        """Load relevant lessons from BOTH base + project wiki/skills."""
        lessons = []
        for wiki_dir in [self.base_wiki, self.project_wiki]:
            if wiki_dir is None:
                continue
            pages_dir = wiki_dir / "pages"
            if pages_dir.exists():
                for page in pages_dir.glob("*.md"):
                    if any(kw in page.name for kw in ("lesson", "gotcha", "pitfall", "prior", "pattern")):
                        lessons.append(page.read_text(encoding="utf-8"))
        return lessons

    def is_plateauing(self, window: int = 3) -> bool:
        if len(self._iteration_history) < window:
            return False
        recent = self._iteration_history[-window:]
        return max(recent) - min(recent) <= 0.5

    def escalate(self, reason: str):
        """Escalate to Studio Director when ceiling is hit."""
        logger.warning("[%s] ESCALATION: %s", self.department, reason)
        self.send_message("studio", "escalation", {"reason": reason})

    def classify_lesson(self, lesson: str) -> str:
        """Classify whether a lesson belongs in base or project layer.

        Returns 'base' or 'project'. Override for LLM-based classification.
        Default heuristic: if the lesson mentions the project name, it's project-specific.
        """
        if self.project and self.project.lower() in lesson.lower():
            return "project"
        return "base"

    def write_to_wiki(self, page_name: str, content: str, layer: str = "auto"):
        """Write a wiki page to the appropriate layer.

        Args:
            layer: 'base', 'project', or 'auto' (classify automatically)
        """
        if layer == "auto":
            layer = self.classify_lesson(content)

        if layer == "project" and self.project_wiki:
            target = self.project_wiki / "pages" / page_name
        else:
            target = self.base_wiki / "pages" / page_name

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        logger.info("[%s] wrote %s → %s", self.department, page_name, layer)

    # --- Learning Loop ---

    def background_review(self, conversation_messages: list):
        """Post-turn review: update wiki and skills based on conversation."""
        raise NotImplementedError

    def curate(self):
        """Periodic skill maintenance: track usage, archive stale skills."""
        raise NotImplementedError

    # --- Cross-Agent Communication ---

    def receive_message(self, message: Message):
        """Ingest message from another agent into wiki."""
        self.log_action("receive", f"{message.type} from {message.from_agent}")

    def send_message(self, to: str, msg_type: str, payload: dict):
        """Send typed message to another agent via the message bus."""
        msg = Message(
            from_agent=self.department,
            to_agent=to,
            type=msg_type,
            payload=payload,
        )
        inbox_dir = self.studio_dir / "base" / to / "inbox"
        inbox_dir.mkdir(parents=True, exist_ok=True)
        msg_file = inbox_dir / f"{msg.timestamp}_{self.department}_{msg_type}.json"
        msg_file.write_text(json.dumps(vars(msg), ensure_ascii=False, indent=2), encoding="utf-8")

    def check_inbox(self) -> List[Message]:
        """Read and process pending messages from other agents."""
        inbox_dir = self.base_dir / "inbox"
        if not inbox_dir.exists():
            return []
        messages = []
        for msg_file in sorted(inbox_dir.glob("*.json")):
            try:
                data = json.loads(msg_file.read_text(encoding="utf-8"))
                messages.append(Message(**data))
                msg_file.unlink()
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning("Bad message file %s: %s", msg_file, e)
        return messages

    # --- Wiki Helpers ---

    def log_action(self, action: str, subject: str, layer: str = "project"):
        """Append to wiki log.md in the specified layer."""
        if layer == "project" and self.project_wiki:
            log_path = self.project_wiki / "log.md"
        else:
            log_path = self.base_wiki / "log.md"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        entry = f"\n## [{date}] {action} | {subject}\n"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(entry)

    def read_all_indexes(self) -> str:
        """Read wiki indexes from both layers for navigation."""
        parts = []
        base_index = self.base_wiki / "index.md"
        if base_index.exists():
            parts.append(f"# Base Knowledge ({self.department})\n\n")
            parts.append(base_index.read_text(encoding="utf-8"))
        if self.project_wiki:
            proj_index = self.project_wiki / "index.md"
            if proj_index.exists():
                parts.append(f"\n\n# Project Knowledge ({self.project}/{self.department})\n\n")
                parts.append(proj_index.read_text(encoding="utf-8"))
        return "\n".join(parts)

    def read_schema(self) -> str:
        """Read agent schema from both layers (base + project overlay)."""
        parts = []
        base_schema = self.base_dir / "AGENTS.md"
        if base_schema.exists():
            parts.append(base_schema.read_text(encoding="utf-8"))
        if self.project_dir:
            proj_schema = self.project_dir / "AGENTS.md"
            if proj_schema.exists():
                parts.append("\n\n---\n# Project Overlay\n\n")
                parts.append(proj_schema.read_text(encoding="utf-8"))
        return "\n".join(parts)

    # --- QA Feedback Hook (Interface #1: ReAct at dispatch level) ---
    # dispatch.py calls this when QA scores below threshold for upstream task.
    # Agent receives QA issues and returns revised input for retry.

    def on_qa_feedback(self, original_task: dict, qa_result: dict) -> Optional[dict]:
        """Receive QA feedback and return a revised task, or None to escalate.

        Called by dispatch when a downstream QA task scores below QA_GATE_THRESHOLD
        and this agent's task is the upstream that needs fixing.

        Args:
            original_task: the task dict that produced the failing output
            qa_result: {"score": float, "issues": [...], "sections": {...}}

        Returns:
            Revised task dict with updated 'input' field incorporating QA feedback,
            or None if the agent cannot self-correct (triggers escalation to human).

        Implementation notes:
            - Append QA issues to task input as structured feedback
            - Load relevant wiki lessons for the failure mode
            - Increment retry_count on the task
            - MAX_QA_RETRIES = 2 (defined in dispatch.py)
        """
        raise NotImplementedError

    # --- Replan Hook (Interface #2: Plan-and-Execute) ---
    # Only PjM agent implements this. Called by dispatch when replan triggers fire.

    def replan(self, dispatch_data: dict, trigger_reason: str) -> Optional[dict]:
        """Dynamically revise the task DAG in response to execution state.

        Only PjM agent should implement this. Other agents raise NotImplementedError.

        Args:
            dispatch_data: full YAML dispatch dict with current task statuses
            trigger_reason: why replan was triggered (e.g. "task X blocked > 30min")

        Returns:
            Revised dispatch_data with updated/added/removed planned tasks,
            or None if no changes needed.

        Implementation notes:
            - Read wiki lessons to understand WHY tasks are blocked
            - May skip blocked tasks, split large tasks, or add new tasks
            - Must preserve completed task results
            - Only modifies tasks with status 'planned' or 'blocked'
            - Should call self.load_lessons() for context
        """
        raise NotImplementedError

    # --- Relevant Lesson Loading (Interface #3: Agentic Search) ---
    # Replaces load_lessons() with filtered, relevance-ranked retrieval.

    def load_relevant_lessons(self, task: dict, current_issues: Optional[list] = None) -> list:
        """Load wiki lessons relevant to the current task and failure mode.

        Upgrade path for load_lessons() — instead of loading all pages with
        keyword-matching filenames, this filters by task_id, variant, and
        issue keywords for higher precision as the wiki grows.

        Args:
            task: current task dict (has task_id, variant, checklist, etc.)
            current_issues: list of issue strings from latest evaluation

        Returns:
            List of relevant lesson texts, ranked by relevance.

        Implementation notes (Phase A — keyword filtering):
            - Filter by task name match (exact)
            - Filter by issue keyword overlap (fuzzy)
            - Deduplicate across base + project layers
            - Cap at 20 most relevant lessons to fit context window

        Implementation notes (Phase B — agentic search):
            - Use search.agentic_search() with LLM-in-the-loop
            - LLM evaluates: "are these lessons sufficient for this task?"
            - If not, LLM generates refined query → search again
            - See: core/search.py → agentic_search()
        """
        return self.load_lessons()

    # --- Main Loop ---

    def loop(self):
        """Agent's autonomous loop. Override for department-specific logic.

        When daemon.py is implemented, this becomes the per-agent tick called
        on a schedule (default 30s). The daemon calls agent.loop() for each
        active department.

        Implementation notes:
            - Check inbox for cross-agent messages
            - Check for pending tasks assigned to this department
            - Execute ready tasks
            - Run background_review if conversation context available
        """
        messages = self.check_inbox()
        for msg in messages:
            self.receive_message(msg)
