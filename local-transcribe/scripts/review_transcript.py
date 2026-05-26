#!/usr/bin/env python3
"""Prepare subagent review packets and apply conservative transcript corrections."""

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


def fmt_hms(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"


def render_transcript(segments: list[dict]) -> str:
    return "\n".join(
        f"[{float(seg['abs_start']):8.2f} -> {float(seg['abs_end']):8.2f}] {seg.get('text', '').strip()}"
        for seg in segments
    ) + "\n"


def packet_text(packet_id: int, segments: list[tuple[int, dict]], domain_context: str) -> str:
    rows = []
    for idx, seg in segments:
        rows.append(
            f"- segment_index: {idx}\n"
            f"  time: {fmt_hms(float(seg['abs_start']))} -> {fmt_hms(float(seg['abs_end']))}\n"
            f"  text: {seg.get('text', '').strip()}"
        )
    context_block = f"\nDomain context: {domain_context}\n" if domain_context else ""
    return f"""# Transcript review packet {packet_id:03d}
{context_block}
You are a transcript review subagent. Review only the packet below.

Rules:
- Correct wording issues, ASR typos, punctuation, and obvious domain-term mistakes.
- Preserve the speaker's meaning and do not summarize or rewrite style.
- Keep Simplified Chinese for Chinese text.
- Keep technical English terms in their canonical spelling.
- Only propose corrections you are confident about from local context.
- If unsure, leave the segment unchanged and add no correction.

Return a JSON array only. Each item must use this schema:
{{
  "segment_index": 12,
  "start": 123.45,
  "end": 130.00,
  "original": "exact substring or exact segment text",
  "corrected": "replacement text",
  "reason": "brief reason",
  "confidence": 0.0,
  "glossary_terms": ["optional durable terms"]
}}

Packet:
{chr(10).join(rows)}
"""


def make_packets(args: argparse.Namespace) -> None:
    segments = load_segments(args.segments)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    packet_seconds = args.packet_minutes * 60.0
    current: list[tuple[int, dict]] = []
    packet_start: float | None = None
    packet_id = 1
    manifest = []

    def flush() -> None:
        nonlocal packet_id, current, packet_start
        if not current:
            return
        path = args.out_dir / f"review-packet-{packet_id:03d}.md"
        path.write_text(packet_text(packet_id, current, args.domain_context or ""), encoding="utf-8")
        manifest.append(
            {
                "packet": packet_id,
                "path": str(path),
                "segment_start": current[0][0],
                "segment_end": current[-1][0],
                "start": current[0][1]["abs_start"],
                "end": current[-1][1]["abs_end"],
                "expected_corrections_file": str(args.out_dir / f"corrections-{packet_id:03d}.json"),
            }
        )
        packet_id += 1
        current = []
        packet_start = None

    for idx, seg in enumerate(segments):
        start = float(seg["abs_start"])
        if packet_start is None:
            packet_start = start
        if current and start - packet_start >= packet_seconds:
            flush()
            packet_start = start
        current.append((idx, seg))
    flush()

    (args.out_dir / "review-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"packets": len(manifest), "out_dir": str(args.out_dir)}, indent=2))


def load_corrections(path: Path) -> list[dict]:
    files: list[Path]
    if path.is_dir():
        files = sorted(path.glob("corrections-*.json")) + sorted(path.glob("corrections-*.jsonl"))
    else:
        files = [path]
    corrections: list[dict] = []
    for file_path in files:
        raw = file_path.read_text(encoding="utf-8").strip()
        if not raw:
            continue
        if file_path.suffix == ".jsonl":
            corrections.extend(json.loads(line) for line in raw.splitlines() if line.strip())
        else:
            data = json.loads(raw)
            if not isinstance(data, list):
                raise SystemExit(f"{file_path} must contain a JSON array")
            corrections.extend(data)
    return corrections


def find_segment(segments: list[dict], correction: dict, tolerance: float) -> tuple[int, dict]:
    if "segment_index" in correction:
        idx = int(correction["segment_index"])
        if idx < 0 or idx >= len(segments):
            raise ValueError(f"segment_index out of range: {idx}")
        return idx, segments[idx]
    start = float(correction["start"])
    end = float(correction["end"])
    candidates = [
        (idx, seg)
        for idx, seg in enumerate(segments)
        if abs(float(seg["abs_start"]) - start) <= tolerance and abs(float(seg["abs_end"]) - end) <= tolerance
    ]
    if len(candidates) != 1:
        raise ValueError(f"Expected exactly one segment for correction at {start}->{end}, found {len(candidates)}")
    return candidates[0]


def apply_corrections(args: argparse.Namespace) -> None:
    segments = load_segments(args.segments)
    corrections = load_corrections(args.corrections)
    applied = []
    skipped_low_confidence = 0

    for correction in corrections:
        confidence = float(correction.get("confidence", 0.0))
        if confidence < args.min_confidence:
            skipped_low_confidence += 1
            continue
        idx, seg = find_segment(segments, correction, args.time_tolerance)
        text = str(seg.get("text", ""))
        original = str(correction["original"])
        corrected = str(correction["corrected"])
        if original not in text:
            raise SystemExit(
                f"Correction original text was not found in segment {idx}: {original!r}. "
                "Use exact segment text/substrings so review application remains auditable."
            )
        if original == corrected:
            continue
        seg["text"] = text.replace(original, corrected, 1)
        applied.append({**correction, "segment_index": idx})

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "segments.json").write_text(json.dumps(segments, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.out_dir / "transcript.txt").write_text(render_transcript(segments), encoding="utf-8")
    (args.out_dir / "review-stats.json").write_text(
        json.dumps(
            {
                "corrections_seen": len(corrections),
                "applied": len(applied),
                "skipped_low_confidence": skipped_low_confidence,
                "min_confidence": args.min_confidence,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"applied": len(applied), "out_dir": str(args.out_dir)}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    make = sub.add_parser("make-packets")
    make.add_argument("segments", type=Path)
    make.add_argument("--out-dir", required=True, type=Path)
    make.add_argument("--packet-minutes", type=float, default=12.0)
    make.add_argument("--domain-context", default="")
    make.set_defaults(func=make_packets)

    apply = sub.add_parser("apply-corrections")
    apply.add_argument("segments", type=Path)
    apply.add_argument("--corrections", required=True, type=Path)
    apply.add_argument("--out-dir", required=True, type=Path)
    apply.add_argument("--min-confidence", type=float, default=0.7)
    apply.add_argument("--time-tolerance", type=float, default=1.0)
    apply.set_defaults(func=apply_corrections)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
