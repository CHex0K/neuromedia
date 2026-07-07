# Task Spec: safe-gradio-url-save-after-mount

## Metadata
- Task ID: safe-gradio-url-save-after-mount
- Created: 2026-07-07T13:31:23+00:00
- Repo root: D:\Projects\Projects_Python\Media\neuromedia
- Working directory at init: D:\Projects\Projects_Python\Media\neuromedia

## Guidance sources
- AGENTS.md
- CLAUDE.md

## Original task statement
Fix run_surface_decoder_colab.ipynb so saving Gradio URL never creates /content/drive/MyDrive before Google Drive is mounted. Save URL locally first, and save to Google Drive only when the Drive mount is already active. Explain why this prevents 'Mountpoint must not already contain files'.

## Acceptance criteria
- AC1: `save_gradio_urls()` never creates `/content/drive/MyDrive` or any Drive subdirectory before Google Drive is actively mounted.
- AC2: Gradio URL is still persisted locally under `/content/neuromedia/gradio_url.txt` so URL output glitches remain recoverable.
- AC3: When Google Drive is already mounted, Gradio URL is also saved to `/content/drive/MyDrive/neuromedia/logs/gradio_url.txt`.
- AC4: `run_surface_decoder_colab.ipynb` remains valid JSON.
- AC5: The final response explains why this prevents `Mountpoint must not already contain files`.

## Constraints
- Keep all task artifacts under `.agent/tasks/safe-gradio-url-save-after-mount/`.
- Preserve UTF-8 encoding.
- Make the smallest safe notebook change.
- Do not change Drive mount semantics outside URL persistence.

## Non-goals
- Do not run the full Colab pipeline locally.
- Do not change dependency versions.
- Do not delete or modify user Google Drive files.
- Do not redesign the Gradio UI.

## Verification plan
- Build: Parse `run_surface_decoder_colab.ipynb` as JSON.
- Unit tests: Static/source checks for local-first saving and active-mount guard before Drive writes.
- Integration tests: Not run locally because Colab Drive mount is external.
- Lint: Run `git diff --check`.
- Manual checks: Inspect `save_gradio_urls()` source and call sites.
