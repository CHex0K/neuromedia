# -*- coding: utf-8 -*-
"""End-to-end: build Template_3 from synthetic data, recalc via LibreOffice, verify."""
import subprocess, sys, tempfile, shutil
from pathlib import Path
import pandas as pd, openpyxl

REPO = Path(r"d:\Projects\Projects_Python\Media\neuromedia")
sys.path.insert(0, str(REPO))
import template3_report as t3

SOFFICE = r"C:\Program Files\LibreOffice\program\soffice.exe"

with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)
    # 3 segments; give attention terms distinct r so ATT index varies across frames
    rows = []
    att_terms = ["attention", "visual attention", "attentional", "orienting",
                 "target detection", "salience", "visual stimuli", "distractor"]
    for ti in range(3):
        for feat in att_terms:
            rows.append({"map_id": "m", "map_path": "m.npy", "time_index": ti,
                         "group": "attention", "alias": feat, "feature": feat,
                         "match_type": "reference", "r": 0.1 + 0.1 * ti})
    pd.DataFrame(rows).to_csv(tmp / "decoded_terms.csv", index=False)
    pd.DataFrame([{"index": i, "offset": float(i), "duration": 1.0} for i in range(3)]).to_csv(
        tmp / "tribe_segments.tsv", sep="\t", index=False)

    out = tmp / "t3.xlsx"
    t3.build_template3_workbook(template_path=REPO / "Template_3_with_frames.xlsx",
                                decoded_terms_csv=tmp / "decoded_terms.csv",
                                segments_tsv=tmp / "tribe_segments.tsv",
                                output_xlsx=out, frame_png_provider=None)

    # LibreOffice recalculates on load; convert to xlsx into a new dir
    outdir = tmp / "recalc"; outdir.mkdir()
    subprocess.run([SOFFICE, "--headless", "--calc", "--convert-to", "xlsx",
                    "--outdir", str(outdir), str(out)], check=True,
                   capture_output=True, timeout=120)
    recalc = outdir / "t3.xlsx"
    wb = openpyxl.load_workbook(recalc, data_only=True)
    s3 = wb["3_INDEX_SCORES"]
    att = [s3.cell(r, 4).value for r in (4, 5, 6)]  # ATT index per frame
    z_att = [s3.cell(r, 12).value for r in (4, 5, 6)]  # z_ATT
    print("ATT index (frames 1-3):", att)
    print("z_ATT (frames 1-3):", z_att)
    # raw r scales linearly with ti (0.1, 0.2, 0.3) so the ATT index must scale x1,x2,x3
    assert all(v is not None for v in att), ("index sheet still empty!", att)
    assert abs(att[1] / att[0] - 2.0) < 1e-6 and abs(att[2] / att[0] - 3.0) < 1e-6, att
    # z-score of 3 equally spaced values must be [-1, 0, +1] -> proves z uses the real 3 frames
    assert abs(z_att[0] + 1.0) < 1e-6 and abs(z_att[1]) < 1e-6 and abs(z_att[2] - 1.0) < 1e-6, z_att
    # phantom row 7 must be empty (not #DIV/0!)
    assert s3.cell(7, 4).value in (None, ""), ("phantom row not clean", s3.cell(7, 4).value)
    print("PASS: formulas recalculated, index sheet populated, phantom rows clean")
