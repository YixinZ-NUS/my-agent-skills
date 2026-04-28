#!/usr/bin/env python3
"""Heuristic suspect-token extractor for transcripts.

Reads a transcript (transcript.txt or segments.json from local_transcribe.py)
and prints lines that are likely to contain misrecognised acronyms / proper
nouns / domain jargon, plus a deduplicated candidate list.

The output is intentionally noisy: it gives a coding agent (or human) a short
list of timestamps to listen back to, and a candidate-token table to feed into
a glossary file for a refinement pass.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

# Tokens that look like acronyms / mixed-case codes.
# Strict ALL-CAPS acronyms (the strongest signal).
ACRONYM = re.compile(r"\b[A-Z]{2,6}\b")
# Mixed-case oddities: e.g. iOS, MacOS, KYIT, FTAG, WBHook, YPOK -- a capital
# followed by a mix where there are at least two upper-case letters.
WEIRD = re.compile(r"\b(?:[a-z]+[A-Z][A-Za-z]+|[A-Z][a-z]*[A-Z]{2,}[A-Za-z]*)\b")

# Common English words that occasionally appear ALL-CAPS or sentence-initial;
# never flag these alone.
STOP_ACRONYMS = {
    "I", "OK", "TV", "USA", "UK", "EU", "AI", "PM", "AM",
    "CEO", "CFO", "CTO", "COO", "API", "URL", "FAQ", "FYI",
    "iOS", "MacOS", "Android",
}

CJK = re.compile(r"[\u4e00-\u9fff]")


def parse_segments_json(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data


def parse_transcript_txt(path: Path) -> list[dict]:
    """Parse the human-readable transcript with `[start -> end] text` lines."""
    segs: list[dict] = []
    line_re = re.compile(r"\[\s*([0-9.]+)\s*->\s*([0-9.]+)\s*\]\s*(.*)$")
    for line in path.read_text(encoding="utf-8").splitlines():
        m = line_re.search(line)
        if not m:
            continue
        segs.append({"abs_start": float(m.group(1)), "abs_end": float(m.group(2)), "text": m.group(3)})
    return segs


def is_chinese(text: str) -> bool:
    return bool(CJK.search(text))


def collect_candidates(segments: list[dict]) -> tuple[Counter, list[dict]]:
    counter: Counter[str] = Counter()
    flagged: list[dict] = []
    for seg in segments:
        text = seg.get("text", "")
        hits: set[str] = set()
        for pat in (ACRONYM, WEIRD):
            for tok in pat.findall(text):
                if tok in STOP_ACRONYMS:
                    continue
                if tok.isdigit():
                    continue
                if len(tok) < 2:
                    continue
                hits.add(tok)
                counter[tok] += 1
        # Mixed CJK+Latin segments are common error sources (English term
        # mid-Chinese sentence often gets garbled).
        mixed = is_chinese(text) and re.search(r"[A-Za-z]{2,}", text)
        if hits or mixed:
            flagged.append({
                "start": seg.get("abs_start", seg.get("start")),
                "end": seg.get("abs_end", seg.get("end")),
                "text": text,
                "hits": sorted(hits),
                "mixed_cjk_latin": bool(mixed),
            })
    return counter, flagged


def format_hms(seconds: float | None) -> str:
    if seconds is None:
        return "??:??:??"
    seconds = int(seconds)
    return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="transcript.txt or segments.json from local_transcribe.py")
    ap.add_argument("--min-count", type=int, default=1, help="Only show candidates with >= this many occurrences.")
    ap.add_argument("--max-flags", type=int, default=80, help="Cap on flagged-line printout.")
    ap.add_argument("--json-out", default=None, help="Optional path to write the full report as JSON.")
    args = ap.parse_args()

    path = Path(args.input)
    if path.suffix == ".json":
        segs = parse_segments_json(path)
    else:
        segs = parse_transcript_txt(path)

    counter, flagged = collect_candidates(segs)

    print(f"# {len(segs)} segments scanned, {len(flagged)} flagged, {len(counter)} unique candidates\n")
    print("## Candidate tokens (token<TAB>count)")
    for tok, n in counter.most_common():
        if n < args.min_count:
            continue
        print(f"{tok}\t{n}")

    print("\n## Flagged segments (timestamp -- hits -- text)")
    for row in flagged[: args.max_flags]:
        ts = format_hms(row["start"])
        hits = ",".join(row["hits"]) or ("CJK+Latin" if row["mixed_cjk_latin"] else "")
        print(f"{ts}\t[{hits}]\t{row['text']}")

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps({"candidates": counter.most_common(), "flagged": flagged}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
