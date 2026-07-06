# -*- coding: utf-8 -*-
"""Unit test for template3_report.build_template3_workbook (no GPU, no media).

Synthesizes small decoded_terms / marketing_scores / tribe_segments artifacts for
3 segments, fills the shipped template skeleton, reloads the produced xlsx and
asserts the contract: sheets preserved, per-segment rows, term columns mapped in
template order, index + z columns, blank manual markup, computed window rows.
"""

import sys
import tempfile
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

import template3_report as t3  # noqa: E402

TEMPLATE = REPO_ROOT / "Template_3_with_frames.xlsx"


def _make_inputs(tmp: Path):
    # 3 segments (time_index 0,1,2). Populate a few known terms + all 8 groups.
    term_rows = []
    feats = {"attention": "attention", "visual attention": "visual_attention", "reward": "reward"}
    for ti in range(3):
        for raw_feat in feats:
            grp = "attention" if raw_feat != "reward" else "reward"
            term_rows.append({
                "map_id": "m", "map_path": "m.npy", "time_index": ti, "group": grp,
                "alias": raw_feat, "feature": raw_feat, "match_type": "reference",
                "r": 0.1 * ti + (0.5 if raw_feat == "reward" else 0.2),
            })
    pd.DataFrame(term_rows).to_csv(tmp / "decoded_terms.csv", index=False)

    # per-segment per-group mean_r; attention varies for a real z-score
    att = {0: -0.2, 1: 0.0, 2: 0.4}
    score_rows = []
    for ti in range(3):
        for grp in ["attention", "affect_arousal", "affect_valence", "memory",
                    "reward", "social", "cog_clarity", "cog_load"]:
            score_rows.append({
                "map_id": "m", "map_path": "m.npy", "time_index": ti, "group": grp,
                "mean_r": att[ti] if grp == "attention" else 0.05 * ti,
                "score_0_100": 50.0,
            })
    pd.DataFrame(score_rows).to_csv(tmp / "marketing_scores.csv", index=False)

    pd.DataFrame([
        {"index": 0, "offset": 0.0, "duration": 1.5},
        {"index": 1, "offset": 1.5, "duration": 1.5},
        {"index": 2, "offset": 3.0, "duration": 1.5},
    ]).to_csv(tmp / "tribe_segments.tsv", sep="\t", index=False)
    return att


def main() -> None:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        att = _make_inputs(tmp)
        out = tmp / "Template_3_out.xlsx"
        t3.build_template3_workbook(
            template_path=TEMPLATE,
            decoded_terms_csv=tmp / "decoded_terms.csv",
            marketing_scores_csv=tmp / "marketing_scores.csv",
            segments_tsv=tmp / "tribe_segments.tsv",
            words_tsv=None,
            output_xlsx=out,
            frame_png_provider=None,
        )
        wb = openpyxl.load_workbook(out, data_only=True)

        expected_sheets = {"1_RAW_CORRELATIONS", "2_FRAME_MARKUP", "3_INDEX_SCORES",
                           "4_WINDOW_AGGREGATES", "5_WEIGHTS_REF", "README"}
        assert expected_sheets.issubset(set(wb.sheetnames)), wb.sheetnames

        # --- 1_RAW_CORRELATIONS ---
        s1 = wb["1_RAW_CORRELATIONS"]
        assert s1.cell(4, 1).value == "F01" and s1.cell(5, 1).value == "F02" and s1.cell(6, 1).value == "F03"
        assert s1.cell(7, 1).value is None, "extra template rows must be cleared"
        # term columns: header row3 col6 == visual_attention, col30 == reward
        assert s1.cell(3, 6).value == "visual_attention" and s1.cell(3, 30).value == "reward"
        # r for visual attention at seg ti=2 -> 0.1*2+0.2 = 0.4
        assert abs(float(s1.cell(6, 6).value) - 0.4) < 1e-9, s1.cell(6, 6).value
        # r for reward at seg ti=0 -> 0.5
        assert abs(float(s1.cell(4, 30).value) - 0.5) < 1e-9, s1.cell(4, 30).value

        # --- 3_INDEX_SCORES ---
        s3 = wb["3_INDEX_SCORES"]
        att_vals = np.array([att[0], att[1], att[2]])
        for i in range(3):
            assert abs(float(s3.cell(4 + i, 4).value) - att_vals[i]) < 1e-9  # col4 = ATT
        std = att_vals.std(ddof=0)
        z_expected = (att_vals - att_vals.mean()) / std
        for i in range(3):
            assert abs(float(s3.cell(4 + i, 12).value) - z_expected[i]) < 1e-6, "z_ATT wrong"  # col12 = z_ATT

        # --- 2_FRAME_MARKUP: manual flags blank skeleton (== 0) ---
        s2 = wb["2_FRAME_MARKUP"]
        for col in range(5, 11):
            assert s2.cell(4, col).value == 0, (col, s2.cell(4, col).value)
        assert s2.cell(4, 1).value == "F01"

        # --- 4_WINDOW_AGGREGATES: computed rows numeric, markup window blank ---
        s4 = wb["4_WINDOW_AGGREGATES"]
        # Hook 0-3s (row4) ATT (col3) = mean(att for offset<3) = mean(att[0],att[1])
        assert abs(float(s4.cell(4, 3).value) - np.mean([att[0], att[1]])) < 1e-9
        # AUC full (row6) ATT = mean of all
        assert abs(float(s4.cell(6, 3).value) - att_vals.mean()) < 1e-9
        # Peak (row7) ATT = max
        assert abs(float(s4.cell(7, 3).value) - att_vals.max()) < 1e-9
        # BRAND window (row9) must be blank (markup-dependent)
        assert s4.cell(9, 3).value in (None, ""), s4.cell(9, 3).value

        print("PASS: template3 workbook filled correctly")
        print("  sheets:", sorted(expected_sheets & set(wb.sheetnames)))
        print("  segment rows: 3; z_ATT + windows verified; markup skeleton blank")


if __name__ == "__main__":
    main()
    print("TEMPLATE3 TEST PASSED")
