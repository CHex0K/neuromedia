# Task Spec: batch-input-videos-discovery

## Metadata
- Task ID: batch-input-videos-discovery
- Created: 2026-07-07T11:18:49+00:00
- Repo root: D:\Projects\Projects_Python\Media\neuromedia
- Working directory at init: D:\Projects\Projects_Python\Media\neuromedia

## Guidance sources
- AGENTS.md
- CLAUDE.md

## Original task statement
Investigate and fix why Colab/Gradio batch launch reports no Google Drive video files even though Drive web UI shows .avi files under neuromedia/input/videos. Use repo-task-proof-loop, identify whether the notebook only scans direct children, and make the smallest safe notebook change so batch folder input can discover nested videos or guide the user correctly.

## Acceptance criteria
- AC1: The current failure mode is explained from repository code: batch folder input scans only direct children and therefore misses videos under `input/videos` when the selected folder is `input`.
- AC2: `run_surface_decoder_colab.ipynb` is updated so batch folder input discovers `.mp4` and `.avi` videos recursively under the selected folder.
- AC3: The existing AVI/MP4 duplicate handling remains in place and works for nested files by comparing stems within the same parent folder.
- AC4: User-visible batch messaging no longer says only "MP4 videos found" when AVI files are accepted, and the no-files error mentions recursive search.
- AC5: The notebook remains valid JSON and the proof-loop artifacts validate with an overall `PASS`.

## Constraints
- Keep all task artifacts under `.agent/tasks/batch-input-videos-discovery/`.
- Preserve UTF-8 encoding for all edited text and notebook files.
- Make the smallest safe change in `run_surface_decoder_colab.ipynb`; do not refactor unrelated notebook logic.
- Do not require live access to the user's Google Drive or Colab runtime for local verification.

## Non-goals
- Do not run the full Colab pipeline locally.
- Do not change dependency versions.
- Do not modify Google Drive contents.
- Do not redesign the Gradio UI beyond the small path/message fix needed for this bug.

## Verification plan
- Build: Parse `run_surface_decoder_colab.ipynb` as JSON.
- Unit tests: Extract the relevant notebook source and verify recursive discovery/deduplication behavior with a temporary nested directory.
- Integration tests: Not run locally because Colab Drive mount is external; use static/path tests instead.
- Lint: Static search for old direct-only `requested_path.iterdir()` batch scan and old "MP4 videos found" message.
- Manual checks: Inspect relevant notebook lines before and after patch.
