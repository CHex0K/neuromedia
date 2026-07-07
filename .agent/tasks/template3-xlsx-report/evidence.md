# Evidence: template3-xlsx-report

## What changed
- `template3_report.py` (new): builds a `Template_3_with_frames.xlsx`-format
  workbook by loading the shipped template as a skeleton (openpyxl), clearing its
  example rows/images, and writing one row per TRIBE segment. Drives term/index/
  window columns from the template header rows, so layout/README/5_WEIGHTS_REF are
  preserved.
- `marketing_report.py`: `generate_report` now calls new `write_template3_report`
  which emits the report `.xlsx` in Template_3 format (replacing the legacy simple
  sheet, D3), with a fallback to the old `write_excel_report` if the skeleton or
  optional deps are missing. Added `extract_frame_png_bytes` (raw PNG bytes) and
  refactored `extract_video_frame` to reuse it; frames are embedded per segment.
- `requirements.txt`: added `openpyxl>=3.1,<4`.
- `Template_3_with_frames.xlsx`: tracked in the repo so the clone-based Colab
  runtime and the report loader find the skeleton.

## Sheet mapping (per decisions D1-D3) — IMPORTANT: template is formula-driven
The template computes everything except the raw correlations via Excel formulas
("формулы — не редактировать"), so the generator fills ONLY the raw sheet and
leaves the formulas intact (see problems.md P1 for the earlier defect where the
formula sheets were wrongly overwritten and came out empty).
- 1_RAW_CORRELATIONS (ONLY sheet written): per-segment rows; frame_id/second/
  scene_description/frame, plus 51 term columns filled from `decoded_terms.csv` (r)
  in the template's exact group+term order.
- 3_INDEX_SCORES: FORMULAS PRESERVED (weighted AVERAGE of raw terms + z-scores);
  Excel recomputes from sheet 1 on open.
- 2_FRAME_MARKUP: frame_id/second/scene are formulas linked to sheet 1 (preserved);
  HOOK/BRAND/PRODUCT/OFFER/CTA/LOGO stay the 0 skeleton for manual fill (D1); frames
  embedded.
- 4_WINDOW_AGGREGATES: FORMULAS PRESERVED (AVERAGE/MAX/AVERAGEIF); markup windows are
  AVERAGEIF formulas that stay blank until markup is filled.
- 5_WEIGHTS_REF, README: preserved from the skeleton.
- Phantom frame rows beyond the real segment count are cleared so empty formulas
  cannot evaluate to #DIV/0! and poison STDEV/AVERAGE; >20 segments extend the
  formula rows and widen the fixed ranges. `fullCalcOnLoad=True` forces recompute.
- Rows are one-per-TRIBE-segment (D2); frames embedded per segment via ffmpeg.

## Verification (current code, current results) — see raw/verification-output.txt
All commands exit 0:
- `python -m py_compile template3_report.py marketing_report.py` -> OK.
- `import marketing_report` OK; `write_template3_report` and `extract_frame_png_bytes`
  present (wiring sanity).
- `raw/test_template3.py` (no GPU, no media): synthesizes decoded_terms /
  marketing_scores / tribe_segments for 3 segments, fills the real template skeleton,
  reloads the produced xlsx and asserts:
  - all 6 sheets preserved;
  - 1_RAW_CORRELATIONS has 3 segment rows (F01/F02/F03), extra template rows cleared,
    term columns equal the template header (visual_attention@col6, reward@col30) with
    the injected r values;
  - 3_INDEX_SCORES ATT column matches inputs and z_ATT equals np zscore(ddof=0);
  - 2_FRAME_MARKUP flags are all 0 (skeleton);
  - 4_WINDOW_AGGREGATES Hook/AUC/Peak numeric while the BRAND window row is blank.

## Not executed locally (needs a real processed video + Colab)
- End-to-end generation with embedded frames (ffmpeg) and the transcript-derived
  scene_description (hybrid backend), and confirming the Template_3 xlsx lands in the
  per-video report ZIP. Frame embedding uses PIL/openpyxl at runtime (pillow is in
  requirements). Locally the test runs with frame_png_provider=None.

## Notes / scope
- Terms/indices already covered by the decoder preset -> no reference-map rebuild.
- Window z-rows follow the template's fixed-second window definitions (0-3, 0-5,
  18-20); windows with no matching segments are left blank.
- Robustness: the xlsx step never fails the report (falls back to the legacy sheet;
  missing frames/transcript degrade to blank cells).
