"""Sync standalone source files into the Colab notebook's base64 constants.

The Colab notebook (run_surface_decoder_colab.ipynb) is self-contained: it stores
each project file as a base64 string and writes it to /content/neuromedia at run
time. Editing the standalone .py files alone has NO effect on Colab until this
script re-encodes them into the notebook constants. Run this after editing any
mapped source file, then re-upload / re-open the notebook on Colab.
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path

NOTEBOOK = "run_surface_decoder_colab.ipynb"

# notebook constant name -> source file on disk
MAPPING = {
    "TRIBE_B64": "tribe_nimare_interpreter.py",
    "SURFACE_DECODER_B64": "marketing_surface_decoder.py",
    "REPORT_B64": "marketing_report.py",
    "HYBRID_TRANSCRIBER_B64": "hybrid_transcriber.py",
    "REQUIREMENTS_B64": "requirements.txt",
    "TRIBE_NODEPS_REQUIREMENTS_B64": "requirements-tribe-nodeps.txt",
    "HYBRID_NODEPS_REQUIREMENTS_B64": "requirements-hybrid-nodeps.txt",
}


def encode(path: str) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode("ascii")


def main() -> None:
    nb = json.loads(Path(NOTEBOOK).read_text(encoding="utf-8"))
    updated: dict[str, bool] = {name: False for name in MAPPING}

    for const_name, src_file in MAPPING.items():
        if not Path(src_file).exists():
            print(f"skip {const_name}: {src_file} not found")
            continue
        new_b64 = encode(src_file)
        pattern = re.compile(rf'({re.escape(const_name)}\s*=\s*")[^"]+(")')
        for cell in nb.get("cells", []):
            src = cell.get("source", [])
            for i, line in enumerate(src):
                if const_name in line and "b64decode" not in line and pattern.search(line):
                    src[i] = pattern.sub(lambda m: m.group(1) + new_b64 + m.group(2), line)
                    updated[const_name] = True

    Path(NOTEBOOK).write_text(
        json.dumps(nb, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )

    for name, ok in updated.items():
        print(f"{'OK ' if ok else 'MISS'} {name} <- {MAPPING[name]}")


if __name__ == "__main__":
    main()
