---
name: "local-transcribe"
description: "Transcribe local audio or video files without an API key using ffmpeg + faster-whisper on CPU, then iteratively refine the transcript with glossary, audio A/B, subagent review, and context-link passes. Use when OpenAI transcription is unavailable, when the user wants local-only transcription, when Chinese/English mixed jargon is misrecognised, or when noisy audio needs proven preprocessing."
---

# Local Transcribe

Local transcription that **self-improves**. Use this skill when:

- `OPENAI_API_KEY` is unavailable, or the user explicitly wants a local-only path.
- The recording contains domain-specific names, acronyms, or product names that
  generic ASR mishears (e.g. KYB→KIB, FinTech→FTAG, Webhook→YPOK, KYT→KYIT,
  Manus→Mandas, Lovable→Lobo, BitGet→BitGate, SafeHeron→Safe Haram, SumSub→SumSum).
- The recording is in English; or in Simplified Chinese, possibly with embedded English jargon.
- You want the corrections to **persist** across runs as a local glossary
  (a "wiki" the user can grow over time), instead of re-prompting the LLM
  every conversation.

The skill exposes composable scripts, glossary files, and starter reference maps.
The agent (you) drives the iterative refinement loop.

## Files

```
local-transcribe/
├── SKILL.md
├── scripts/
│   ├── local_transcribe.py     # one-pass faster-whisper transcription with hotwords/glossary
│   ├── extract_suspects.py     # heuristic detector of likely-misrecognised tokens
│   ├── compare_audio_filters.py # prove whether denoising beats raw audio on sample windows
│   ├── concat_segments.py      # combine split recorder files into one continuous transcript
│   ├── refine_transcript.py    # merge a refinement pass into a baseline by timestamp
│   ├── review_transcript.py    # create subagent review packets + apply exact corrections
│   └── context_links.py        # render first-mention web/context links into Markdown
└── glossaries/
    ├── robotics-world-models-zh-en.txt
    ├── ui-ux-en.txt
    ├── web3-finance-en.txt
    ├── web3-finance-zh.txt
    └── ...                     # add domain-specific files here, one term per line
└── references/
    └── robotics-world-models-starter.json
```

## Dependencies

Python 3.10+ in a venv:

```bash
python3 -m venv .venv-transcribe
.venv-transcribe/bin/pip install --upgrade pip
.venv-transcribe/bin/pip install faster-whisper imageio-ffmpeg av opencc-python-reimplemented
```

`av` is used for media duration probing; `imageio-ffmpeg` ships a static ffmpeg.
`opencc-python-reimplemented` normalizes `--language zh` output to Simplified
Chinese by default.
No API key required.

## Self-improving workflow (the main loop)

This is the workflow you should drive on a non-trivial recording. Each step is
small; iterate until the suspect list is empty or stable.

```
            ┌─────────────────────────────┐
            │  0. audio A/B check         │
            │  raw vs mild denoise        │
            └─────────────┬───────────────┘
                          ▼
            ┌─────────────────────────────┐
            │  1. baseline pass           │
            │  model=small|medium         │
            │  zh→Simplified if needed    │
            └─────────────┬───────────────┘
                          ▼
            ┌─────────────────────────────┐
            │  2. extract suspect tokens  │
            │  + LLM-driven correction    │
            │    (you read the transcript)│
            └─────────────┬───────────────┘
                          ▼
            ┌─────────────────────────────┐
            │  3. update glossary file    │
            │  (this is the local wiki)   │
            └─────────────┬───────────────┘
                          ▼
            ┌─────────────────────────────┐
            │  4. refinement pass         │
            │  model=small|medium         │
            │  --glossary-file ...        │
            │  optionally --start/--dur   │
            └─────────────┬───────────────┘
                          ▼
            ┌─────────────────────────────┐
            │  5. merge with baseline     │
            │  (refine_transcript.py)     │
            └─────────────┬───────────────┘
                          ▼
            ┌─────────────────────────────┐
            │  6. subagent review packets │
            │  apply exact corrections    │
            └─────────────┬───────────────┘
                          ▼
            ┌─────────────────────────────┐
            │  7. add context links       │
            │  from proactive web search  │
            └─────────────┬───────────────┘
                          ▼
                    converged? → stop
                    else → back to 2
```

### 0. Prove whether denoising helps

Before applying `--audio-filter` to the full file, test identical windows and
only use denoising if it beats raw audio by score:

```bash
.venv-transcribe/bin/python local-transcribe/scripts/compare_audio_filters.py \
  test/MyRec_0523_1813.m4a \
  --model small \
  --language zh \
  --beam-size 3 \
  --glossary-file local-transcribe/glossaries/robotics-world-models-zh-en.txt \
  --out-dir output/local-transcribe/audio-ab/MyRec_0523_1813
```

