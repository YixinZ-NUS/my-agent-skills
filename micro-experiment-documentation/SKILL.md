---
name: micro-experiment-documentation
description: >
  Plan, execute, and document exploratory micro-experiments and experiment
  branches for software engineering investigations (codec paths, pipeline
  alternatives, hardware quirks, protocol variations, or any isolatable
  hypothesis). Use when starting an experiment branch workflow, when an
  investigation requires iterative hypothesis testing, when prior conclusions
  may need revisiting, or when an experiment design needs a rubber-duck
  critique before execution.
license: MIT
metadata:
  author: YixinZ-NUS
  version: "2.0"
  repo: https://github.com/YixinZ-NUS/insight-io-agent-skills
  changelog: See CHANGELOG.md in the repo root.
compatibility: Designed for GitHub Copilot CLI / Claude Code (or similar products)
---

# Micro-Experiment Documentation

This skill covers two interleaved concerns:

1. **Experiment Branch Workflow** — the end-to-end lifecycle for creating,
   validating, and landing an experiment branch.
2. **Micro-Experiment Documentation** — how to plan, execute, and record
   individual experiments within a branch.

---

## Part A — Experiment Branch Workflow

A standard five-step process for any experiment branch. Each step produces a
clear handoff artifact so work can be resumed by any agent or human.

### Step A1 — Plan

1. Read the full project doc chain before writing any code (README → PRD /
   architecture docs → task list → feature scoreboard → past-tasks).
2. Create a `plan.md` in the session folder with one section per experiment
   task: problem statement, approach, key files.
3. Track tasks in a SQL `todos` table with dependency edges.

**Handoff artifact:** `plan.md` + SQL todos at `pending` status.

### Step A2 — Branch & Implement

1. Create `experiment/<name>` from `main` (or the project's default branch).
2. Write `docs/tasks/task-<N>-<name>.md` — implementation report with
   findings, code changes, and conclusions.
3. Commit incrementally; each commit scoped to one logical change.
4. Build and run the test suite before pushing.

**Handoff artifact:** Branch with task report committed.

### Step A3 — PR & Review

1. Create PR: `gh pr create --base main --head experiment/<name>`.
2. Request an automated or peer review.
3. Classify each review item:
   - **real fix** — apply it
   - **cleanup** — apply if low-risk
   - **duplicate** — note and skip
   - **not actionable** — record rationale and skip
4. Push fixes to the same branch.

**Handoff artifact:** PR with review comments and fix commits.

### Step A4 — Micro-Experiment

Follow Part B below. For each branch:

1. Write the experiment plan with numbered experiments (Exp 1, Exp 2, …).
2. **Rubber-duck the plan** (see Part B, Step B0) — spawn subagents in parallel.
3. Execute each experiment — spawn a `general-purpose` subagent per experiment
   in parallel (see Part B, Step B2).
4. Save report as `docs/experiments/<name>.md`.
5. Commit and push to the experiment branch.

**Handoff artifact:** `docs/experiments/<name>.md` committed on branch.

### Step A5 — Final Sweep

1. Re-check review items against current code.
2. Confirm all experiment reports are committed.
3. Verify the branch builds and passes all tests.
4. Update `docs/past-tasks.md` with verification paths and flip `passes`
   to `true` only after actual verification has run.

**Handoff artifact:** Branch ready-to-merge with task report, experiment
report, and all review fixes applied.

---

## Part B — Micro-Experiment Documentation

### Step B0 — Rubber-Duck the Plan: Spawn Critics in Parallel

Self-review is weak — the same model that wrote the plan is reviewing it.
Instead, **spawn one `general-purpose` subagent per critique dimension in
parallel** before executing anything. Each agent gets the full experiment plan
as context and a single focused question. Launch all of them in one turn:

| Agent name | Prompt |
|------------|--------|
| `critic-isolation` | "Review this experiment plan. For each experiment, does it isolate exactly one variable, or does the setup change multiple things at once? List every isolation failure you find." |
| `critic-confounds` | "Review this experiment plan. Identify any confounding variables — places where the setup accidentally changes something other than the intended variable. Be specific." |
| `critic-reasoning` | "Review this experiment plan. Flag any circular reasoning: cases where the measurement captures the symptom rather than the root cause." |
| `critic-tool-bias` | "Review this experiment plan. Identify tool bias: places where the chosen tool, flag, or log level could hide failures. Suggest stricter alternatives." |
| `critic-symmetry` | "Review this experiment plan. For any pair of experiments that test opposite hypotheses, check that their setups are identical except for the one variable under test." |

Collect all responses before running a single experiment. Revise the plan to
address every issue raised. A critique that costs 5 minutes of parallel compute
routinely saves hours of investigation down a wrong path.

**Minimum bar**: at least one `general-purpose` critic agent must find zero
blocking issues before execution proceeds. If any agent flags a blocking issue,
revise and re-run that agent.

### Step B1 — Create the Report First

Before running any experiment, create (or append to) a markdown report under
`docs/experiments/`. Do **not** start executing until the plan is written and
rubber-ducked.

### Step B2 — Execute Experiments in Parallel via Subagents

For independent experiments (no data dependency between them), **spawn one
`general-purpose` subagent per experiment in a single turn**. Give each agent:

- The full experiment plan (hypothesis, setup, expected result)
- The repo path and any relevant source files
- The instruction to write its Hypothesis / Setup / Result / Conclusion block
  directly into `docs/experiments/<name>.md`

Experiments that depend on each other's results must run sequentially — spawn
the next agent only after reading the prior one's conclusion.

Each subagent's response becomes the experiment entry:

| Field | Content |
|-------|---------|
| **Hypothesis** | What you expect to observe and why |
| **Setup** | Exact commands, config, hardware, software versions |
| **Result** | Raw output (truncate if huge; pointer to full log) |
| **Conclusion** | What the result proves or disproves |

### Step B3 — Record Negative Results

Knowing that approach X fails under condition Y is just as valuable as a
success. Document failures with the same rigour as successes.

### Step B4 — Summarize

End the report with a decision table and the chosen path forward, linking to
the relevant `docs/past-tasks.md` entry.

---

## Prior Conclusions Can Be Wrong

Treat earlier negative results as **hypotheses, not facts** when revisiting a
problem.

**Why**: An experiment that appears to disprove hypothesis X may have
introduced a confounding variable that masked the real result. Before
concluding "X is not the cause", ask: "Did the experiment cleanly remove X,
or did it introduce new breakage while trying to?"

**Principle**: Simpler experiments are more trustworthy. If an experiment
requires complex structural surgery (byte-level, schema-level, etc.), it
probably has confounding variables. Revisit from first principles rather than
building on prior (possibly flawed) infrastructure.
