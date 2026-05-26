#!/usr/bin/env python3
"""A/B test ffmpeg audio filters before using denoising on a full transcript.

The script transcribes identical short windows with raw audio and one or more
candidate filters, scores the resulting text with language-aware heuristics,
and recommends denoising only when it beats raw audio by a configured margin.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from statistics import mean
from typing import Optional

import av
import imageio_ffmpeg
from av.error import FFmpegError


PRESET_FILTERS = {
    "raw": None,
    "mild": "highpass=f=80,lowpass=f=8000",
    "denoise": "highpass=f=80,lowpass=f=8000,afftdn=nr=10",
    "strong": "highpass=f=120,lowpass=f=7000,afftdn=nr=18",
}

HALLUCINATION_PATTERNS = [
    re.compile(r"\bthanks?\s+for\s+watching\b", re.I),
    re.compile(r"\bdon'?t\s+forget\s+to\s+subscribe\b", re.I),
    re.compile(r"\bsubtitles?\s+by\b", re.I),
    re.compile(r"\bi'?m\s+gonna\s+share\s+with\s+you\b", re.I),
]
CJK = re.compile(r"[\u4e00-\u9fff]")
LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{1,}")


def media_duration(path: Path) -> float:
    try:
        container = av.open(str(path))
        try:
            if container.duration is None:
                raise RuntimeError(f"Could not determine media duration for {path}")
            return float(container.duration / 1_000_000)
        finally:
            container.close()
    except FFmpegError:
        result = subprocess.run(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr)
        if not match:
            raise RuntimeError(
                f"Could not determine media duration for {path}. ffmpeg reported:\n{result.stderr.strip()}"
            )
        hours, minutes, seconds = match.groups()
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def parse_hms(value: str) -> float:
    if ":" not in value:
        return float(value)
    parts = [float(p) for p in value.split(":")]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    raise argparse.ArgumentTypeError(f"Invalid time value: {value}")


def sec_to_hms(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"


def parse_window(value: str) -> tuple[float, float]:
    if "+" in value:
        start, duration = value.split("+", 1)
    elif ":" in value and "," in value:
        start, duration = value.split(",", 1)
    else:
        raise argparse.ArgumentTypeError("Window must be START+DURATION, e.g. 00:10:00+90")
    return parse_hms(start), parse_hms(duration)


def default_windows(total_duration: float, sample_seconds: float, count: int) -> list[tuple[float, float]]:
    if total_duration <= sample_seconds:
        return [(0.0, total_duration)]
    anchors = [0.12, 0.45, 0.75, 0.9]
    windows: list[tuple[float, float]] = []
    for ratio in anchors[:count]:
        start = min(max(0.0, total_duration * ratio), total_duration - sample_seconds)
        windows.append((start, sample_seconds))
    return windows


def load_terms(path: Optional[Path]) -> list[str]:
    if not path:
        return []
    terms: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            terms.append(line)
    return terms


def redact_allowed_terms(text: str, terms: list[str]) -> str:
    out = text
    for term in sorted(terms, key=len, reverse=True):
        if not term or not re.search(r"[A-Za-z]", term):
            continue
        out = re.sub(re.escape(term), " ", out, flags=re.I)
    return out


def score_text(text: str, *, language: Optional[str], duration: float, glossary_terms: list[str]) -> dict:
    compact = re.sub(r"\s+", "", text)
    cjk_count = len(CJK.findall(text))
    latin_text = redact_allowed_terms(text, glossary_terms)
    latin_count = sum(len(m.group(0)) for m in LATIN_WORD.finditer(latin_text))
    char_count = len(compact)
    repeated_char_runs = len(re.findall(r"(.)\1{4,}", compact))
    repeated_phrase_runs = len(re.findall(r"(.{2,12})\1{3,}", compact))
    hallucinations = sum(len(p.findall(text)) for p in HALLUCINATION_PATTERNS)
    chars_per_minute = char_count / max(duration / 60.0, 0.01)

    if language and language.lower().startswith("zh"):
        cjk_ratio = cjk_count / max(char_count, 1)
        latin_ratio = latin_count / max(char_count, 1)
        score = 1.0 + (0.6 * cjk_ratio) - (0.45 * latin_ratio)
        if chars_per_minute < 45:
            score -= (45 - chars_per_minute) / 100
    else:
        score = 1.0
        cjk_ratio = cjk_count / max(char_count, 1)
        latin_ratio = latin_count / max(char_count, 1)

    score -= hallucinations * 0.8
    score -= repeated_char_runs * 0.15
    score -= repeated_phrase_runs * 0.25

    return {
        "score": round(score, 4),
        "chars": char_count,
        "chars_per_minute": round(chars_per_minute, 2),
        "cjk_ratio": round(cjk_ratio, 4),
        "latin_ratio_after_glossary": round(latin_ratio, 4),
        "hallucinations": hallucinations,
        "repeated_char_runs": repeated_char_runs,
        "repeated_phrase_runs": repeated_phrase_runs,
    }


def read_transcript_text(run_dir: Path) -> str:
    segments = json.loads((run_dir / "segments.json").read_text(encoding="utf-8"))
    return "\n".join(str(seg.get("text", "")).strip() for seg in segments)


def transcribe_window(args, filter_name: str, audio_filter: Optional[str], window: tuple[float, float], out_dir: Path) -> dict:
    start, duration = window
    run_dir = out_dir / filter_name / f"{int(start):06d}-{int(duration):04d}"
    cmd = [
        sys.executable,
        str(Path(__file__).with_name("local_transcribe.py")),
        str(args.input),
        "--out-dir",
        str(run_dir),
        "--model",
        args.model,
        "--language",
        args.language,
        "--beam-size",
        str(args.beam_size),
        "--chunk-minutes",
        str(max(duration / 60.0, 0.5)),
        "--start",
        sec_to_hms(start),
        "--duration",
        sec_to_hms(duration),
        "--chinese-script",
        args.chinese_script,
        "--vad-filter",
        args.vad_filter,
        "--condition-on-previous-text",
        args.condition_on_previous_text,
    ]
    if args.glossary_file:
        cmd += ["--glossary-file", str(args.glossary_file)]
    if args.initial_prompt:
        cmd += ["--initial-prompt", args.initial_prompt]
    cmd += ["--max-initial-prompt-chars", str(args.max_initial_prompt_chars)]
    if args.hotwords:
        cmd += ["--hotwords", args.hotwords]
    if audio_filter:
        cmd += ["--audio-filter", audio_filter]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    if result.returncode != 0:
        return {
            "filter": filter_name,
            "audio_filter": audio_filter,
            "window_start": start,
            "window_duration": duration,
            "out_dir": str(run_dir),
            "failed": True,
            "error": result.stderr.strip()[-4000:],
            "text_preview": "",
            "score": -999.0,
            "chars": 0,
            "chars_per_minute": 0.0,
            "cjk_ratio": 0.0,
            "latin_ratio_after_glossary": 0.0,
            "hallucinations": 0,
            "repeated_char_runs": 0,
            "repeated_phrase_runs": 0,
        }
    text = read_transcript_text(run_dir)
    metrics = score_text(text, language=args.language, duration=duration, glossary_terms=args.glossary_terms)
    return {
        "filter": filter_name,
        "audio_filter": audio_filter,
        "window_start": start,
        "window_duration": duration,
        "out_dir": str(run_dir),
        "failed": False,
        "text_preview": text[:500],
        **metrics,
    }


def parse_filter_arg(value: str) -> tuple[str, Optional[str]]:
    if value in PRESET_FILTERS:
        return value, PRESET_FILTERS[value]
    if "=" not in value:
        raise argparse.ArgumentTypeError(
            f"Unknown preset '{value}'. Use one of {', '.join(PRESET_FILTERS)} or NAME=ffmpeg_filter."
        )
    name, expr = value.split("=", 1)
    if not name:
        raise argparse.ArgumentTypeError("Filter name cannot be empty")
    return name, expr or None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--model", default="small")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--chinese-script", choices=("auto", "none", "simplified", "traditional"), default="auto")
    parser.add_argument("--beam-size", type=int, default=3)
    parser.add_argument("--vad-filter", choices=("on", "off"), default="on")
    parser.add_argument("--condition-on-previous-text", choices=("on", "off"), default="off")
    parser.add_argument("--glossary-file", type=Path)
    parser.add_argument("--initial-prompt")
    parser.add_argument("--max-initial-prompt-chars", type=int, default=500)
    parser.add_argument("--hotwords")
    parser.add_argument("--window", action="append", type=parse_window, help="START+DURATION; can be repeated")
    parser.add_argument("--sample-seconds", type=float, default=75.0)
    parser.add_argument("--sample-count", type=int, default=3)
    parser.add_argument("--filter", action="append", type=parse_filter_arg, default=None)
    parser.add_argument("--min-improvement", type=float, default=0.05)
    args = parser.parse_args()

    args.input = args.input.expanduser().resolve()
    args.out_dir = args.out_dir.expanduser().resolve()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.glossary_file = args.glossary_file.expanduser().resolve() if args.glossary_file else None
    args.glossary_terms = load_terms(args.glossary_file)

    filters = args.filter or [("raw", None), ("mild", PRESET_FILTERS["mild"]), ("denoise", PRESET_FILTERS["denoise"])]
    if not any(name == "raw" for name, _ in filters):
        filters.insert(0, ("raw", None))

    windows = args.window or default_windows(media_duration(args.input), args.sample_seconds, args.sample_count)
    runs: list[dict] = []
    for filter_name, audio_filter in filters:
        for window in windows:
            runs.append(transcribe_window(args, filter_name, audio_filter, window, args.out_dir))

    by_filter: dict[str, list[dict]] = {}
    for run in runs:
        by_filter.setdefault(run["filter"], []).append(run)

    summary = []
    for filter_name, rows in by_filter.items():
        summary.append(
            {
                "filter": filter_name,
                "audio_filter": rows[0]["audio_filter"],
                "mean_score": round(mean(row["score"] for row in rows), 4),
                "mean_chars_per_minute": round(mean(row["chars_per_minute"] for row in rows), 2),
                "failed_windows": sum(1 for row in rows if row.get("failed")),
                "total_hallucinations": sum(row["hallucinations"] for row in rows),
                "total_repetition_penalties": sum(row["repeated_char_runs"] + row["repeated_phrase_runs"] for row in rows),
            }
        )
    summary.sort(key=lambda row: row["mean_score"], reverse=True)
    raw = next(row for row in summary if row["filter"] == "raw")
    best = summary[0]
    improvement = round(best["mean_score"] - raw["mean_score"], 4)
    recommended = best if best["filter"] != "raw" and improvement >= args.min_improvement else raw

    report = {
        "input": str(args.input),
        "windows": [{"start": s, "duration": d} for s, d in windows],
        "min_improvement": args.min_improvement,
        "raw_mean_score": raw["mean_score"],
        "best_mean_score": best["mean_score"],
        "best_minus_raw": improvement,
        "recommended_filter": recommended["filter"],
        "recommended_audio_filter": recommended["audio_filter"],
        "summary": summary,
        "runs": runs,
    }
    (args.out_dir / "comparison.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    recommendation = "raw audio" if recommended["audio_filter"] is None else recommended["audio_filter"]
    (args.out_dir / "recommendation.txt").write_text(
        f"Recommended: {recommended['filter']} ({recommendation})\n"
        f"Best-minus-raw score: {improvement}\n"
        "Only use denoising on the full run when this recommendation is not raw audio.\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
