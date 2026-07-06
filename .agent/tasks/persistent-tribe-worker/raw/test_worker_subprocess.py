# -*- coding: utf-8 -*-
"""Cross-process smoke test: drive tribe_worker.serve over real OS pipes.

Proves the sentinel protocol survives a real subprocess boundary (Popen +
stdin/stdout), which is what the notebook's TribeWorkerSession relies on. Uses a
stub model + stub processor, so no GPU or checkpoint is needed.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]

STUB_WORKER = r'''
import sys
from pathlib import Path
sys.path.insert(0, r"{repo}")
import tribe_worker

def load(config):
    return {{"m": "stub"}}

def process(model, job):
    if job.get("input") == "bad":
        raise RuntimeError("stub predict failure")
    return {{"prediction_path": "/out/" + str(job.get("input")) + ".npy"}}

raise SystemExit(tribe_worker.serve(load, process, {{}}, sys.stdin, sys.stdout))
'''.format(repo=str(REPO_ROOT))


def main() -> None:
    proc = subprocess.Popen(
        [sys.executable, "-c", STUB_WORKER],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    jobs = [
        {"input": "good1", "output_dir": "/out/1"},
        {"input": "bad", "output_dir": "/out/bad"},
        {"input": "good2", "output_dir": "/out/2"},
        {"command": "shutdown"},
    ]
    stdin_payload = "".join(json.dumps(j) + "\n" for j in jobs)
    out, _ = proc.communicate(stdin_payload, timeout=30)

    results = [
        json.loads(line[len(tribe_prefix):])
        for line in out.splitlines()
        if line.startswith(tribe_prefix)
    ]
    statuses = [r.get("status") for r in results]
    assert statuses == ["ready", "ok", "error", "ok"], (statuses, out)
    assert results[2]["input"] == "bad"
    assert "stub predict failure" in results[2]["error"]
    assert proc.returncode == 0, proc.returncode
    print("PASS: real subprocess protocol OK, statuses =", statuses)


tribe_prefix = "@@TRIBE_WORKER_RESULT@@ "

if __name__ == "__main__":
    main()
    print("SUBPROCESS SMOKE TEST PASSED")
