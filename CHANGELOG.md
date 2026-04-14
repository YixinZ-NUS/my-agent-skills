# Changelog

All notable changes to this project are documented here.

## [3.0] — 2026-04-14

### Changed
- `micro-experiment-documentation` skill: rubber-duck and execution steps now
  use subagents rather than self-review.
  - **Step B0** replaced with a parallel subagent critic pattern: spawn five
    `general-purpose` agents simultaneously (critic-isolation,
    critic-confounds, critic-reasoning, critic-tool-bias, critic-symmetry),
    each with a focused critique prompt. Execution is blocked until all agents
    report no blocking issues.
  - **Step B2** restructured: spawn one `general-purpose` agent per
    independent experiment in a single turn; sequential ordering only when
    experiments have data dependencies.
  - Step A4 (branch workflow) updated to call out parallel subagent execution
    explicitly.

## [2.0] — 2026-04-14

### Changed
- `micro-experiment-documentation` skill: restructured into two-part format.
  - **Part A — Experiment Branch Workflow**: generic five-step branch lifecycle
    (Plan → Branch & Implement → PR & Review → Micro-Experiment → Final Sweep),
    made adoptable for any project and future task types.
  - **Part B — Micro-Experiment Documentation**: renamed steps B0–B4 to avoid
    numbering collision with Part A; rubber-duck critique checklist retained.
  - Removed project-specific case study from skill body (kept conceptually as
    the "Prior Conclusions Can Be Wrong" principle section — project-neutral).
  - Expanded `description` field to also trigger on experiment branch workflow
    requests.
- Installed to `~/.agents/skills/` (cross-client standard path) instead of
  `~/.copilot/`.

## [1.0] — 2026-04-14

### Added
- `micro-experiment-documentation` skill: initial release.
  - Step-by-step process: create report first, structure each entry with
    Hypothesis / Setup / Result / Conclusion, number sequentially, record
    negative results, summarize with decision table.
  - Rubber-duck checklist for catching flawed experiment designs before
    execution (isolation, confounding variables, circular reasoning, tool
    bias, symmetry).
  - Guidance on overturning prior conclusions, with DRI/MJPEG case study
    from `libav-rtsp-publisher` experiments 10–11.
