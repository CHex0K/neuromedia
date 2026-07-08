# Task Spec: dynamic-finale-3sec-window

## Metadata
- Task ID: dynamic-finale-3sec-window
- Created: 2026-07-08T08:36:49+00:00
- Repo root: D:\Projects\Projects_Python\Media\neuromedia
- Working directory at init: D:\Projects\Projects_Python\Media\neuromedia

## Guidance sources
- AGENTS.md
- CLAUDE.md

## Original task statement
Fix generated Excel report so row 'Finale 18-20с' / final aggregate uses all frames from the last 3 seconds of the video based on actual frame timing/duration, instead of fixed frame rows 18-20 or the last three frames. The number of frames in the finale window must change dynamically with video length/frame segmentation.

## Acceptance criteria
- AC1: The report generator identifies the current fixed `Finale` behavior in `4_WINDOW_AGGREGATES` as a template formula problem.
- AC2: Generated workbooks compute the `Finale` row from all segment/frame rows that overlap the last 3 seconds of the video, using `tribe_segments.tsv` timing (`start`/`offset`/`timeline` plus `duration`) when available.
- AC3: The number of rows used by `Finale` changes with segment timing and is not hard-coded to rows 21-23, frames 18-20, or the last three rows when timing exists.
- AC4: If segment timing is unavailable, generation falls back to the previous safe behavior of using up to the last three available rows.
- AC5: The workbook labels for the `Finale` row no longer claim a fixed `18-20с` window.
- AC6: Focused checks prove the generated formulas and workbook JSON/code syntax are valid.

## Constraints
- Keep all task artifacts under `.agent/tasks/dynamic-finale-3sec-window/`.
- Preserve UTF-8 encoding.
- Make a focused change in report generation; avoid unrelated report redesign.
- Do not edit `Template_3_with_frames.xlsx` unless code-based generation cannot solve the bug.

## Non-goals
- Do not evaluate Excel formulas locally with Excel/LibreOffice.
- Do not change TRIBE segmentation or neural scoring.
- Do not change unrelated window aggregate rows.
- Do not regenerate user Google Drive files.

## Verification plan
- Build: Run `python -m py_compile template3_report.py`.
- Unit tests: Exercise the new final-window row selection helper with variable segment durations and missing timing fallback.
- Integration tests: Generate temporary workbooks from synthetic `decoded_terms.csv` and `tribe_segments.tsv`; inspect `4_WINDOW_AGGREGATES` formulas.
- Lint: Run `git diff --check` on changed code and task artifacts.
- Manual checks: Inspect formulas in the generated workbook for absence of fixed `D21:D23` finale ranges.
