# Task Spec: skip-existing-report-progress

## Metadata
- Task ID: skip-existing-report-progress
- Created: 2026-07-08T16:34:07+00:00
- Repo root: D:\Projects\Projects_Python\Media\neuromedia
- Working directory at init: D:\Projects\Projects_Python\Media\neuromedia

## Guidance sources
- AGENTS.md
- CLAUDE.md

## Original task statement
If a per-video marketing_report_bundle.zip already exists, skip reprocessing that video while still counting it in the Gradio batch progress bar. The skipped report should be treated as a processed report and included in the final batch ZIP. Preserve current report path generation and existing TRIBE cache behavior.

## Acceptance criteria
- AC1: When a non-empty per-video `marketing_report_bundle.zip` already exists at the currently generated report path, that video skips TRIBE execution, surface decoding, and report rebuilding.
- AC2: A skipped existing report is treated as processed: it is appended to `processed_reports`, exposed as `final_report_file`, and included in the final batch ZIP.
- AC3: Progress accounting still advances by one input for skipped videos through the existing per-video `finally` progress update.
- AC4: Existing behavior is preserved when no report ZIP exists: TRIBE cache checks, decoder execution, report generation, failure handling, and temporary AVI cleanup remain on the current path.
- AC5: Focused checks prove notebook syntax, skip branch placement before TRIBE cache work, processed-report bookkeeping, and diff hygiene.

## Constraints
- Use UTF-8 for all task artifacts.
- Keep the implementation scoped to `run_surface_decoder_colab.ipynb`.
- Preserve current report path generation and current TRIBE cache behavior.
- Treat only an existing non-empty ZIP as a completed downloadable report.

## Non-goals
- Do not add a UI checkbox or setting.
- Do not change output directory structure.
- Do not change batch discovery, recursive folder behavior, or report content.
- Do not modify existing report files.

## Verification plan
- Build: compile Python code cells from `run_surface_decoder_colab.ipynb`.
- Unit tests: static source check that the existing-report skip branch is before TRIBE cache checking, adds to `processed_reports`, sets `final_report_file`, yields a skip snapshot, and continues into the existing `finally`.
- Integration tests: source-level simulation or structural check proving skipped reports are included in `processed_reports` and therefore batch ZIP creation.
- Lint: `git diff --check`.
- Manual checks: inspect diff for minimal scope and unchanged non-skip pipeline.
