# Task Spec: blank-scene-description-no-zero

## Metadata
- Task ID: blank-scene-description-no-zero
- Created: 2026-07-08T11:16:24+00:00
- Repo root: D:\Projects\Projects_Python\Media\neuromedia
- Working directory at init: D:\Projects\Projects_Python\Media\neuromedia

## Guidance sources
- AGENTS.md
- CLAUDE.md

## Original task statement
Fix Template_3 Excel report so rows without transcript text display a blank scene_description in 2_FRAME_MARKUP instead of Excel's 0 from direct blank-cell references. Keep rows with transcript text unchanged and do not alter scoring or transcript generation.

## Acceptance criteria
- AC1: Generated Template_3 workbooks rewrite `2_FRAME_MARKUP` `scene_description` formulas so blank raw transcript cells render as blank strings, not Excel `0`.
- AC2: Rows with transcript text still display the transcript text by referencing `1_RAW_CORRELATIONS!C*`.
- AC3: The change applies to every generated data row, including reports with fewer or more than the template's default 20 rows.
- AC4: Transcript generation, scoring, frame images, markup flags, and unrelated workbook formulas are unchanged.
- AC5: Focused checks prove Python syntax, generated formula structure, workbook generation, and diff hygiene.

## Constraints
- Preserve UTF-8 encoding.
- Keep the change focused in Template_3 report generation.
- Do not edit `Template_3_with_frames.xlsx`.
- Do not modify existing user-generated `.xlsx` files.

## Non-goals
- Do not rerun TRIBE/transcription.
- Do not change how `scene_description` text is selected or aligned.
- Do not evaluate formulas in desktop Excel/LibreOffice.

## Verification plan
- Build: Run `python -m py_compile template3_report.py`.
- Unit tests: Verify the formula rewriter emits `IF(raw="","",raw)` formulas for the expected rows.
- Integration tests: Generate synthetic Template_3 workbooks with blank and populated transcript segments, then inspect `2_FRAME_MARKUP!C*` formulas and `1_RAW_CORRELATIONS!C*` values.
- Lint: Run `git diff --check` on changed code and task artifacts.
- Manual checks: Confirm the formula targets only `2_FRAME_MARKUP` scene-description cells.
