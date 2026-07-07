# Evidence Bundle: safe-gradio-url-save-after-mount

## Summary
- Overall status: PASS
- Last updated: 2026-07-07T13:40:00+00:00

## Acceptance criteria evidence

### AC1
- Status: PASS
- Proof:
  - `save_gradio_urls()` checks `is_active_mount(Path("/content/drive"))` before constructing/writing the Drive log path.
  - See `.agent/tasks/safe-gradio-url-save-after-mount/raw/test-unit.txt`.
- Gaps:
  - None.

### AC2
- Status: PASS
- Proof:
  - `save_gradio_urls()` writes to `PROJECT_DIR / "gradio_url.txt"` before Drive handling.
  - See `.agent/tasks/safe-gradio-url-save-after-mount/raw/test-unit.txt`.
- Gaps:
  - None.

### AC3
- Status: PASS
- Proof:
  - The Drive URL log path is still present after the active mount guard.
  - See `.agent/tasks/safe-gradio-url-save-after-mount/raw/test-integration.txt`.
- Gaps:
  - Live Drive write was not run locally.

### AC4
- Status: PASS
- Proof:
  - `python -m json.tool run_surface_decoder_colab.ipynb` succeeded.
  - See `.agent/tasks/safe-gradio-url-save-after-mount/raw/test-integration.txt`.
- Gaps:
  - None.

### AC5
- Status: PASS
- Proof:
  - Final response will explain that the fix prevents local files from being created in `/content/drive` before mount.
- Gaps:
  - None.

## Commands run
- `python -m json.tool run_surface_decoder_colab.ipynb > $null; if ($LASTEXITCODE -eq 0) { 'notebook json ok' }`
- `rg -n 'local_path = PROJECT_DIR|drive_mount = Path|if not is_active_mount\(drive_mount\)|drive_path = Path\(DEFAULT_ROOT_DIR\)|Google Drive is not mounted; skipped Drive URL log' run_surface_decoder_colab.ipynb`
- `$text = Get-Content -LiteralPath run_surface_decoder_colab.ipynb -Encoding UTF8 -Raw; ...`
- `git diff --check -- run_surface_decoder_colab.ipynb .agent\tasks\safe-gradio-url-save-after-mount\spec.md`
- `python .agents\skills\repo-task-proof-loop\scripts\task_loop.py validate --task-id safe-gradio-url-save-after-mount`

## Commands for fresh verifier
- `python -m json.tool run_surface_decoder_colab.ipynb > $null; if ($LASTEXITCODE -eq 0) { 'notebook json ok' }`
- `rg -n 'local_path = PROJECT_DIR|drive_mount = Path|if not is_active_mount\(drive_mount\)|drive_path = Path\(DEFAULT_ROOT_DIR\)|Google Drive is not mounted; skipped Drive URL log' run_surface_decoder_colab.ipynb`
- `$text = Get-Content -LiteralPath run_surface_decoder_colab.ipynb -Encoding UTF8 -Raw; if ($text -notmatch 'local_path = PROJECT_DIR / \\"gradio_url\\.txt\\"') { throw 'missing local_path' }; if ($text -notmatch 'if not is_active_mount\\(drive_mount\\):') { throw 'missing mount guard' }; if ($text.IndexOf('local_path = PROJECT_DIR') -ge $text.IndexOf('drive_path = Path(DEFAULT_ROOT_DIR)')) { throw 'wrong order' }; 'url save source ok'`
- `git diff --check -- run_surface_decoder_colab.ipynb .agent\tasks\safe-gradio-url-save-after-mount\spec.md`
- `python .agents\skills\repo-task-proof-loop\scripts\task_loop.py validate --task-id safe-gradio-url-save-after-mount`

## Raw artifacts
- `.agent/tasks/safe-gradio-url-save-after-mount/raw/build.txt`
- `.agent/tasks/safe-gradio-url-save-after-mount/raw/test-unit.txt`
- `.agent/tasks/safe-gradio-url-save-after-mount/raw/test-integration.txt`
- `.agent/tasks/safe-gradio-url-save-after-mount/raw/lint.txt`
- `.agent/tasks/safe-gradio-url-save-after-mount/raw/screenshot-1.png`

## Changed files
- `run_surface_decoder_colab.ipynb`
- `.agent/tasks/safe-gradio-url-save-after-mount/spec.md`
- `.agent/tasks/safe-gradio-url-save-after-mount/evidence.md`
- `.agent/tasks/safe-gradio-url-save-after-mount/evidence.json`
- `.agent/tasks/safe-gradio-url-save-after-mount/raw/build.txt`
- `.agent/tasks/safe-gradio-url-save-after-mount/raw/test-unit.txt`
- `.agent/tasks/safe-gradio-url-save-after-mount/raw/test-integration.txt`
- `.agent/tasks/safe-gradio-url-save-after-mount/raw/lint.txt`

## Known gaps
- Live Colab Drive mount behavior was not rerun from this local environment.
