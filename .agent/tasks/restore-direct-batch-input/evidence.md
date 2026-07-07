# Evidence Bundle: restore-direct-batch-input

## Summary
- Overall status: PASS
- Last updated: 2026-07-07T11:45:00+00:00

## Acceptance criteria evidence

### AC1
- Status: PASS
- Proof:
  - Static search shows `DEFAULT_INPUT_PATH = "/content/drive/MyDrive/neuromedia/input"`.
  - See `.agent/tasks/restore-direct-batch-input/raw/test-integration.txt`.
- Gaps:
  - None.

### AC2
- Status: PASS
- Proof:
  - Static search shows `requested_path.iterdir()` and no recursive `requested_path.rglob`.
  - Unit test confirms nested files are ignored.
  - See `.agent/tasks/restore-direct-batch-input/raw/test-unit.txt`.
- Gaps:
  - None.

### AC3
- Status: PASS
- Proof:
  - Static search shows `_mp4_stems`.
  - Unit test confirms same-stem `.avi` is skipped when `.mp4` exists directly in the selected folder.
  - See `.agent/tasks/restore-direct-batch-input/raw/test-unit.txt`.
- Gaps:
  - None.

### AC4
- Status: PASS
- Proof:
  - Static search confirms the no-files message no longer says recursive.
  - Static search confirms no `recursively for sequential` log text remains.
  - The old direct-folder `MP4 videos found` text is restored.
  - See `.agent/tasks/restore-direct-batch-input/raw/test-integration.txt`.
- Gaps:
  - None.

### AC5
- Status: PASS
- Proof:
  - Notebook JSON parse succeeded.
  - `git diff --check` succeeded.
  - Proof-loop validation succeeded.
  - See `.agent/tasks/restore-direct-batch-input/raw/test-integration.txt` and `.agent/tasks/restore-direct-batch-input/raw/lint.txt`.
- Gaps:
  - None.

### AC6
- Status: PASS
- Proof:
  - Final response will explain direct-folder mass processing and its limitation.
- Gaps:
  - None.

## Commands run
- `python -m json.tool run_surface_decoder_colab.ipynb > $null; if ($LASTEXITCODE -eq 0) { 'notebook json ok' }`
- `rg -n 'DEFAULT_INPUT_PATH|requested_path\.iterdir|requested_path\.rglob|_mp4_stems|_mp4_keys|No \.mp4/\.avi files found|MP4 videos found|recursively for sequential' run_surface_decoder_colab.ipynb`
- `python -c "from pathlib import Path; import tempfile; ..."`
- `git diff -- run_surface_decoder_colab.ipynb`
- `git diff --check -- run_surface_decoder_colab.ipynb .agent\tasks\restore-direct-batch-input\spec.md`

## Commands for fresh verifier
- `python -m json.tool run_surface_decoder_colab.ipynb > $null; if ($LASTEXITCODE -eq 0) { 'notebook json ok' }`
- `rg -n 'DEFAULT_INPUT_PATH|requested_path\.iterdir|requested_path\.rglob|_mp4_stems|_mp4_keys|No \.mp4/\.avi files found|MP4 videos found|recursively for sequential' run_surface_decoder_colab.ipynb`
- `python -c "from pathlib import Path; import tempfile; exts={'.mp4','.avi'}; d=Path(tempfile.mkdtemp()); (d/'nested').mkdir(); (d/'a.avi').write_text('', encoding='utf-8'); (d/'a.mp4').write_text('', encoding='utf-8'); (d/'b.avi').write_text('', encoding='utf-8'); (d/'nested'/'c.avi').write_text('', encoding='utf-8'); files=sorted(p for p in d.iterdir() if p.is_file() and p.suffix.lower() in exts); stems={p.stem for p in files if p.suffix.lower()=='.mp4'}; files=[p for p in files if not (p.suffix.lower()=='.avi' and p.stem in stems)]; result=[p.relative_to(d).as_posix() for p in files]; print(result); assert result == ['a.mp4', 'b.avi']"`
- `git diff --check -- run_surface_decoder_colab.ipynb .agent\tasks\restore-direct-batch-input\spec.md`
- `python .agents\skills\repo-task-proof-loop\scripts\task_loop.py validate --task-id restore-direct-batch-input`

## Raw artifacts
- `.agent/tasks/restore-direct-batch-input/raw/build.txt`
- `.agent/tasks/restore-direct-batch-input/raw/test-unit.txt`
- `.agent/tasks/restore-direct-batch-input/raw/test-integration.txt`
- `.agent/tasks/restore-direct-batch-input/raw/lint.txt`
- `.agent/tasks/restore-direct-batch-input/raw/screenshot-1.png`

## Changed files
- `run_surface_decoder_colab.ipynb`
- `.agent/tasks/restore-direct-batch-input/spec.md`
- `.agent/tasks/restore-direct-batch-input/evidence.md`
- `.agent/tasks/restore-direct-batch-input/evidence.json`
- `.agent/tasks/restore-direct-batch-input/raw/build.txt`
- `.agent/tasks/restore-direct-batch-input/raw/test-unit.txt`
- `.agent/tasks/restore-direct-batch-input/raw/test-integration.txt`
- `.agent/tasks/restore-direct-batch-input/raw/lint.txt`

## Known gaps
- Live Colab Google Drive batch run was not executed from this local environment.
