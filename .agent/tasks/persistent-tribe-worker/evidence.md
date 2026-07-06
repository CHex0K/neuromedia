# Evidence: persistent-tribe-worker

## What changed
- `tribe_nimare_interpreter.py`: split `run_tribe_v2` into two importable seams —
  `load_tribe_model(checkpoint, cache_dir, device)` and
  `process_input_with_model(model, input_path, ...)`. `run_tribe_v2` now delegates
  to both, so the one-shot CLI behavior is unchanged.
- `tribe_worker.py` (new): a persistent worker that loads the TRIBE checkpoint
  once, then processes line-delimited JSON jobs from stdin, emitting one
  sentinel-prefixed (`@@TRIBE_WORKER_RESULT@@`) JSON result per job. `serve()`
  takes injectable `load_model`/`process_job` callables (test seam); `main()`
  wires the real ones from `tribe_nimare_interpreter`.
- `run_surface_decoder_colab.ipynb`: added `TribeWorkerSession` (Popen + reader
  thread + sentinel parsing, mirroring `run_command_stream`), a per-run session
  created once before the file loop, lazy start on the first video that needs
  TRIBE, restart-on-crash with a bounded counter (`TRIBE_WORKER_MAX_RESTARTS`),
  a `use_persistent_worker` UI checkbox (default ON) that falls back to the
  original per-video subprocess path, and a `shutdown()` after the loop.

## How the GPU-idle problem is addressed
Previously each video launched a fresh `tribe_nimare_interpreter.py` subprocess,
so `TribeModel.from_pretrained` ran once per video and VRAM was freed on exit.
Now one worker process loads the checkpoint once per "Run analysis" and reuses it
across all videos, removing the per-video reload and the associated GPU idle.

## Verification (current code, current results)
See `raw/verification-output.txt`. All commands exit 0:
- `python -m py_compile tribe_nimare_interpreter.py tribe_worker.py` → OK.
- `raw/test_worker_protocol.py` (StringIO seams): model loaded exactly once for 3
  jobs; a raising job yields `status="error"` and the loop continues; a fatal load
  yields `status="fatal"` and returns 1; an invalid JSON line is isolated.
- `raw/test_worker_subprocess.py` (real Popen over OS pipes, stub model):
  statuses `['ready','ok','error','ok']`, clean shutdown (returncode 0). Proves
  the sentinel protocol survives a real process boundary.
- Notebook static/syntax checks: cell compiles, JSON valid, worker dispatch +
  legacy fallback both present, `use_persistent_worker` param and
  `persistent_worker_input` are positionally consistent between the
  `analyze_video` signature and the Gradio `inputs=[...]` list.

## Not executed locally (requires Colab GPU + tribev2 checkpoint)
- Full end-to-end batch through the real worker (AC2 runtime, AC4 real
  crash/OOM recovery). Heavy deps (torch, tribev2, nibabel, ...) are not
  installed in this environment; `tribe_nimare_interpreter.py --help` fails only
  on `import nibabel`, which is pre-existing and unrelated to this change.
- Manual follow-ups are listed in `evidence.json`.

## Scope / non-goals
- GigaAM model persistence across videos is intentionally out of scope for v1
  (follow-up); only the TRIBE checkpoint is kept resident.
- No changes to decode/report/reference-build stages or numerics.
- The change is reversible at runtime via the `use_persistent_worker` toggle.
