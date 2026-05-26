#!/usr/bin/env python3
"""Render transcript Markdown with first-mention web context links."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def load_segments(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit(f"{path} must be a segments.json array")
    return data


def load_references(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit(f"{path} must contain a JSON array")
    for ref in data:
        if "term" not in ref or "url" not in ref:
            raise SystemExit("Each reference must include at least 'term' and 'url'")
    return data


def fmt_hms(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"


def mention_pattern(term: str) -> re.Pattern:
    escaped = re.escape(term)
    if re.fullmatch(r"[A-Za-z0-9 _\-/]+", term):
        return re.compile(rf"(?<![A-Za-z0-9])({escaped})(?![A-Za-z0-9])", re.I)
    return re.compile(f"({escaped})")


def find_first_mentions(segments: list[dict], references: list[dict]) -> dict[str, dict]:
    first_mentions: dict[str, dict] = {}
    for ref in references:
        aliases = [ref["term"], *ref.get("aliases", [])]
        for seg in segments:
            text = str(seg.get("text", ""))
            matched_alias = None
            for alias in aliases:
                if mention_pattern(alias).search(text):
                    matched_alias = alias
                    break
            if matched_alias:
                first_mentions[ref["term"]] = {
                    "term": ref["term"],
                    "matched_alias": matched_alias,
                    "start": seg["abs_start"],
                    "end": seg["abs_end"],
                    "text": text,
                    "url": ref["url"],
                    "title": ref.get("title", ref["term"]),
                    "note": ref.get("note", ""),
                }
                break
    return first_mentions


def link_first_mentions(text: str, references: list[dict], linked_terms: set[str]) -> str:
    rendered = text
    for ref in references:
        term = ref["term"]
        if term in linked_terms:
            continue
        aliases = [term, *ref.get("aliases", [])]
        for alias in aliases:
            pattern = mention_pattern(alias)
            if pattern.search(rendered):
                rendered = pattern.sub(lambda m: f"[{m.group(1)}]({ref['url']})", rendered, count=1)
                linked_terms.add(term)
                break
    return rendered


def render_markdown(segments: list[dict], references: list[dict], title: str) -> str:
    linked_terms: set[str] = set()
    lines = [f"# {title}", ""]
    for seg in segments:
        text = str(seg.get("text", "")).strip()
        if not text:
            continue
        linked = link_first_mentions(text, references, linked_terms)
        lines.append(f"[{fmt_hms(float(seg['abs_start']))}] {linked}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_context_index(first_mentions: dict[str, dict], references: list[dict]) -> str:
    by_term = {ref["term"]: ref for ref in references}
    lines = ["# Context links", ""]
    for term in by_term:
        mention = first_mentions.get(term)
        ref = by_term[term]
        if mention:
            lines.append(f"- [{term}]({ref['url']}) — first mention {fmt_hms(float(mention['start']))}. {ref.get('note', '')}".rstrip())
        else:
            lines.append(f"- [{term}]({ref['url']}) — not found in transcript. {ref.get('note', '')}".rstrip())
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("segments", type=Path)
    parser.add_argument("--references", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--title", default="Annotated transcript")
    args = parser.parse_args()

    segments = load_segments(args.segments)
    references = load_references(args.references)
    first_mentions = find_first_mentions(segments, references)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "annotated_transcript.md").write_text(render_markdown(segments, references, args.title), encoding="utf-8")
    (args.out_dir / "context_links.md").write_text(render_context_index(first_mentions, references), encoding="utf-8")
    (args.out_dir / "first_mentions.json").write_text(json.dumps(first_mentions, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"references": len(references), "matched": len(first_mentions), "out_dir": str(args.out_dir)}, indent=2))


if __name__ == "__main__":
    main()
