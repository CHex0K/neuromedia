# -*- coding: utf-8 -*-

# Evidence: Batch Continue On Error

## Summary

Implementation changed `run_surface_decoder_colab.ipynb` so folder/batch processing catches per-video exceptions, records failures, continues to the next input, and writes a `batch_failures.json` manifest into the final batch ZIP when at least one video succeeds.

## Acceptance Criteria

AC1. PASS. The per-file body in `analyze_video` is wrapped in `try/except`; in batch mode the exception is recorded and the loop executes `continue`. Static proof: `.agent/tasks/batch-continue-on-error/raw/notebook-static-check.txt`.

AC2. PASS. The exception handler appends `FAILED`, `Failed stage`, and `traceback.format_exc()` to the UI log. Static proof: `run_surface_decoder_colab.ipynb` diff and notebook static check.

AC3. PASS. Batch ZIP creation writes `batch_failures_manifest` to UTF-8 JSON and archives it as `batch_failures.json`. Static proof: `.agent/tasks/batch-continue-on-error/raw/notebook-static-check.txt`.

AC4. PASS. In batch mode, if `processed_reports` is empty after processing all inputs, the code raises `RuntimeError("Batch failed: 0/{total_inputs} videos processed...")` before creating a ZIP. Static proof: notebook static check.

AC5. PASS. The per-video exception handler immediately re-raises when `not batch_mode`, preserving single-file failure behavior. Static proof: notebook static check.

AC6. PASS. `run_surface_decoder_colab.ipynb` parses as JSON and the UI cell containing `analyze_video` compiles successfully. Command proof: notebook static check exited 0.

## Commands

- `git diff --check`
  - Exit code: 0
  - Raw output: `.agent/tasks/batch-continue-on-error/raw/git-diff-check.txt`

- Notebook static check
  - Exit code: 0
  - Raw output: `.agent/tasks/batch-continue-on-error/raw/notebook-static-check.txt`

- `git diff --stat`
  - Exit code: 0
  - Raw output: `.agent/tasks/batch-continue-on-error/raw/git-diff-stat.txt`
