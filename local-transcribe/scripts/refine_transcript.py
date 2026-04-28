#!/usr/bin/env python3
"""Merge a refinement transcription into a baseline transcript.

Typical workflow:

1. Run local_transcribe.py with `--model tiny|small` to get a fast baseline
   (writes baseline/segments.json).
2. Identify suspect chunks with extract_suspects.py and build a glossary file.
3. Re-run local_transcribe.py with `--model small|medium`,
   `--glossary-file ...`, optionally `--start`/`--duration`, into a separate
   `refined/` directory.
4. Run this script:

       refine_transcript.py \
         --baseline output/job/segments.json \
         --refined  output/job-refined/segments.json \
         --out-dir  output/job-merged

Behaviour: refined segments fully replace any baseline segment whose
[abs_start, abs_end] window overlaps the refined window. Segments outside the
refined coverage are kept verbatim from the baseline. Output is sorted by
abs_start and emitted as both `transcript.txt` (human-readable) and
`segments.json` (programmatic).

The script is idempotent and can be chained: feed its output back in as the
new `--baseline` for a third pass with a tighter slice.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_segments(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit(f"{path} does not look like a segments.json (expected a JSON array)")
    return data


def coverage(segments: list[dict]) -> tuple[float, float]:
    if not segments:
        return (0.0, 0.0)
    return (
        min(float(s["abs_start"]) for s in segments),
        max(float(s["abs_end"]) for s in segments),
    )


def merge(baseline: list[dict], refined: list[dict], pad: float) -> tuple[list[dict], dict]:
    if not refined:
        return list(baseline), {"replaced": 0, "kept": len(baseline), "added": 0}

    rstart, rend = coverage(refined)
    rstart -= pad
    rend += pad

    kept: list[dict] = []
    replaced = 0
    for seg in baseline:
        s = float(seg["abs_start"])
        e = float(seg["abs_end"])
        if e >= rstart and s <= rend:
            replaced += 1
            continue
        kept.append(seg)
    merged = kept + refined
    merged.sort(key=lambda r: float(r["abs_start"]))

    stats = {
        "refined_window_start": rstart,
        "refined_window_end": rend,
        "baseline_total": len(baseline),
        "refined_total": len(refined),
        "replaced": replaced,
        "kept": len(kept),
        "added": len(refined),
        "merged_total": len(merged),
    }
    return merged, stats


def fmt_hms(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"


def render_text(segments: list[dict]) -> str:
    lines = []
    for seg in segments:
        start = float(seg["abs_start"])
        end = float(seg["abs_end"])
        text = seg.get("text", "").strip()
        lines.append(f"[{start:8.2f} -> {end:8.2f}] {text}")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True, help="segments.json from the baseline pass")
    ap.add_argument("--refined", required=True, help="segments.json from the refinement pass")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument(
        "--pad",
        type=float,
        default=1.0,
        help="Seconds of padding added to the refined window when deciding which baseline "
             "segments to drop. Helps when chunk boundaries don't align exactly.",
    )
    args = ap.parse_args()

    baseline = load_segments(Path(args.baseline).expanduser().resolve())
    refined = load_segments(Path(args.refined).expanduser().resolve())

    merged, stats = merge(baseline, refined, pad=args.pad)

    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "segments.json").write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "transcript.txt").write_text(render_text(merged), encoding="utf-8")
    (out_dir / "merge-stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")

    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
