# Task Spec: excel-russian-scene-description

## Metadata
- Task ID: excel-russian-scene-description
- Created: 2026-07-08T09:05:45+00:00
- Repo root: D:\Projects\Projects_Python\Media\neuromedia
- Working directory at init: D:\Projects\Projects_Python\Media\neuromedia

## Guidance sources
- AGENTS.md
- CLAUDE.md

## Original task statement
Make Template_3 Excel scene_description use Russian/original transcript text for display when available, without changing the transcript text used by TRIBE scoring, HTML reports, cache settings, or other downstream processing. If Russian/original text is unavailable, keep the existing safe fallback to the selected transcript text.

## Acceptance criteria
- AC1: Template_3 Excel `scene_description` uses Russian/original transcript text when the selected transcript artifact has an `original_text` column and the run's corrected `text` is not Russian.
- AC2: When the selected transcript artifact is already targeted to Russian (`target_language=ru`) and has populated `text`, Template_3 may use the corrected Russian `text` column.
- AC3: The change is scoped to Template_3 Excel display; TRIBE word events, scoring inputs, HTML transcript display, cache metadata, and transcript files are not changed.
- AC4: If no Russian/original display column is available, Template_3 falls back to the existing selected transcript text column.
- AC5: Generated Excel workbooks preserve Russian UTF-8 text in `1_RAW_CORRELATIONS!C*` and `2_FRAME_MARKUP` continues to reference those raw cells.
- AC6: Focused checks prove syntax, text-column selection, workbook generation, and diff hygiene.

## Constraints
- Preserve UTF-8 encoding for all touched files.
- Keep the change focused in Template_3 report generation.
- Do not rerun transcription or alter generated user `.xlsx` files.
- Do not change the user's target-language setting or the model input text.

## Non-goals
- Do not translate English-only transcript artifacts back to Russian.
- Do not change HTML report transcript language.
- Do not change TRIBE scoring, segmentation, or cache invalidation rules.
- Do not evaluate Excel formulas in desktop Excel/LibreOffice.

## Verification plan
- Build: Run `python -m py_compile template3_report.py marketing_report.py`.
- Unit tests: Exercise the new Template_3 text-column chooser for target `en` with `original_text`, target `ru`, and missing original text.
- Integration tests: Generate synthetic Template_3 workbooks from transcript TSVs where `text` is English and `original_text` is Russian, then inspect `1_RAW_CORRELATIONS!C*`.
- Fallback tests: Generate with only `text` and confirm the existing selected text is used.
- Lint: Run `git diff --check` on changed code and task artifacts.
- Manual checks: Confirm no callers or transcript-generation code paths were changed for TRIBE/HTML.
