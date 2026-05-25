"""Wiki search — find relevant pages by tag or keyword.

Usage:
    python3 -m core.search "sprite-pipeline"
    python3 -m core.search "touch-zone layout"
    python3 -m core.search "how to handle inventory display" --content
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
