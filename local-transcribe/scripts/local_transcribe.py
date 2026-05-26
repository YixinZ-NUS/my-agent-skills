#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import av
import imageio_ffmpeg
from av.error import FFmpegError
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
    try:
        container = av.open(str(path))
        try:
            if container.duration is None:
                raise RuntimeError("Could not determine media duration")
            return float(container.duration / 1_000_000)
        finally:
            container.close()
    except FFmpegError:
        result = subprocess.run(
            [ffmpeg(), "-hide_banner", "-i", str(path)],
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


def build_glossary_prompt(terms: list[str], max_chars: int) -> Optional[str]:
    if not terms or max_chars <= 0:
        return None
    selected: list[str] = []
    current_len = len("Domain terms: ")
    for term in terms:
        extra = len(term) + (2 if selected else 0)
        if current_len + extra > max_chars:
            break
        selected.append(term)
        current_len += extra
    if not selected:
        return None
    return "Domain terms: " + ", ".join(selected)


def resolve_chinese_script(language: Optional[str], requested: str) -> str:
    if requested != "auto":
        return requested
    if language and language.lower() in {"zh", "zh-cn", "cmn", "mandarin"}:
        return "simplified"
    return "none"


def make_text_normalizer(chinese_script: str):
    if chinese_script == "none":
        return lambda text: text
    try:
        from opencc import OpenCC
    except ImportError as exc:
        raise SystemExit(
            "Chinese script normalization requires opencc-python-reimplemented. "
            "Install it with: pip install opencc-python-reimplemented"
        ) from exc

    config = {
        "simplified": "t2s",
        "traditional": "s2t",
    }[chinese_script]
    converter = OpenCC(config)
    return converter.convert


def transcribe_chunk(
    model: WhisperModel,
    wav_path: Path,
    *,
    language: Optional[str],
    beam_size: int,
    initial_prompt: Optional[str],
    hotwords: Optional[str],
    normalize_text,
    condition_on_previous_text: bool,
    vad_filter: bool = True,
) -> tuple[str, list[dict]]:
    segments, info = model.transcribe(
        str(wav_path),
        beam_size=beam_size,
        vad_filter=vad_filter,
        language=language,
        initial_prompt=initial_prompt,
        hotwords=hotwords,
        condition_on_previous_text=condition_on_previous_text,
    )
    rows = []
    lines = [f"language {info.language} prob {info.language_probability}"]
    for seg in segments:
        text = normalize_text(seg.text.strip())
        row = {"start": seg.start, "end": seg.end, "text": text}
        rows.append(row)
        lines.append(f"[{seg.start:8.2f} -> {seg.end:8.2f}] {text}")
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
    p.add_argument(
        "--chinese-script",
        choices=("auto", "none", "simplified", "traditional"),
        default="auto",
        help="Normalize Chinese transcript text. 'auto' converts zh output to Simplified Chinese.",
    )
    p.add_argument("--beam-size", type=int, default=1)
    p.add_argument("--initial-prompt", default=None)
    p.add_argument(
        "--max-initial-prompt-chars",
        type=int,
        default=500,
        help="Cap glossary-seeded initial prompt length. Hotwords still receive the full glossary.",
    )
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
        "--condition-on-previous-text",
        choices=("on", "off"),
        default="off",
        help="Carry previous decoded text as prompt inside a chunk. Off is safer for long Chinese recordings.",
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
        initial_prompt = build_glossary_prompt(glossary_terms, args.max_initial_prompt_chars)
    chinese_script = resolve_chinese_script(args.language, args.chinese_script)
    normalize_text = make_text_normalizer(chinese_script)

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
        "chinese_script": chinese_script,
        "beam_size": args.beam_size,
        "initial_prompt": initial_prompt,
        "max_initial_prompt_chars": args.max_initial_prompt_chars,
        "hotwords": hotwords,
        "glossary_file": args.glossary_file,
        "glossary_terms": glossary_terms,
        "audio_filter": args.audio_filter,
        "vad_filter": args.vad_filter,
        "condition_on_previous_text": args.condition_on_previous_text,
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
                normalize_text=normalize_text,
                condition_on_previous_text=args.condition_on_previous_text == "on",
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

    (out_dir / "transcript.txt").write_text("\n".join(text_parts), encoding="utf-8")
    (out_dir / "segments.json").write_text(json.dumps(all_segments, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
