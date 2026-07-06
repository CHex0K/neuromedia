# -*- coding: utf-8 -*-
"""Unit test for tribe_worker.serve protocol/loop, no GPU or checkpoint needed.

Verifies the persistence + fault-isolation contract:
  - the model is loaded exactly once for many jobs,
  - each job yields exactly one result line,
  - a job that raises produces a status="error" result and the loop CONTINUES,
  - a load failure yields status="fatal" and returns 1 without processing jobs.
"""

import io
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

import tribe_worker  # noqa: E402


def parse_results(out: str) -> list[dict]:
    results = []
    for line in out.splitlines():
        if line.startswith(tribe_worker.RESULT_PREFIX):
            results.append(json.loads(line[len(tribe_worker.RESULT_PREFIX):]))
    return results


def test_loads_once_and_isolates_job_failures() -> None:
    load_calls = {"n": 0}

    def fake_load(config):
        load_calls["n"] += 1
        return {"model": "stub", "loaded_from": config.get("checkpoint")}

    processed = []

    def fake_process(model, job):
        assert model["model"] == "stub"  # same preloaded model reused
        processed.append(job["input"])
        if job.get("input") == "bad.mp4":
            raise RuntimeError("boom while predicting")
        return {"prediction_path": f"/out/{job['input']}.npy"}

    jobs = [
        {"input": "a.mp4", "output_dir": "/out/a"},
        {"input": "bad.mp4", "output_dir": "/out/bad"},
        {"input": "c.mp4", "output_dir": "/out/c"},
        {"command": "shutdown"},
    ]
    in_stream = io.StringIO("\n".join(json.dumps(j) for j in jobs) + "\n")
    out_stream = io.StringIO()

    rc = tribe_worker.serve(fake_load, fake_process, {"checkpoint": "stub-ckpt"}, in_stream, out_stream)
    results = parse_results(out_stream.getvalue())

    assert rc == 0, rc
    assert load_calls["n"] == 1, f"model loaded {load_calls['n']} times, expected 1"
    assert processed == ["a.mp4", "bad.mp4", "c.mp4"], processed  # loop continued past failure

    assert results[0] == {"status": "ready"}
    ok = [r for r in results if r.get("status") == "ok"]
    err = [r for r in results if r.get("status") == "error"]
    assert len(ok) == 2, ok
    assert len(err) == 1, err
    assert err[0]["input"] == "bad.mp4"
    assert "boom while predicting" in err[0]["error"]
    assert "traceback" in err[0] and "RuntimeError" in err[0]["traceback"]
    print("PASS: loads once, per-job failure isolated, loop continued")


def test_fatal_load_reports_and_stops() -> None:
    def failing_load(config):
        raise RuntimeError("cannot load checkpoint")

    def never(model, job):  # pragma: no cover - must not be called
        raise AssertionError("process_job must not run when load fails")

    in_stream = io.StringIO(json.dumps({"input": "a.mp4"}) + "\n")
    out_stream = io.StringIO()
    rc = tribe_worker.serve(failing_load, never, {}, in_stream, out_stream)
    results = parse_results(out_stream.getvalue())

    assert rc == 1, rc
    assert len(results) == 1 and results[0]["status"] == "fatal", results
    assert "cannot load checkpoint" in results[0]["error"]
    print("PASS: fatal load reported, no jobs processed")


def test_invalid_json_line_is_isolated() -> None:
    def fake_load(config):
        return "m"

    def fake_process(model, job):
        return {"prediction_path": "/out/ok.npy"}

    in_stream = io.StringIO("not-json\n" + json.dumps({"input": "ok.mp4"}) + "\n")
    out_stream = io.StringIO()
    rc = tribe_worker.serve(fake_load, fake_process, {}, in_stream, out_stream)
    results = parse_results(out_stream.getvalue())

    assert rc == 0
    statuses = [r["status"] for r in results]
    assert statuses == ["ready", "error", "ok"], statuses
    print("PASS: invalid JSON line isolated, subsequent job still ran")


if __name__ == "__main__":
    test_loads_once_and_isolates_job_failures()
    test_fatal_load_reports_and_stops()
    test_invalid_json_line_is_isolated()
    print("ALL WORKER PROTOCOL TESTS PASSED")
