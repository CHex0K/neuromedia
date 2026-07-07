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

## P2 — Template example markup (LOGO=1) leaked into real reports

### Symptom
In a real report, `2_FRAME_MARKUP` showed `LOGO=1` on frames F03/F04 even though
the markup is supposed to be a clean 0 skeleton.

### Root cause
The shipped `Template_3_with_frames.xlsx` ships example markup values (LOGO=1 on
F03/F04). The formula-preserving generator cleared only phantom rows beyond the
segment count, so the example flag cells (E:J) in the real rows were left as-is.

### Fix
In the per-segment fill loop, reset the manual markup flag columns (E:J =
HOOK/BRAND/PRODUCT/OFFER/CTA/LOGO) to `0` for every real frame row.

### Verification
Unit test now asserts `2_FRAME_MARKUP!J6` (template ships LOGO=1 there) == 0 after
generation; test passes.

## P3 — Empty scene_description and no embedded frames (missing segment timing)

### Symptom
In a real report, `scene_description` (col C) was blank on every row and no frame
images were embedded; the `second` column showed 1..10 (frame ordinals, not times).

### Root cause
`tribe_segments.tsv` leaves the `offset` column EMPTY and stores the real
per-segment time in the `start` column (0.0, 1.0, ... , 9.0). The generator picked
the timing column by name (`offset` first) via `_find_column`, which returned the
existing-but-empty `offset` column, so every segment offset was `None`. With no
offset, both features that depend on it failed silently: the frame timestamp
(`start + duration/2`) could not be computed (no frame), and transcript words could
not be aligned to a segment window (blank scene_description).

### Fix
Added `_first_populated_column(...)` and used it for the timing/duration lookups:
it prefers the first candidate column that actually has data
(`offset` -> else `start` -> else `timeline`). Now offsets come from `start`.

### Verification
Unit test mimics the real TSV (empty `offset`, populated `start`) plus a words TSV
and asserts `second` = start values (0,1,2) and `scene_description` = the
window-aligned words ("hello","world","foo"). Test passes. Frame extraction uses
the same offset, so frames embed once a video is provided.

## P4 — Template example red fill leaked onto the F03 tags cell

### Symptom
The `tags` cell of frame F03 (`3_INDEX_SCORES!C6`) appeared red in every report.

### Root cause
The shipped template highlights `3_INDEX_SCORES!C6` red (its example ad had LOGO on
F03). The generator preserved the formula but never touched cell fills, so the
example red persisted on F03 of every generated report. Structural reds (LOGO header
`2_FRAME_MARKUP!J3`, LOGO window `4_WINDOW_AGGREGATES!A13/B13`, a README line) are
intentional and must stay.

### Fix
`_reset_data_fills` clears solid cell fills on the DATA rows (4..last) of sheets 1-3
after filling, removing the stray F03 red while leaving header rows and the other
sheets' structural reds untouched.

### Verification
Unit test asserts `3_INDEX_SCORES!C6.fill.patternType != "solid"` after generation;
a manual check confirms `2_FRAME_MARKUP!J3` and `4_WINDOW_AGGREGATES!A13` stay red.
