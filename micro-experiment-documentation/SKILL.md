---
name: micro-experiment-documentation
description: >
  Plan, execute, and document exploratory micro-experiments for software
  engineering investigations (codec paths, pipeline alternatives, hardware
  quirks, protocol variations). Use when an investigation requires iterative
  hypothesis testing, when prior conclusions may be wrong, or when an
  experiment design needs a rubber-duck critique before execution.
license: MIT
metadata:
  author: YixinZ-NUS
  version: "1.0"
  repo: https://github.com/YixinZ-NUS/insight-io-agent-skills
  changelog: See CHANGELOG.md in the repo root.
compatibility: Designed for GitHub Copilot CLI / Claude Code (or similar products)
---

# Micro-Experiment Documentation

## Step 0 — Before You Execute: Rubber-Duck the Plan

Write the full experiment plan first, then **critique it as if reviewing
someone else's work**:

- **Isolation check**: Does each experiment actually isolate the one variable
  you think it does?
- **Confounding variables**: Does the setup accidentally change two things at
  once?
- **Circular reasoning**: Are you measuring the symptom instead of the cause?
- **Tool bias**: Are you seeing "no error" because the tool hides it?
  (e.g., `-loglevel error` silently swallows corruption that
  `-err_detect +careful` catches)
- **Symmetry**: If two experiments target opposite hypotheses, they must share
  identical setup except for the single variable being tested.

A 5-minute critique can save hours down a wrong path.

## Step 1 — Create the Report First

Before running any experiment, create (or append to) a markdown report under
`docs/experiments/` in the repository. Do **not** start executing until the
plan is written and rubber-ducked.

## Step 2 — Structure Each Experiment Entry

Number experiments sequentially within the report (`Exp 1`, `Exp 2`, …) so
cross-references are unambiguous. For each entry:

| Field | Content |
|-------|---------|
| **Hypothesis** | What you expect to observe and why |
| **Setup** | Exact commands, config, hardware, software versions |
| **Result** | Raw output (truncate if huge; include pointer to full log) |
| **Conclusion** | What the result proves or disproves |

## Step 3 — Record Negative Results

Knowing that approach X fails under condition Y is just as valuable as a
success. Document failures with the same rigor as successes.

## Step 4 — Summarize

End the report with a decision table and the chosen path forward, linking to
the relevant `docs/past-tasks.md` entry.

---

## Re-Experimenting May Overturn Prior Conclusions

Treat earlier negative results as **hypotheses, not facts** when revisiting a
problem. Prior conclusions can be wrong even when they looked definitive.

### Case Study — MJPEG RTSP Corruption (`libav-rtsp-publisher`)

Prior experiments 10–11 stripped DRI restart markers from Xiaomi JPEG frames
and observed 450 errors (down from 537). Conclusion: *"DRI is not the root
cause."* That conclusion was **wrong** because:

- Stripping the DRI marker from the header without removing the corresponding
  restart markers (RST₀–RST₇) from the scan data left the JPEG structurally
  inconsistent.
- The experiment changed two things at once — a confounding variable masked the
  real cause.

When the question was re-approached from a simpler angle (probe for DRI
presence → route to re-encode), the fix was immediate and zero-error.

### Lessons

- When a prior experiment says "X is not the cause", ask: "Did the experiment
  cleanly remove X, or did it introduce new breakage while trying to remove X?"
- Simpler experiments are more trustworthy. Complex byte surgery usually
  introduces confounding variables.
- Start from first principles rather than building on prior (possibly flawed)
  experiment infrastructure.
