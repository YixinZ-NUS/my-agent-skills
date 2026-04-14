# Changelog

All notable changes to this project are documented here.

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
