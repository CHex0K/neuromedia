# Task Spec: xlsx-extended-row-styles

## Metadata
- Task ID: xlsx-extended-row-styles
- Created: 2026-07-08T14:25:33+00:00
- Repo root: D:\Projects\Projects_Python\Media\neuromedia
- Working directory at init: D:\Projects\Projects_Python\Media\neuromedia

## Guidance sources
- AGENTS.md
- CLAUDE.md

## Original task statement
Fix Template_3 XLSX generation so rows added beyond the 20-row template keep the same visual formatting as template data rows across relevant sheets. Preserve formulas, values, red-highlight removal, and existing transcript behavior.

## Acceptance criteria
- AC1: Generated Template_3 XLSX files with more than 20 segment rows copy visual row/cell formatting from the template data row to every added row on `1_RAW_CORRELATIONS`, `2_FRAME_MARKUP`, and `3_INDEX_SCORES`.
- AC2: Existing formula/value behavior is preserved: added formula-sheet rows still receive translated formulas/static values, and raw rows still receive generated frame ids, seconds, scene descriptions, and term scores.
- AC3: Existing cleanup behavior is preserved, including removal of red fills and clean manual markup defaults.
- AC4: Reports with 20 or fewer rows keep the existing behavior.
- AC5: Focused checks prove syntax, generated workbook style parity for row F21+, formula preservation, and diff hygiene.

## Constraints
- Use UTF-8 for all text artifacts.
- Keep the implementation scoped to Template_3 XLSX generation.
- Do not change report paths, TRIBE processing, transcript selection, or scoring logic.
- Do not reintroduce red highlight fills into generated workbooks.

## Non-goals
- Do not redesign the workbook template.
- Do not change HTML report generation.
- Do not modify already-generated XLSX files; users must regenerate reports.

## Verification plan
- Build: `python -m py_compile template3_report.py`.
- Unit tests: direct helper check that style copying preserves border/fill/number format/alignment and row height.
- Integration tests: generate a synthetic 21-row Template_3 workbook and compare row F21 formatting against the template row on raw, markup, and index sheets while checking formulas/values.
- Lint: `git diff --check`.
- Manual checks: inspect diff for small, formatting-only implementation scope.
