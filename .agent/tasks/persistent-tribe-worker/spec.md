# Task Spec: persistent-tribe-worker

## Metadata
- Task ID: persistent-tribe-worker
- Created: 2026-07-06
- Repo root: D:\Projects\Projects_Python\Media\neuromedia

## Original Task Statement
In batch video processing the TRIBE v2 checkpoint is currently loaded and freed once per video, because the notebook launches a fresh `tribe_nimare_interpreter.py` subprocess for every input file. This leaves the GPU idle during model (re)loading and during the CPU-bound stages, and the reload overhead can dominate batches of many short clips. Refactor the batch flow so the TRIBE model is loaded once per run via a long-lived worker process, while preserving the current fault isolation, caching, and logging behavior.

## Context (current behavior)
- Notebook `run_surface_decoder_colab.ipynb` batch loop builds a per-file `tribe_cmd` and runs it with `run_command_stream` -> `subprocess.Popen`.
- `tribe_nimare_interpreter.py` `main()` -> `run_tribe_v2()` calls `TribeModel.from_pretrained(checkpoint, device=device, ...)` on every invocation (tribe_nimare_interpreter.py:229), runs `model.predict` once, then the process exits and VRAM is freed.
- Per-file `try/except` in the notebook records failures to `batch_failures.json` and continues (one bad video does not abort the batch).
- TRIBE `.npy` outputs are cached per input under the stem; the notebook skips TRIBE when a valid cache exists and transcription settings match.

## Acceptance Criteria
- AC1: Add a new `tribe_worker.py` that imports the model-load and per-input processing seams from `tribe_nimare_interpreter.py`, loads the TRIBE checkpoint exactly once, then processes multiple jobs read as line-delimited JSON from stdin, emitting exactly one structured JSON result line per job (marked with a sentinel prefix). Each job is the equivalent of the current `--tribe-only` run for one input and writes the same `.npy` artifacts to the job's output dir. (Decision: standalone worker file, not a subcommand.)
- AC2: The notebook drives the TRIBE step through a single persistent worker session per "Run analysis" for BOTH single-file and batch runs (job list of length 1 or N), so `TribeModel.from_pretrained` runs once per run instead of once per video. Downstream decode/report inputs and the produced `.npy` files are structurally identical to the current pipeline. (Decision: one code path via worker; no separate single-file subprocess branch.)
- AC3: Per-job fault isolation is preserved: a Python-level error while processing one video is returned as an error result (with `stage`, `error`, `traceback`) and the worker stays alive and processes subsequent jobs without reloading the model. The notebook records such failures into `batch_failures.json` and continues.
- AC4: Hard-crash recovery: if the worker process exits unexpectedly (e.g. CUDA OOM / segfault) mid-job, the notebook marks the current video failed, restarts the worker (reloading the model), and continues with the remaining videos. A bounded restart limit prevents an infinite restart loop when the model itself cannot load.
- AC5: TRIBE cache reuse still takes precedence and is checked before dispatch: videos whose valid `.npy` cache and transcription settings already match are skipped without sending a job, and the worker is started lazily only once at least one video actually needs TRIBE.
- AC6: A UI/config toggle selects between the persistent worker (default ON) and the legacy per-video subprocess path (OFF). Both paths produce equivalent outputs, providing a safe fallback / A-B comparison.
- AC7: Worker stdout/stderr (TRIBE and GigaAM logs, per-job tracebacks, resource snapshots) continue to stream into `gradio_last_run.log` and the Gradio log panel. Protocol/result lines are separated from human-readable log lines by the sentinel and are not shown as noise.
- AC8: The standalone one-shot CLI (`python tribe_nimare_interpreter.py <video> ...`) keeps working exactly as before; `tribe_worker.py` is additive and imports from it. `tribe_worker.py` lives in the repo so the clone-based Colab runtime picks it up automatically.
- AC9: UTF-8 handling stays explicit, modified Python files keep the `# -*- coding: utf-8 -*-` header, and no API keys are written to logs, result lines, or command-line arguments.

## Constraints
- Reuse `run_tribe_v2` internals: factor out (a) "load model" and (b) "process one input with a preloaded model" into importable functions in `tribe_nimare_interpreter.py`, and have both the one-shot CLI and `tribe_worker.py` call them, rather than duplicating checkpoint-loading or inference code.
- Provide a lightweight test seam so the `serve` loop and protocol can be exercised without a GPU or the real checkpoint (e.g. a stub model-loader / processor selectable via a hidden flag or env var). This is required for AC1/AC3/AC4 verification.
- Keep the decode, report, and reference-build stages unchanged.
- Do not persist OpenRouter / HF secrets to repository files, notebooks, logs, result lines, or CLI args; keep passing them via environment as today.
- The notebook is now the clone-based source of truth; no base64 re-embedding step is required.
- Make the smallest defensible diff; do not restructure unrelated notebook logic.

## Non-Goals
- GigaAM model persistence across videos (separate follow-up; v1 persists only the TRIBE checkpoint).
- Parallelizing CPU stages (avi->mp4 conversion, decode, report) with GPU inference of the next video.
- Multi-GPU execution or batching several videos into one forward pass.
- Any change to TRIBE/decoder numerics, marketing scoring, or report layout.
- Using the persistent worker for standalone CLI usage outside the notebook.

## Verification Plan
- Build: `python -m py_compile tribe_nimare_interpreter.py`; compile the notebook cell source with `compile(...)` and confirm the notebook JSON is valid.
- Protocol/loop unit test (no GPU): drive `serve` mode with the stub processor, feeding two jobs plus one job that raises. Assert: the model loader is invoked exactly once; two/three result lines are emitted with correct `status`; the raising job yields `status="error"` with a traceback and the loop continues to the next job.
- Notebook static checks: assert the worker-session driver exists; the TRIBE cache check still precedes dispatch; the fallback toggle is present and wired; sentinel parsing and restart-on-crash-with-bound logic are present; single-file and batch both route through the same TRIBE dispatch.
- Regression check: `tribe_nimare_interpreter.py --help` still exposes the existing options and the one-shot path is unchanged.
- Integration (best-effort, GPU required, may be manual): run a 2-video batch with one intentionally broken input; expect 1 processed + 1 failed in `batch_failures.json`, a single `from_pretrained` load in the log, and a correct combined report ZIP.

## Rollback
- The AC6 toggle (persistent worker OFF) restores the exact current per-video subprocess behavior without code removal, so the change is reversible at runtime.
