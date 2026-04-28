#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import av
import imageio_ffmpeg
from faster_whisper import WhisperModel


def ffmpeg() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def sec_to_hms(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def parse_hms(value: str) -> float:
    parts = value.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    if len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    return float(value)


def media_duration(path: Path) -> float:
    container = av.open(str(path))
    try:
        if container.duration is None:
            raise RuntimeError("Could not determine media duration")
        return float(container.duration / 1_000_000)
    finally:
        container.close()


def extract_wav(
    src: Path,
    dst: Path,
    start: float,
    duration: float,
    audio_filter: Optional[str] = None,
) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg(),
        "-y",
        "-ss",
        sec_to_hms(start),
        "-t",
        sec_to_hms(duration),
        "-i",
        str(src),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
    ]
    if audio_filter:
        cmd += ["-af", audio_filter]
    cmd += [
        "-c:a",
        "pcm_s16le",
        str(dst),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def load_glossary(path: Optional[Path]) -> list[str]:
    """Load a glossary file: one term per line, '#' starts a comment."""
    if not path:
        return []
    terms: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        terms.append(line)
    return terms


def merge_glossary_with_arg(file_terms: list[str], arg_value: Optional[str]) -> Optional[str]:
    """Combine glossary file terms with a comma-separated CLI value, dedup preserving order."""
    seen: set[str] = set()
    out: list[str] = []
    for source in (file_terms, [t.strip() for t in (arg_value or "").split(",") if t.strip()]):
        for term in source:
            key = term.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(term)
    if not out:
        return None
    return ", ".join(out)


def transcribe_chunk(
    model: WhisperModel,
    wav_path: Path,
    *,
    language: Optional[str],
    beam_size: int,
    initial_prompt: Optional[str],
    hotwords: Optional[str],
    vad_filter: bool = True,
) -> tuple[str, list[dict]]:
    segments, info = model.transcribe(
        str(wav_path),
        beam_size=beam_size,
        vad_filter=vad_filter,
        language=language,
        initial_prompt=initial_prompt,
        hotwords=hotwords,
    )
    rows = []
    lines = [f"language {info.language} prob {info.language_probability}"]
    for seg in segments:
        row = {"start": seg.start, "end": seg.end, "text": seg.text.strip()}
        rows.append(row)
        lines.append(f"[{seg.start:8.2f} -> {seg.end:8.2f}] {seg.text.strip()}")
    return "\n".join(lines) + "\n", rows


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("input")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--model", default="tiny")
    p.add_argument("--chunk-minutes", type=float, default=10.0)
    p.add_argument("--start", default=None)
    p.add_argument("--duration", default=None)
    p.add_argument("--language", default=None)
    p.add_argument("--beam-size", type=int, default=1)
    p.add_argument("--initial-prompt", default=None)
    p.add_argument("--hotwords", default=None)
    p.add_argument(
        "--glossary-file",
        default=None,
        help="Path to a UTF-8 text file with one term per line ('#' for comments). "
             "Terms are merged with --hotwords and (when --initial-prompt is empty) "
             "used to seed the initial prompt.",
    )
    p.add_argument(
        "--audio-filter",
        default=None,
        help="Optional ffmpeg -af expression applied during chunk extraction. "
             "Useful for noisy / music-heavy recordings, e.g. "
             "'highpass=f=80,lowpass=f=8000,loudnorm=I=-16:LRA=11:TP=-1.5'.",
    )
    p.add_argument(
        "--vad-filter",
        choices=("on", "off"),
        default="on",
        help="Toggle faster-whisper VAD pre-filter. Turn off for very dense / overlapping speech.",
    )
    p.add_argument(
        "--keep-temp-files",
        action="store_true",
        help="Keep extracted chunk WAV files instead of deleting them after transcription.",
    )
    args = p.parse_args()

    src = Path(args.input).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    glossary_terms = load_glossary(Path(args.glossary_file).expanduser().resolve()) if args.glossary_file else []
    hotwords = merge_glossary_with_arg(glossary_terms, args.hotwords)
    initial_prompt = args.initial_prompt
    if initial_prompt is None and glossary_terms:
        initial_prompt = ", ".join(glossary_terms)

    total_duration = media_duration(src)
    start = parse_hms(args.start) if args.start else 0.0
    usable_duration = parse_hms(args.duration) if args.duration else total_duration - start

    model_name = args.model
    model = WhisperModel(model_name, device="cpu", compute_type="int8")

    chunk_seconds = max(30.0, args.chunk_minutes * 60.0)
    chunk_count = int(math.ceil(usable_duration / chunk_seconds))

    all_segments: list[dict] = []
    text_parts: list[str] = []
    temp_root: Optional[Path] = None
    if args.keep_temp_files:
        temp_root = out_dir / "temp-wav"
        temp_root.mkdir(parents=True, exist_ok=True)
    else:
        temp_root = Path(tempfile.mkdtemp(prefix="local-transcribe-", dir=str(out_dir)))

    manifest = {
        "input": str(src),
        "model": model_name,
        "start": start,
        "duration": usable_duration,
        "chunk_seconds": chunk_seconds,
        "language": args.language,
        "beam_size": args.beam_size,
        "initial_prompt": initial_prompt,
        "hotwords": hotwords,
        "glossary_file": args.glossary_file,
        "glossary_terms": glossary_terms,
        "audio_filter": args.audio_filter,
        "vad_filter": args.vad_filter,
        "keep_temp_files": args.keep_temp_files,
        "chunks": [],
    }

    try:
        for i in range(chunk_count):
            chunk_start = start + i * chunk_seconds
            remaining = start + usable_duration - chunk_start
            this_duration = min(chunk_seconds, remaining)
            if this_duration <= 0:
                break
            wav_path = temp_root / f"chunk-{i:03d}.wav"
            extract_wav(src, wav_path, chunk_start, this_duration, audio_filter=args.audio_filter)
            text, rows = transcribe_chunk(
                model,
                wav_path,
                language=args.language,
                beam_size=args.beam_size,
                initial_prompt=initial_prompt,
                hotwords=hotwords,
                vad_filter=args.vad_filter == "on",
            )
            text_parts.append(f"## chunk {i:03d} start={sec_to_hms(chunk_start)} duration={sec_to_hms(this_duration)}\n{text}")
            adjusted_rows = []
            for row in rows:
                adjusted = {
                    "chunk": i,
                    "abs_start": chunk_start + row["start"],
                    "abs_end": chunk_start + row["end"],
                    "text": row["text"],
                }
                adjusted_rows.append(adjusted)
                all_segments.append(adjusted)
            chunk_manifest = {
                "chunk": i,
                "start": chunk_start,
                "duration": this_duration,
                "segment_count": len(rows),
            }
            if args.keep_temp_files:
                chunk_manifest["wav"] = str(wav_path)
            manifest["chunks"].append(chunk_manifest)
    finally:
        if temp_root and temp_root.exists() and not args.keep_temp_files:
            shutil.rmtree(temp_root)

    (out_dir / "transcript.txt").write_text("\n".join(text_parts))
    (out_dir / "segments.json").write_text(json.dumps(all_segments, indent=2))
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
