# -*- coding: utf-8 -*-
"""Persistent TRIBE v2 worker.

The notebook batch flow used to launch a fresh ``tribe_nimare_interpreter.py``
subprocess per video, which reloaded the TRIBE checkpoint into VRAM every time.
This worker instead loads the checkpoint **once** and then processes many jobs
read as line-delimited JSON from stdin, emitting one structured result line per
job. It is the equivalent of running ``tribe_nimare_interpreter.py <video>
--tribe-only`` repeatedly, but without paying the model-load cost each time.

Protocol (all on stdout, one JSON object per line, prefixed with RESULT_PREFIX):
    startup ready:  {"status": "ready"}
    startup fatal:  {"status": "fatal", "error": ..., "traceback": ...}
    job ok:         {"status": "ok", "input": ..., "prediction_path": ...,
                     "activity_path": ..., "segments_path": ...}
    job error:      {"status": "error", "input": ..., "stage": ...,
                     "error": ..., "traceback": ...}

Any stdout line WITHOUT the prefix (e.g. TRIBE's own progress prints) is a plain
log line and must be ignored by the protocol parser. Secrets are never placed on
the command line or in result lines; they are inherited from the environment
(OPENROUTER_API_KEY, HF_TOKEN) exactly as in the one-shot CLI.

Input jobs (one JSON object per stdin line):
    {"input": "/path/clip.mp4", "output_dir": "/path/out",
     "backend": "hybrid", "target_language": "en", "source_language": "auto",
     "gigaam_model": "v3_e2e_rnnt", "gigaam_download_root": "/path/cache",
     "openrouter_model": "google/gemini-3.5-flash", "aggregation": "mean",
     "gigaam_chunk_sec": 22.0, "correction_max_words": ..., ...}
A ``{"command": "shutdown"}`` line (or EOF) stops the worker cleanly.

``serve`` takes injectable ``load_model`` and ``process_job`` callables so the
protocol/loop can be unit-tested with stubs, without a GPU or the real
checkpoint.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Callable, TextIO

RESULT_PREFIX = "@@TRIBE_WORKER_RESULT@@ "

DEFAULT_CHECKPOINT = "facebook/tribev2"
DEFAULT_DEVICE = "cuda"
DEFAULT_AGGREGATION = "mean"
DEFAULT_BACKEND = "hybrid"
DEFAULT_TARGET_LANGUAGE = "en"
DEFAULT_SOURCE_LANGUAGE = "auto"
DEFAULT_GIGAAM_MODEL = "v3_e2e_rnnt"
DEFAULT_OPENROUTER_MODEL = "google/gemini-3.5-flash"
DEFAULT_GIGAAM_CHUNK_SEC = 22.0
DEFAULT_CORRECTION_MAX_WORDS = 120
DEFAULT_CORRECTION_MAX_SECONDS = 24.0
DEFAULT_CORRECTION_MIN_CONFIDENCE = 0.0
DEFAULT_CORRECTION_RETRIES = 2


def serve(
    load_model: Callable[[dict[str, Any]], Any],
    process_job: Callable[[Any, dict[str, Any]], dict[str, Any]],
    config: dict[str, Any],
    in_stream: TextIO,
    out_stream: TextIO,
) -> int:
    """Load the model once, then process one JSON job per input line.

    Returns 0 on clean shutdown/EOF, 1 if the model could not be loaded.
    A failure while processing a single job is reported and the loop continues,
    so one bad video does not take down the worker.
    """

    def emit(obj: dict[str, Any]) -> None:
        out_stream.write(RESULT_PREFIX + json.dumps(obj, ensure_ascii=False) + "\n")
        out_stream.flush()

    try:
        model = load_model(config)
    except Exception as exc:  # noqa: BLE001 - report any load failure to the driver
        emit({"status": "fatal", "error": str(exc), "traceback": traceback.format_exc()})
        return 1
    emit({"status": "ready"})

    for raw_line in in_stream:
        line = raw_line.strip()
        if not line:
            continue
        try:
            job = json.loads(line)
        except Exception as exc:  # noqa: BLE001
            emit({"status": "error", "stage": "parse job", "error": str(exc), "input": None})
            continue
        if job.get("command") == "shutdown":
            break
        try:
            result = process_job(model, job)
            emit({"status": "ok", "input": job.get("input"), **result})
        except Exception as exc:  # noqa: BLE001 - isolate per-job failures
            emit(
                {
                    "status": "error",
                    "input": job.get("input"),
                    "stage": job.get("stage", "processing"),
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
            )
    return 0


def real_load_model(config: dict[str, Any]) -> Any:
    """Load the real TRIBE v2 model from the shared interpreter module."""

    import tribe_nimare_interpreter as tni

    return tni.load_tribe_model(
        checkpoint=config["checkpoint"],
        cache_dir=Path(config["cache_dir"]),
        device=config["device"],
    )


def real_process_job(model: Any, job: dict[str, Any]) -> dict[str, Any]:
    """Process one input with the preloaded model and return artifact paths."""

    import tribe_nimare_interpreter as tni

    output_dir = Path(job["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    download_root = job.get("gigaam_download_root") or job["output_dir"]
    prediction = tni.process_input_with_model(
        model=model,
        input_path=Path(job["input"]),
        output_dir=output_dir,
        aggregation=job.get("aggregation", DEFAULT_AGGREGATION),
        verbose=bool(job.get("verbose", True)),
        transcript_backend=job.get("backend", DEFAULT_BACKEND),
        transcript_source_language=job.get("source_language", DEFAULT_SOURCE_LANGUAGE),
        transcript_target_language=job.get("target_language", DEFAULT_TARGET_LANGUAGE),
        gigaam_model=job.get("gigaam_model", DEFAULT_GIGAAM_MODEL),
        gigaam_download_root=Path(download_root),
        openrouter_model=job.get("openrouter_model", DEFAULT_OPENROUTER_MODEL),
        gigaam_chunk_sec=float(job.get("gigaam_chunk_sec", DEFAULT_GIGAAM_CHUNK_SEC)),
        correction_max_words=int(job.get("correction_max_words", DEFAULT_CORRECTION_MAX_WORDS)),
        correction_max_seconds=float(job.get("correction_max_seconds", DEFAULT_CORRECTION_MAX_SECONDS)),
        correction_min_confidence=float(
            job.get("correction_min_confidence", DEFAULT_CORRECTION_MIN_CONFIDENCE)
        ),
        correction_retries=int(job.get("correction_retries", DEFAULT_CORRECTION_RETRIES)),
    )
    return {
        "prediction_path": str(prediction.prediction_path),
        "activity_path": str(output_dir / "tribe_activity_fsaverage5.npy"),
        "segments_path": str(prediction.segments_path),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Persistent TRIBE v2 worker (line-delimited JSON over stdin).")
    parser.add_argument("--checkpoint", default=DEFAULT_CHECKPOINT, help="TRIBE v2 checkpoint path or HF repo id.")
    parser.add_argument("--cache-dir", default="cache/tribev2", help="TRIBE v2 feature/model cache directory.")
    parser.add_argument("--device", default=DEFAULT_DEVICE, help='Torch device, e.g. "cuda", "cpu", or "auto".')
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = {"checkpoint": args.checkpoint, "cache_dir": args.cache_dir, "device": args.device}
    return serve(real_load_model, real_process_job, config, sys.stdin, sys.stdout)


if __name__ == "__main__":
    raise SystemExit(main())
