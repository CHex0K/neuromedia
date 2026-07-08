# Task Spec: xlsx-overlap-scene-transcript

## Metadata
- Task ID: xlsx-overlap-scene-transcript
- Created: 2026-07-08T13:04:12+00:00
- Repo root: D:\Projects\Projects_Python\Media\neuromedia
- Working directory at init: D:\Projects\Projects_Python\Media\neuromedia

## Guidance sources
- AGENTS.md
- CLAUDE.md

## Original task statement
Make Template_3 XLSX scene_description alignment use the same transcript overlap rule as the HTML report: include transcript rows whose start/end interval overlaps the segment window, instead of only rows whose start timestamp falls inside the segment. Preserve existing Excel display text-column selection and fallbacks.

## Acceptance criteria
- AC1: Template_3 XLSX `scene_description` includes transcript rows whose time interval overlaps the segment window, matching the HTML report rule.
- AC2: Transcript rows that start before a segment but end inside/after it are included in that segment, so boundary-crossing words may appear in adjacent XLSX rows like HTML.
- AC3: Existing display text-column selection is preserved, including Russian/source `original_text` preference for XLSX when available.
- AC4: If transcript end/duration columns are unavailable, XLSX falls back to the previous start-based behavior safely.
- AC5: Focused checks prove Python syntax, overlap selection, generated workbook values, and diff hygiene.

## Constraints
- Preserve UTF-8 encoding.
- Keep the change focused in Template_3 XLSX scene-description alignment.
- Do not alter HTML behavior, transcript generation, TRIBE scoring, or workbook formulas unrelated to scene descriptions.

## Non-goals
- Do not deduplicate transcript words across segment rows.
- Do not change segment timing or TRIBE prediction count.
- Do not modify existing generated `.xlsx` files.

## Verification plan
- Build: Run `python -m py_compile template3_report.py`.
- Unit tests: Exercise segment-row assembly with a word crossing a 1-second boundary.
- Integration tests: Generate a Template_3 workbook where a word spans `0.8-1.2` and confirm it appears in both adjacent rows.
- Fallback tests: Generate with only `start` and no end/duration and confirm start-based behavior remains.
- Lint: Run `git diff --check` on changed code and task artifacts.