Read `recommendation.txt`. If it says `raw`, do **not** denoise the full run.
If it recommends an ffmpeg filter, pass that exact expression to
`local_transcribe.py --audio-filter`.

### 1. Baseline pass

```bash
.venv-transcribe/bin/python local-transcribe/scripts/local_transcribe.py \
  test-cn-2.mp4 \
  --model small \
  --language zh \
  --chinese-script simplified \
  --chunk-minutes 5 \
  --out-dir output/local-transcribe/cn2-baseline
```

Use `tiny` for English discovery, `small` for English production or Chinese
discovery, `medium`/`large-v3` for high-stakes Chinese (slower).

### 2. Extract suspect tokens

```bash
.venv-transcribe/bin/python local-transcribe/scripts/extract_suspects.py \
  output/local-transcribe/cn2-baseline/transcript.txt
```

The script flags:

- ALL-CAPS Latin acronyms (`KIB`, `FTAG`, `YPOK`, `KYIT`, `EGML`, …).
- Mixed-case oddities (`WBHook`, `iOS`, `BitGate`, `AgentCypher`).
- Chinese segments containing embedded Latin words (the most common error
  source in zh audio).

Then **read the flagged segments yourself**. For each suspect token, decide:

- "This is wrong; the real term is X" → add X to the glossary file.
- "This is correct; ignore" → leave it.

If you're unsure, listen back to the timestamp (the script prints `HH:MM:SS`).
Look for context cues in adjacent segments: a misheard "KIB" near "Know Your"
is almost certainly KYB; "Mandas" near "公司" is almost certainly Manus.

### 3. Update the glossary file

Glossary files live under `local-transcribe/glossaries/`, one term per line,
`#` for comments. Existing files are starting points — copy and edit per job.

Treat this file as durable: commit it (or sync it) so the next run on a
similar recording starts smarter. **It grows with use.**

### 4. Refinement pass

```bash
.venv-transcribe/bin/python local-transcribe/scripts/local_transcribe.py \
  test-cn-2.mp4 \
  --model small \
  --language zh \
  --chinese-script simplified \
  --beam-size 3 \
  --chunk-minutes 5 \
  --glossary-file local-transcribe/glossaries/cn-2-web3-founder.txt \
  --out-dir output/local-transcribe/cn2-refined
```

Tighten focus by re-running only the slice that still has errors:

```bash
  --start 00:01:30 --duration 00:02:00 \
  --model medium \
```

`--glossary-file` does two things:

1. Joins terms into `--hotwords` (faster-whisper biases beam search toward them).
2. Seeds `--initial-prompt` (gives whisper sentence-level context) when no
   `--initial-prompt` was passed explicitly. This prompt is capped by
   `--max-initial-prompt-chars` so large glossaries do not overflow Whisper's
   context window; the full glossary still goes to hotwords.

### 5. Merge refinement into baseline

```bash
.venv-transcribe/bin/python local-transcribe/scripts/refine_transcript.py \
  --baseline output/local-transcribe/cn2-baseline/segments.json \
  --refined  output/local-transcribe/cn2-refined/segments.json \
  --out-dir  output/local-transcribe/cn2-merged
```

The merger drops baseline segments overlapping the refined window
(plus a 1 s pad) and slots the refined ones in. Output is sorted by
`abs_start`. Chain merges by feeding `cn2-merged/segments.json` back as
`--baseline` for the next slice.

For split recorder files, transcribe each file separately, then concatenate in
chronological order:

```bash
.venv-transcribe/bin/python local-transcribe/scripts/concat_segments.py \
  output/local-transcribe/part-1813 \
  output/local-transcribe/part-1839 \
  output/local-transcribe/part-1906 \
  --out-dir output/local-transcribe/full-seminar
```

### Convergence

Re-run `extract_suspects.py` on the merged transcript. Stop when:

- The suspect token list contains only true acronyms / proper nouns that
  are spelled correctly, **or**
- Two consecutive iterations produce the same flagged set
  (no further improvement available without a bigger model).

### 6. Subagent-driven transcript review

After ASR refinement converges, create review packets and send independent
packets to subagents. The packets are intentionally strict: reviewers must
return exact JSON corrections, not a rewritten transcript.

```bash
.venv-transcribe/bin/python local-transcribe/scripts/review_transcript.py make-packets \
  output/local-transcribe/job-merged/segments.json \
  --out-dir output/local-transcribe/job-review \
  --domain-context "Seminar on robotics, world models, world action models, and agentic workflows."
```

For each `review-packet-NNN.md`, launch a subagent with the packet content and
ask it to write `corrections-NNN.json` using the packet schema. Then apply the
reviewed corrections:

```bash
.venv-transcribe/bin/python local-transcribe/scripts/review_transcript.py apply-corrections \
  output/local-transcribe/job-merged/segments.json \
  --corrections output/local-transcribe/job-review \
  --out-dir output/local-transcribe/job-reviewed
```

