# Task Spec: template3-xlsx-report

## Metadata
- Task ID: template3-xlsx-report
- Created: 2026-07-06
- Repo root: D:\Projects\Projects_Python\Media\neuromedia

## Original Task Statement
For each processed video, in addition to the HTML report, produce an Excel table in
the `Template_3_with_frames.xlsx` format (a 6-sheet "Neurosemantic Correlation
Dashboard": 1_RAW_CORRELATIONS, 2_FRAME_MARKUP, 3_INDEX_SCORES,
4_WINDOW_AGGREGATES, 5_WEIGHTS_REF, README, with an embedded video frame per row).

## Decisions (from clarifying Q&A)
- D1: The manual creative markup in 2_FRAME_MARKUP (HOOK/BRAND/PRODUCT/OFFER/CTA/LOGO
  and the `tags` column) is left as an EMPTY SKELETON for a human to fill; no
  auto-heuristics.
- D2: Rows are one-per-TRIBE-segment (frame_id F01, F02, ... = segment index), NOT
  resampled to 1 fps.
- D3: The new Template_3 xlsx REPLACES the current simple `marketing_report.xlsx`
  inside each video's report bundle (HTML stays).

## Data sources (already produced by the pipeline)
- `surface_dir/decoded_terms.csv`: columns map_id, map_path, time_index, group,
  alias, feature, match_type, r  -> per-segment (time_index) x per-term (feature) r.
- `surface_dir/marketing_scores.csv`: per-segment per-group mean_r / score_0_100.
- `tribe_dir/tribe_segments.tsv`: index, offset, duration, start, ... (segment timing).
- Transcript words (hybrid backend): `tribe_dir/gigaam_openrouter_corrected_words.tsv`
  (id/start/end/text) for scene_description alignment; may be absent.
- `input_media`: source video for per-segment frame extraction (reuse
  marketing_report.extract_video_frame).
- Shipped `Template_3_with_frames.xlsx`: used as the skeleton to preserve exact
  sheet layout, styles, README, and 5_WEIGHTS_REF.
- Term/group coverage: the template's 8 indices and 51 terms already match the
  decoder preset, so no reference-map rebuild is needed.

## Acceptance Criteria
- AC1: A new `template3_report.py` builds a workbook in the Template_3_with_frames
  format by loading the shipped template as a skeleton (openpyxl), clearing its
  example data rows/images, and writing one row per TRIBE segment. Sheets, styles,
  README text, and 5_WEIGHTS_REF are preserved from the skeleton.
- AC2: 1_RAW_CORRELATIONS is filled from decoded_terms.csv: for each segment a row
  with frame_id/second/scene_description/frame_image plus one column per template
  term, in the template's exact group+term order (ATT, AFF_A, AFF_V, MEM, REW, SOC,
  COG_CL, COG_LD), values = Pearson r. Terms/order match the template header row.
- AC3: 3_INDEX_SCORES is filled with per-segment per-index mean_r for the 8 indices
  plus `z_<INDEX>` columns (z-score of each index column across segments).
- AC4: 2_FRAME_MARKUP is an empty skeleton: frame_id/second/scene_description/
  frame_image populated; HOOK/BRAND/PRODUCT/OFFER/CTA/LOGO default to 0 (or blank)
  and the `tags` column blank, for manual annotation (D1).
- AC5: 4_WINDOW_AGGREGATES computes the markup-independent windows (Hook 0-3s,
  Hook 0-5s, AUC/full, Peak, Finale) from the per-segment index scores; the
  markup-dependent windows (BRAND/OFFER/CTA/PRODUCT/LOGO window) are left blank
  because they require the manual markup.
- AC6: One embedded frame image per segment is placed in the frame_image column,
  extracted at the segment offset via the existing ffmpeg helper. If ffmpeg or the
  media is unavailable, the cell is left blank and generation still succeeds.
- AC7: scene_description is auto-filled from the transcript words that fall inside
  each segment window [offset, offset+duration] when a words TSV is available;
  blank otherwise (D2/hybrid backend).
- AC8: marketing_report.py emits this Template_3 xlsx as the report's `.xlsx`
  (replacing the previous simple sheet, D3) and still zips it with the HTML into the
  per-video report bundle. The HTML report is unchanged.
- AC9: `openpyxl` is added to requirements, and `Template_3_with_frames.xlsx` is
  tracked in the repo so the clone-based Colab runtime and the report loader can
  find the skeleton.
- AC10: UTF-8 is explicit, new Python files start with `# -*- coding: utf-8 -*-`,
  and no secrets are written into the workbook.

## Constraints
- Reuse existing artifacts and helpers (decoded_terms.csv, marketing_scores.csv,
  tribe_segments.tsv, extract_video_frame/run_ffmpeg); do not recompute decoder
  numerics.
- Use the shipped template as a skeleton ("fill the template") rather than
  reconstructing layout/styles by hand, to guarantee format fidelity.
- Smallest defensible diff; keep the change scoped to xlsx generation + wiring.
- Do not fail the whole report if frames or transcript are missing; degrade to
  blank cells.

## Non-Goals
- Auto-populating the manual creative markup (D1).
- Changing the HTML report content or the decoder/reference maps.
- Adding new Neurosynth terms (the 51 template terms are already covered).
- Perfect visual styling beyond what the skeleton template already provides.

## Verification Plan
- Build: `python -m py_compile template3_report.py marketing_report.py`.
- Unit test (no GPU): synthesize small decoded_terms.csv / marketing_scores.csv /
  tribe_segments.tsv for K segments, call the generator, then reload the produced
  xlsx with openpyxl and assert: all 6 sheets present; 1_RAW_CORRELATIONS has K
  data rows and its term columns equal the template header terms in order;
  3_INDEX_SCORES has 8 index columns + 8 z_ columns with correct z-values;
  2_FRAME_MARKUP markup flags are blank/0; 4_WINDOW_AGGREGATES Hook/AUC/Peak/Finale
  rows are numeric while markup windows are blank; README and 5_WEIGHTS_REF match
  the skeleton.
- Integration (best-effort/manual, needs a real run): generate for one processed
  video and confirm frames embed and the bundle ZIP contains the Template_3 xlsx.
