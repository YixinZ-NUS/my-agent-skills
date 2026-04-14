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
2. **Rubber-duck the plan** (see Part B, Step B0).
3. Execute with full Setup / Result / Conclusion documentation.
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

### Step B0 — Rubber-Duck the Plan First

Write the full experiment plan, then **critique it as if reviewing someone
else's work** before running anything:

- **Isolation**: Does each experiment isolate exactly one variable?
- **Confounding variables**: Does the setup accidentally change two things
  at once?
- **Circular reasoning**: Are you measuring the symptom instead of the
  cause?
- **Tool bias**: Are you seeing "no error" because the tool hides it?
  (e.g., `-loglevel error` silently swallows corruption that
  `-err_detect +careful` catches)
- **Symmetry**: Experiments targeting opposite hypotheses must share an
  identical setup except for the single variable under test.

A 5-minute critique can save hours down a wrong path.

### Step B1 — Create the Report First

Before running any experiment, create (or append to) a markdown report under
`docs/experiments/`. Do **not** start executing until the plan is written and
rubber-ducked.

### Step B2 — Structure Each Experiment Entry

Number experiments sequentially (`Exp 1`, `Exp 2`, …). For each entry:

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
