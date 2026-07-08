# Task Spec: remove-red-workbook-highlights

## Metadata
- Task ID: remove-red-workbook-highlights
- Created: 2026-07-08T11:26:45+00:00
- Repo root: D:\Projects\Projects_Python\Media\neuromedia
- Working directory at init: D:\Projects\Projects_Python\Media\neuromedia

## Guidance sources
- AGENTS.md
- CLAUDE.md

## Original task statement
Remove red cell highlighting from generated Template_3 Excel reports while preserving non-red structural header fills. Do not edit the template workbook; apply the cleanup during report generation and verify generated workbooks contain no solid red fills.

## Acceptance criteria
- AC1: Generated Template_3 workbooks contain no cells with solid red fill/highlight.
- AC2: Non-red structural fills, such as blue/green header backgrounds, are preserved.
- AC3: The source `Template_3_with_frames.xlsx` file is not edited; cleanup happens only during generated workbook creation.
- AC4: Existing report formulas, values, images, row fitting, and transcript/scoring logic remain unchanged except for red fill removal.
- AC5: Focused checks prove Python syntax, red-fill detection/removal, generated workbook styling, and diff hygiene.

## Constraints
- Preserve UTF-8 encoding.
- Keep the change focused in Template_3 workbook generation.
- Do not modify existing user-generated `.xlsx` files.
- Do not remove borders, fonts, alignment, or non-red fills.

## Non-goals
- Do not redesign workbook colors broadly.
- Do not change manual markup semantics or LOGO formulas.
- Do not run Excel/LibreOffice formula recalculation.

## Verification plan
- Build: Run `python -m py_compile template3_report.py`.
- Unit tests: Exercise the red-fill cleanup helper against synthetic red and non-red filled cells.
- Integration tests: Generate a Template_3 workbook and inspect every worksheet for solid red fills while confirming at least one non-red header fill remains.
- Lint: Run `git diff --check` on changed code and task artifacts.
- Manual checks: Inspect the template workbook separately to confirm the source template still contains red fills and was not edited.
