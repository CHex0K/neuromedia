# Evidence Bundle: batch-input-videos-discovery

## Summary
- Overall status: PASS
- Last updated: 2026-07-07T11:35:00+00:00

## Acceptance criteria evidence

### AC1
- Status: PASS
- Proof:
  - Pre-patch notebook code used `requested_path.iterdir()` in batch mode, which scans only direct children.
  - User screenshot shows files under `input/videos`, so choosing the parent `input` folder would report no videos even though nested files exist.
  - See `.agent/tasks/batch-input-videos-discovery/raw/build.txt`.
- Gaps:
  - None.

### AC2
- Status: PASS
- Proof:
  - `run_surface_decoder_colab.ipynb` now uses `requested_path.rglob("*")` for batch discovery.
  - Static search confirms the changed line.
  - See `.agent/tasks/batch-input-videos-discovery/raw/test-integration.txt`.
- Gaps:
  - None.

### AC3
- Status: PASS
- Proof:
  - Deduplication now uses `_mp4_keys = {(p.parent, p.stem) ...}`.
  - Local test proves `videos/a.avi` is skipped when `videos/a.mp4` exists, while `other/a.avi` is retained.
  - See `.agent/tasks/batch-input-videos-discovery/raw/test-unit.txt`.
- Gaps:
  - None.

### AC4
- Status: PASS
- Proof:
  - Error text now says `No .mp4/.avi files found recursively in input directory`.
  - UI text now says `Videos found`, not `MP4 videos found`.
  - Log text now says files were found recursively.
  - See `.agent/tasks/batch-input-videos-discovery/raw/test-integration.txt`.
- Gaps:
  - None.

### AC5
- Status: PASS
- Proof:
  - `python -m json.tool run_surface_decoder_colab.ipynb` completed successfully.
  - `git diff --check` completed successfully.
  - Proof-loop validation completed successfully.
  - See `.agent/tasks/batch-input-videos-discovery/raw/test-integration.txt` and `.agent/tasks/batch-input-videos-discovery/raw/lint.txt`.
- Gaps:
  - None.

## Commands run
- `python -m json.tool run_surface_decoder_colab.ipynb > $null; if ($LASTEXITCODE -eq 0) { 'notebook json ok' }`
- `rg -n 'DEFAULT_INPUT_PATH|requested_path\.rglob|requested_path\.iterdir|_mp4_keys|No \.mp4/\.avi files found|Videos found|recursively for sequential' run_surface_decoder_colab.ipynb`
- `python -c "from pathlib import Path; import tempfile; ..."`
- `git diff --check -- run_surface_decoder_colab.ipynb .agent\tasks\batch-input-videos-discovery\spec.md`
- `python .agents\skills\repo-task-proof-loop\scripts\task_loop.py validate --task-id batch-input-videos-discovery`

## Commands for fresh verifier
- `python -m json.tool run_surface_decoder_colab.ipynb > $null; if ($LASTEXITCODE -eq 0) { 'notebook json ok' }`
- `rg -n 'DEFAULT_INPUT_PATH|requested_path\.rglob|requested_path\.iterdir|_mp4_keys|No \.mp4/\.avi files found|Videos found|recursively for sequential' run_surface_decoder_colab.ipynb`
- `python -c "from pathlib import Path; import tempfile; exts={'.mp4','.avi'}; d=Path(tempfile.mkdtemp()); (d/'videos').mkdir(); (d/'other').mkdir(); (d/'videos'/'a.avi').write_text('', encoding='utf-8'); (d/'videos'/'a.mp4').write_text('', encoding='utf-8'); (d/'other'/'a.avi').write_text('', encoding='utf-8'); (d/'videos'/'b.avi').write_text('', encoding='utf-8'); files=sorted(p for p in d.rglob('*') if p.is_file() and p.suffix.lower() in exts); keys={(p.parent,p.stem) for p in files if p.suffix.lower()=='.mp4'}; files=[p for p in files if not (p.suffix.lower()=='.avi' and (p.parent,p.stem) in keys)]; result=[p.relative_to(d).as_posix() for p in files]; print(result); assert result == ['other/a.avi', 'videos/a.mp4', 'videos/b.avi']"`
- `git diff --check -- run_surface_decoder_colab.ipynb .agent\tasks\batch-input-videos-discovery\spec.md`
- `python .agents\skills\repo-task-proof-loop\scripts\task_loop.py validate --task-id batch-input-videos-discovery`

## Raw artifacts
- `.agent/tasks/batch-input-videos-discovery/raw/build.txt`
- `.agent/tasks/batch-input-videos-discovery/raw/test-unit.txt`
- `.agent/tasks/batch-input-videos-discovery/raw/test-integration.txt`
- `.agent/tasks/batch-input-videos-discovery/raw/lint.txt`
- `.agent/tasks/batch-input-videos-discovery/raw/screenshot-1.png`

## Changed files
- `run_surface_decoder_colab.ipynb`
- `.agent/tasks/batch-input-videos-discovery/spec.md`
- `.agent/tasks/batch-input-videos-discovery/evidence.md`
- `.agent/tasks/batch-input-videos-discovery/evidence.json`
- `.agent/tasks/batch-input-videos-discovery/raw/build.txt`
- `.agent/tasks/batch-input-videos-discovery/raw/test-unit.txt`
- `.agent/tasks/batch-input-videos-discovery/raw/test-integration.txt`
- `.agent/tasks/batch-input-videos-discovery/raw/lint.txt`

## Known gaps
- Live Colab Google Drive mount behavior was not rerun from this local environment.
