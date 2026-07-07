# Task Spec: restore-direct-batch-input

## Metadata
- Task ID: restore-direct-batch-input
- Created: 2026-07-07T11:30:21+00:00
- Repo root: D:\Projects\Projects_Python\Media\neuromedia
- Working directory at init: D:\Projects\Projects_Python\Media\neuromedia

## Guidance sources
- AGENTS.md
- CLAUDE.md

## Original task statement
Revert the previous recursive batch folder handling in run_surface_decoder_colab.ipynb. The default input path should be /content/drive/MyDrive/neuromedia/input, not input/videos. Batch processing should not search nested folders; it should process direct .mp4/.avi files in the selected folder. Explain how current mass video processing works.

## Acceptance criteria
- AC1: `run_surface_decoder_colab.ipynb` uses `/content/drive/MyDrive/neuromedia/input` as the default input path.
- AC2: Batch folder mode does not recurse into nested folders; it scans only direct child files of the selected folder.
- AC3: Batch folder mode accepts only direct `.mp4` and `.avi` files and keeps the existing behavior of preferring `.mp4` over same-stem `.avi`.
- AC4: User-visible batch messages match direct-folder processing and do not claim recursive search.
- AC5: The notebook remains valid JSON and proof-loop validation reports `PASS`.
- AC6: The final response explains how mass video processing works, including the direct-folder limitation.

## Constraints
- Keep all task artifacts under `.agent/tasks/restore-direct-batch-input/`.
- Preserve UTF-8 encoding for all edited files.
- Use a minimal patch; do not refactor unrelated notebook logic.
- Do not use destructive git commands; only revert the previous changes owned by this assistant.

## Non-goals
- Do not add recursive nested folder processing.
- Do not run the full Colab pipeline locally.
- Do not change dependency versions or Google Drive contents.
- Do not remove previous task artifact folders.

## Verification plan
- Build: Parse `run_surface_decoder_colab.ipynb` as JSON.
- Unit tests: Simulate direct-folder batch discovery with a temporary directory containing direct and nested video files.
- Integration tests: Not run locally because Colab and Google Drive mount are external.
- Lint: Run `git diff --check` on the changed notebook and task artifacts.
- Manual checks: Search the notebook for `DEFAULT_INPUT_PATH`, `requested_path.iterdir()`, and absence of `requested_path.rglob("*")`.