The applier fails if a correction does not match exact original text. This keeps
the review auditable and prevents silent broad rewrites.

### 7. Web context links for downstream digesting

For digest-ready transcripts, proactively web-search the first mentions of
research terms, papers, labs, tools, and frameworks. Save the selected links as
a JSON array like `local-transcribe/references/robotics-world-models-starter.json`
or a job-specific reference file, then render the Markdown transcript:

```bash
.venv-transcribe/bin/python local-transcribe/scripts/context_links.py \
  output/local-transcribe/job-reviewed/segments.json \
  --references local-transcribe/references/robotics-world-models-starter.json \
  --out-dir output/local-transcribe/job-final \
  --title "Robotics / World Models Seminar Transcript"
```

The output includes:

- `annotated_transcript.md` — full transcript with first mentions linked.
- `context_links.md` — compact source index for downstream summaries.
- `first_mentions.json` — machine-readable timestamp map.

## Simplified Chinese tips

- Always pass `--language zh`. Auto-detect occasionally picks `en` on short
  silences and hallucinates "I'm gonna share with you…" sentences.
- `--chinese-script auto` converts `zh` transcripts to Simplified Chinese.
  Pass `--chinese-script none` only if you want raw Whisper output.
- Default `--vad-filter on` is best for clean speech; turn it off
  (`--vad-filter off`) for dense panels where speakers overlap and VAD
  drops valid speech as "silence".
- Default `--condition-on-previous-text off` is intentional for long Chinese
  recordings; it reduces prompt-growth errors and repeated hallucinations.
- `--beam-size 3` is a good Chinese sweet spot. `1` is fine for fast
  discovery; `5+` rarely pays off.
- `medium` is materially better than `small` on zh, at ~3× the runtime.
  `large-v3` is the next jump but needs ~3 GB RAM and ~6× small-runtime.
- Embedded English terms benefit most from hotwords. Pure-Chinese
  mistranscriptions (e.g. "产严"→"产品", "可教科"→"可交互") are best fixed by:
  1. running a larger model on the affected slice, or
  2. post-edit pass (an LLM-driven correction map; out of scope for this
     skill but easy to build on top of `segments.json`).

## Audio preprocessing (use sparingly)

`--audio-filter` injects an ffmpeg `-af` chain during chunk extraction.

Only use it on **noisy** sources — music beds, phone-call compression, low SNR —
and only after `compare_audio_filters.py` proves it improves sample windows.
On clean speech, aggressive filters (especially `loudnorm`) can cause whisper
to hallucinate (we observed it switching language mid-clip). Recommended chains:

```text
# Mild — phone-call-ish recordings
highpass=f=80,lowpass=f=8000

# Moderate — heavy background music
highpass=f=120,lowpass=f=7000,afftdn=nr=12

# Last resort — only when speech is clearly buried
highpass=f=120,lowpass=f=7000,afftdn=nr=20,loudnorm=I=-16:LRA=11:TP=-1.5
```

If the refinement pass starts producing English mid-Chinese audio, **drop
the audio filter** and fall back to raw extraction.

## CLI reference

```text
local_transcribe.py INPUT --out-dir DIR
  --model           tiny | base | small | medium | large-v3   (default tiny)
  --chunk-minutes   float, default 10.0 (lower bound 0.5)
  --start HH:MM:SS  start offset (default beginning)
  --duration HH:MM:SS  cap on transcribed length (default to EOF)
  --language        ISO code, e.g. en, zh; omit for auto-detect
  --chinese-script  auto | none | simplified | traditional (default auto)
  --beam-size       int, default 1 (3 for refinement passes)
  --initial-prompt  free-form sentence-level context (overrides glossary seeding)
  --max-initial-prompt-chars  default 500; set lower if Whisper reports position overflow
  --hotwords        comma-separated terms (merged with glossary file)
  --glossary-file   path to a one-term-per-line file
  --audio-filter    ffmpeg -af expression (use sparingly)
  --vad-filter      on | off (default on)
  --condition-on-previous-text on | off (default off)
  --keep-temp-files keep extracted chunk WAVs for debugging
```

Outputs in `--out-dir`:

- `transcript.txt` — chunked human-readable transcript with timestamps.
- `segments.json`  — list of `{chunk, abs_start, abs_end, text}` records.
- `manifest.json`  — exact parameters used, for reproducibility.

## Notes

- `tiny`: fast discovery only.
- `small`: solid for English; baseline for Chinese.
- `medium` / `large-v3`: high-value Chinese refinement on focused slices.
- `--initial-prompt` and `--hotwords` are independent levers.
  `--glossary-file` populates both.
- Temporary chunk WAVs are deleted by default; pass `--keep-temp-files`
  only when debugging alignment or model quality.
- The skill is intentionally agent-driven: you (the LLM) inspect the
  transcript, propose corrections, update the glossary, and re-run.
  This is what turns one transcription into a growing local knowledge base.
