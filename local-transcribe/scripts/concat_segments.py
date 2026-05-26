#!/usr/bin/env python3
"""Concatenate segments from split recordings into one continuous transcript."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_segments(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit(f"{path} must contain a segments.json array")
    return data


def load_manifest(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def fmt_hms(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"


def render_text(segments: list[dict]) -> str:
    lines = []
    current_source = None
    for seg in segments:
        source = seg.get("source")
        if source != current_source:
            current_source = source
            lines.append(f"\n## {source}\n")
        lines.append(f"[{float(seg['abs_start']):8.2f} -> {float(seg['abs_end']):8.2f}] {seg.get('text', '').strip()}")
    return "\n".join(lines).lstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path, help="segments.json files or output directories containing segments.json")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument(
        "--offset-mode",
        choices=("duration", "last-segment"),
        default="duration",
        help="Use manifest duration when available, otherwise last segment end.",
    )
    args = parser.parse_args()

    offset = 0.0
    combined: list[dict] = []
    sources = []
    for input_path in args.inputs:
        path = input_path.expanduser().resolve()
        seg_path = path / "segments.json" if path.is_dir() else path
        base_dir = seg_path.parent
        manifest = load_manifest(base_dir / "manifest.json")
        segments = load_segments(seg_path)
        source = Path(manifest.get("input", base_dir.name)).name
        for seg in segments:
            adjusted = dict(seg)
            adjusted["source"] = source
            adjusted["source_abs_start"] = adjusted["abs_start"]
            adjusted["source_abs_end"] = adjusted["abs_end"]
            adjusted["abs_start"] = offset + float(seg["abs_start"])
            adjusted["abs_end"] = offset + float(seg["abs_end"])
            combined.append(adjusted)
        if args.offset_mode == "duration" and manifest.get("duration") is not None:
            source_duration = float(manifest["duration"])
        elif segments:
            source_duration = max(float(seg["abs_end"]) for seg in segments)
        else:
            source_duration = 0.0
        sources.append({"source": source, "offset": offset, "duration": source_duration})
        offset += source_duration

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "segments.json").write_text(json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.out_dir / "transcript.txt").write_text(render_text(combined), encoding="utf-8")
    (args.out_dir / "manifest.json").write_text(
        json.dumps({"sources": sources, "total_duration": offset}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"segments": len(combined), "duration": fmt_hms(offset), "out_dir": str(args.out_dir)}, indent=2))


if __name__ == "__main__":
    main()
