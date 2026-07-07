# -*- coding: utf-8 -*-
"""Unit test for template3_report.build_template3_workbook (no GPU, no media).

The template is formula-driven: only 1_RAW_CORRELATIONS holds raw numbers, while
3_INDEX_SCORES / 4_WINDOW_AGGREGATES / 2_FRAME_MARKUP(A:C) are Excel formulas.
This test verifies the generator fills the raw sheet per segment, PRESERVES all
formulas, and clears phantom frame rows beyond the real segment count (so empty
formula rows cannot poison the STDEV/AVERAGE ranges).
"""

import sys
import tempfile
from pathlib import Path

import openpyxl
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

import template3_report as t3  # noqa: E402

TEMPLATE = REPO_ROOT / "Template_3_with_frames.xlsx"


def _make_inputs(tmp: Path):
    term_rows = []
    feats = {"attention": "attention", "visual attention": "visual_attention", "reward": "reward"}
    for ti in range(3):  # 3 segments -> F01..F03 (< 20, trim path)
        for raw_feat in feats:
            grp = "attention" if raw_feat != "reward" else "reward"
            term_rows.append({
                "map_id": "m", "map_path": "m.npy", "time_index": ti, "group": grp,
                "alias": raw_feat, "feature": raw_feat, "match_type": "reference",
                "r": 0.1 * ti + (0.5 if raw_feat == "reward" else 0.2),
            })
    pd.DataFrame(term_rows).to_csv(tmp / "decoded_terms.csv", index=False)
    pd.DataFrame([
        {"index": 0, "offset": 0.0, "duration": 1.5},
        {"index": 1, "offset": 1.5, "duration": 1.5},
        {"index": 2, "offset": 3.0, "duration": 1.5},
    ]).to_csv(tmp / "tribe_segments.tsv", sep="\t", index=False)


def main() -> None:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _make_inputs(tmp)
        out = tmp / "Template_3_out.xlsx"
        t3.build_template3_workbook(
            template_path=TEMPLATE,
            decoded_terms_csv=tmp / "decoded_terms.csv",
            segments_tsv=tmp / "tribe_segments.tsv",
            words_tsv=None,
            output_xlsx=out,
            frame_png_provider=None,
        )
        wb = openpyxl.load_workbook(out, data_only=False)  # keep formulas

        assert {"1_RAW_CORRELATIONS", "2_FRAME_MARKUP", "3_INDEX_SCORES",
                "4_WINDOW_AGGREGATES", "5_WEIGHTS_REF", "README"}.issubset(set(wb.sheetnames))

        # --- 1_RAW_CORRELATIONS: raw numbers written; phantom rows cleared ---
        s1 = wb["1_RAW_CORRELATIONS"]
        assert s1["A4"].value == "F01" and s1["A5"].value == "F02" and s1["A6"].value == "F03"
        assert s1["A7"].value is None, "rows beyond segment count must be cleared"
        assert s1.cell(3, 6).value == "visual_attention" and s1.cell(3, 30).value == "reward"
        assert abs(float(s1.cell(6, 6).value) - 0.4) < 1e-9   # visual_attention @ ti=2
        assert abs(float(s1.cell(4, 30).value) - 0.5) < 1e-9  # reward @ ti=0

        # --- 3_INDEX_SCORES: formulas PRESERVED for real rows, phantom rows cleared ---
        s3 = wb["3_INDEX_SCORES"]
        assert isinstance(s3["D4"].value, str) and s3["D4"].value.startswith("=AVERAGE"), s3["D4"].value
        assert isinstance(s3["L4"].value, str) and s3["L4"].value.startswith("=IFERROR"), s3["L4"].value
        assert isinstance(s3["A4"].value, str) and s3["A4"].value.startswith("="), "frame_id link preserved"
        assert s3["D7"].value is None, "phantom index formula rows (>3 frames) must be cleared"

        # --- 2_FRAME_MARKUP: linked headers preserved, flag skeleton present, phantom cleared ---
        s2 = wb["2_FRAME_MARKUP"]
        assert isinstance(s2["A4"].value, str) and s2["A4"].value.startswith("="), "markup frame_id link preserved"
        assert s2["E4"].value in (0, None)  # HOOK skeleton
        assert s2["A7"].value is None, "phantom markup rows cleared"

        # --- 4_WINDOW_AGGREGATES: untouched formulas ---
        s4 = wb["4_WINDOW_AGGREGATES"]
        assert isinstance(s4["C4"].value, str) and s4["C4"].value.startswith("=AVERAGE"), s4["C4"].value

        print("PASS: raw sheet filled; index/window formulas preserved; phantom rows cleared")


if __name__ == "__main__":
    main()
    print("TEMPLATE3 TEST PASSED")
