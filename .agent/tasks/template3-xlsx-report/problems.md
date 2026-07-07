# Problems: template3-xlsx-report

## P1 — Index/window sheets came out empty (reported from a real run)

### Symptom
In a generated `Template_3_with_frames.xlsx`, sheet `3_INDEX_SCORES` showed empty
ATT..COG-LD columns and z-columns of `0,000000` (some z-columns blank).

### Root cause
The template is FORMULA-DRIVEN, which the first implementation missed:
- Only `1_RAW_CORRELATIONS` holds raw numbers (per-segment per-term r).
- `3_INDEX_SCORES` cells are Excel formulas, e.g.
  `D4 = =AVERAGE('1_RAW_CORRELATIONS'!E4*1,'1_RAW_CORRELATIONS'!F4*1.2,...)` and
  `L4 (z_ATT) = =IFERROR((D4-AVERAGE(D$4:D$23))/STDEV(D$4:D$23),0)`.
- `4_WINDOW_AGGREGATES` and `2_FRAME_MARKUP`(A:C) are formulas too.

The first `template3_report.py` CLEARED those formula cells and wrote its own
values computed from `marketing_scores.csv`. That both (a) destroyed the intended
formulas ("формулы — не редактировать") and (b) left cells blank when the
per-group score lookup returned nothing, and a key-mismatch bug left half the
z-columns unwritten.

### Fix (smallest defensible)
Rewrote `template3_report.py` to fill ONLY `1_RAW_CORRELATIONS` (frame_id, second,
scene_description, embedded frame, and the 51 raw r values) and to leave every
formula in sheets 2/3/4 intact. It also:
- clears phantom frame rows beyond the real segment count — otherwise empty
  formula rows evaluate to `#DIV/0!` and poison the `STDEV`/`AVERAGE` ranges;
- extends formula rows and widens the fixed 20-row (`$23`) aggregation anchors when
  there are more than 20 segments;
- sets `fullCalcOnLoad=True` so Excel/LibreOffice recompute on open (openpyxl
  writes formulas without cached values).

### Verification of the fix
- Unit test (`raw/test_template3.py`): raw sheet filled, index/window formulas
  PRESERVED (`D4` starts `=AVERAGE`, `L4` starts `=IFERROR`), phantom rows cleared.
- End-to-end recalc (`raw/recalc_check_libreoffice.py`, LibreOffice headless):
  after recompute, `3_INDEX_SCORES` is POPULATED — ATT index scales x1/x2/x3 with
  the injected raw r, `z_ATT = [-1, 0, +1]` (correct z over exactly the 3 real
  frames), and the phantom row is clean (no `#DIV/0!`).
