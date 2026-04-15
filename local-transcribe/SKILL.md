---
name: "local-transcribe"
description: "Transcribe local audio or video files without an API key using ffmpeg extraction plus faster-whisper on CPU. Use when OpenAI transcription is unavailable, when a user wants local-only transcription, or when extracting insights from recordings in mp4/m4a/mp3/wav formats."
---

# Local Transcribe

Use this skill for local transcription when `OPENAI_API_KEY` is unavailable or when the user explicitly wants a local-only path.

## Workflow

1. Use `scripts/local_transcribe.py`.
2. Prefer chunked transcription for long files.
3. If the recording contains domain-specific names or acronyms, pass them in as `--initial-prompt` or `--hotwords`.
4. Save outputs under `output/local-transcribe/<job>/`.
5. By default, chunk WAVs are treated as temporary intermediates and deleted automatically after transcription.
6. Review the transcript for quality before drawing conclusions.

## Dependencies

The script expects:

- `imageio-ffmpeg`
- `faster-whisper`

Install if missing:

```bash
python -m pip install imageio-ffmpeg faster-whisper
```

## Recommended commands

Single file, plain text:

```bash
python ~/.codex/skills/local-transcribe/scripts/local_transcribe.py \
  /path/to/input.mp4 \
  --language en \
  --out-dir output/local-transcribe/job-name
```

Faster first pass:

```bash
python ~/.codex/skills/local-transcribe/scripts/local_transcribe.py \
  /path/to/input.mp4 \
  --model tiny \
  --language en \
  --chunk-minutes 10 \
  --out-dir output/local-transcribe/job-name
```

Higher-accuracy follow-up on selected sections:

```bash
python ~/.codex/skills/local-transcribe/scripts/local_transcribe.py \
  /path/to/input.mp4 \
  --model small \
  --language en \
  --beam-size 3 \
  --initial-prompt "GMPA, MOYA Analytics, Moya Cascade, NDC Partnership, NCCS, ASEAN Centre for Energy, Benedict Chia" \
  --hotwords "GMPA, MOYA, Cascade, NDC, NCCS, ASEAN, Benedict Chia" \
  --start 00:20:00 \
  --duration 00:10:00 \
  --out-dir output/local-transcribe/job-name-section
```

Keep chunk WAVs only when you need to debug alignment or model quality:

```bash
python ~/.codex/skills/local-transcribe/scripts/local_transcribe.py \
  /path/to/input.mp4 \
  --model small \
  --language en \
  --keep-temp-files \
  --out-dir output/local-transcribe/job-name-debug
```

## Notes

- `tiny` is good for quick discovery.
- `small` is better for higher-value excerpts.
- For long panels, transcribe in chunks first, then re-run higher-accuracy passes only on the most relevant sections.
- `--initial-prompt` helps with acronyms, speaker names, and domain vocabulary.
- `--hotwords` helps when the same terms recur many times and spelling matters.
- Temporary chunk WAVs are deleted by default; use `--keep-temp-files` only when debugging.
