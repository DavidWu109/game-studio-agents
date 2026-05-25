"""Wiki search — find relevant pages by tag or keyword.

Usage:
    python3 -m core.search "sprite-pipeline"
    python3 -m core.search "touch-zone layout"
    python3 -m core.search "how to handle inventory display" --content

Architecture Interfaces:

Interface #3 — Agentic Search (search → evaluate → refine)
    agentic_search(): LLM-in-the-loop retrieval that evaluates whether
    results are sufficient, then refines query if not.
    Called by: agent.load_relevant_lessons() (Phase B)

    evaluate_results(): LLM judges result sufficiency for a given question.
    Called by: agentic_search() internally.

    filter_by_task(): Fast pre-filter by task name + issue keywords.
    Called by: agent.load_relevant_lessons() (Phase A, no LLM needed)
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import List, Tuple

STUDIO_DIR = Path(__file__).parent.parent
BASE_DIR = STUDIO_DIR / "base"
PROJECT_DIR = Path(os.path.expanduser("~/Projects/gopoo-studio-project"))


def _parse_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    end = text.find("---", 3)
    if end == -1:
        return {}
    fm = text[3:end]
    result = {}
    for line in fm.strip().split("\n"):
        if ":" in line:
            key, val = line.split(":", 1)
            result[key.strip()] = val.strip()
    return result


def _extract_tags(fm: dict) -> List[str]:
    raw = fm.get("tags", "[]")
    return [t.strip().strip("'\"") for t in raw.strip("[]").split(",") if t.strip()]


def search_by_tags(query_tags: List[str], search_dirs: List[Path] = None) -> List[Tuple[Path, float, List[str]]]:
    """Search wiki pages by tag overlap. Returns (path, score, matched_tags)."""
    if search_dirs is None:
        search_dirs = [BASE_DIR, PROJECT_DIR]

    results = []
    query_set = set(t.lower() for t in query_tags)

    for base in search_dirs:
        if not base.exists():
            continue
        for page in base.rglob("*/wiki/pages/*.md"):
            fm = _parse_frontmatter(page)
            page_tags = [t.lower() for t in _extract_tags(fm)]
            matched = query_set & set(page_tags)
            if matched:
                score = len(matched) / len(query_set)
                results.append((page, score, list(matched)))

    results.sort(key=lambda x: -x[1])
    return results


def search_by_content(keywords: List[str], search_dirs: List[Path] = None) -> List[Tuple[Path, int, str]]:
    """Search wiki pages by keyword in content. Returns (path, hit_count, snippet)."""
    if search_dirs is None:
        search_dirs = [BASE_DIR, PROJECT_DIR]

    results = []

    for base in search_dirs:
        if not base.exists():
            continue
        for page in base.rglob("*/wiki/pages/*.md"):
            text = page.read_text(encoding="utf-8").lower()
            hits = sum(text.count(kw.lower()) for kw in keywords)
            if hits > 0:
                for line in text.split("\n"):
                    if any(kw.lower() in line for kw in keywords):
                        snippet = line.strip()[:100]
                        break
                else:
                    snippet = ""
                results.append((page, hits, snippet))

    results.sort(key=lambda x: -x[1])
    return results


# ---------------------------------------------------------------------------
# Interface #3: Agentic Search (search → evaluate → refine)
# ---------------------------------------------------------------------------


def filter_by_task(task_name: str, issue_keywords: List[str] = None,
                   search_dirs: List[Path] = None, max_results: int = 20
                   ) -> List[Tuple[Path, float, str]]:
    """Phase A: Fast pre-filter by task name and issue keywords. No LLM needed.

    Returns (path, relevance_score, snippet) sorted by relevance.

    Relevance scoring:
    - task_name exact match in content: +1.0
    - task_name partial match (e.g. "poop_emotions" matches "poop"): +0.5
    - Each issue keyword match: +0.3
    - Normalized to 0-1 range

    Called by: agent.load_relevant_lessons() Phase A implementation.

    Example:
        results = filter_by_task("blank_button_template",
                                 issue_keywords=["outline", "glossy", "flat"])
        for path, score, snippet in results:
            print(f"{score:.2f} {path.name}: {snippet}")
    """
    if search_dirs is None:
        search_dirs = [BASE_DIR, PROJECT_DIR]
    if issue_keywords is None:
        issue_keywords = []

    scored: dict[Path, tuple[float, str]] = {}

    task_results = search_by_content([task_name], search_dirs)
    for path, hits, snippet in task_results:
        scored[path] = (hits * 1.0, snippet)

    if issue_keywords:
        kw_results = search_by_content(issue_keywords, search_dirs)
        for path, hits, snippet in kw_results:
            prev_score, prev_snippet = scored.get(path, (0.0, ""))
            scored[path] = (prev_score + hits * 0.3, prev_snippet or snippet)

    tag_words = [task_name] + issue_keywords
    tag_results = search_by_tags(tag_words, search_dirs)
    for path, tag_score, _ in tag_results:
        prev_score, prev_snippet = scored.get(path, (0.0, ""))
        scored[path] = (prev_score + tag_score * 0.5, prev_snippet)

    ranked = [(p, s, snip) for p, (s, snip) in scored.items()]
    ranked.sort(key=lambda x: -x[1])

    if ranked:
        max_score = ranked[0][1]
        if max_score > 0:
            ranked = [(p, s / max_score, snip) for p, s, snip in ranked]

    return ranked[:max_results]


def evaluate_results(question: str, results: List[str], context: str = ""
                     ) -> dict:
    """LLM evaluates whether search results sufficiently answer the question.

    Returns:
        {
            "sufficient": bool,
            "coverage": float,       # 0-1, how well results cover the question
            "missing_aspects": [...], # what's not covered
            "refined_query": str,     # suggested query to fill gaps (if not sufficient)
        }

    Called by: agentic_search() internally.

    Implementation notes:
        - Use Claude via subprocess (claude -p) or API
        - Prompt: "Given these wiki results, does the information sufficiently
          address: {question}? What aspects are missing?"
        - Parse structured JSON response
        - Budget: ~500 input tokens per call (keep results concise)
    """
    # TODO: implement — requires LLM call
    raise NotImplementedError


def agentic_search(question: str, context: str = "",
                   search_dirs: List[Path] = None,
                   max_rounds: int = 3) -> List[str]:
    """Agentic search: search → evaluate → refine → search again.

    Implements Anthropic's recommended agentic search pattern:
    1. Initial search (tag + content)
    2. LLM evaluates: "are these results sufficient?"
    3. If not: LLM suggests refined query → search again
    4. Repeat up to max_rounds
    5. Return consolidated results

    Args:
        question: natural language question (e.g. "how to get flat matte
                  cartoon button without glossy highlights")
        context: additional context (e.g. current task, recent failures)
        search_dirs: wiki directories to search
        max_rounds: max search-evaluate-refine iterations

    Returns:
        List of relevant wiki page contents, deduplicated and ranked.

    Call site: agent.load_relevant_lessons() Phase B:
        from core.search import agentic_search
        lessons = agentic_search(
            question=f"lessons for {task['task_id']} about {', '.join(issues)}",
            context=f"round {round_n}, score {score}",
        )

    Cost estimate: ~$0.01 per search (1 LLM call per round, 3 rounds max)
    """
    # TODO: implement
    # Round 1: extract keywords from question → search_by_tags + search_by_content
    # Round 2+: evaluate_results() → if not sufficient, use refined_query → search again
    # Final: deduplicate, return page contents
    raise NotImplementedError


def main():
    import argparse
    p = argparse.ArgumentParser(description="Search wiki by tags or content")
    p.add_argument("query", nargs="+", help="Tags or keywords to search")
    p.add_argument("--content", action="store_true", help="Search in page content, not just tags")
    args = p.parse_args()

    if args.content:
        results = search_by_content(args.query)
        for path, hits, snippet in results[:10]:
            rel = path.relative_to(STUDIO_DIR) if str(path).startswith(str(STUDIO_DIR)) else path
            print(f"  {hits:3d} hits | {rel}")
            if snippet:
                print(f"         {snippet}")
    else:
        results = search_by_tags(args.query)
        for path, score, matched in results[:10]:
            rel = path.relative_to(STUDIO_DIR) if str(path).startswith(str(STUDIO_DIR)) else path
            print(f"  {score:.0%} match | {rel} | tags: {matched}")


if __name__ == "__main__":
    main()
