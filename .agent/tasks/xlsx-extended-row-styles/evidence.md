# Evidence Bundle: xlsx-extended-row-styles

## Summary
- Overall status: PASS
- Last updated: 2026-07-08T14:36:00+00:00

## Acceptance criteria evidence

### AC1
- Status: PASS
- Proof:
  - `template3_report.py` now copies row/cell formatting from the template data row to dynamically added rows.
  - Integration generated a 21-row workbook and proved row 24 (`F21`) style matches row 23 (`F20`) on `1_RAW_CORRELATIONS`, `2_FRAME_MARKUP`, and `3_INDEX_SCORES`.
  - See `.agent/tasks/xlsx-extended-row-styles/raw/test-integration.txt`.
- Gaps:
  - None.

### AC2
- Status: PASS
- Proof:
  - Integration proved raw `A24 = F21`, raw `B24 = 20`, row 24 formula cells exist on `3_INDEX_SCORES`, and markup row 24 formulas/static zero flags are preserved.
  - See `.agent/tasks/xlsx-extended-row-styles/raw/test-integration.txt`.
- Gaps:
  - None.

### AC3
- Status: PASS
- Proof:
  - Integration proved generated workbook has no red fills after style propagation.
  - See `.agent/tasks/xlsx-extended-row-styles/raw/test-integration.txt`.
- Gaps:
  - None.

### AC4
- Status: PASS
- Proof:
  - Integration generated a 20-row workbook and proved raw data stops at `F20` without creating `F21`.
  - See `.agent/tasks/xlsx-extended-row-styles/raw/test-integration.txt`.
- Gaps:
  - None.

### AC5
- Status: PASS
- Proof:
  - `python -m py_compile template3_report.py` passed.
  - Direct helper unit check passed.
  - Synthetic 21-row and 20-row workbook integration checks passed.
  - `git diff --check` passed; git emitted only its line-ending warning for `template3_report.py`.
- Gaps:
  - None.

## Commands run
- `python -m py_compile template3_report.py`
- Direct `_copy_row_format()` unit check via `@' ... '@ | python -`
- Synthetic Template_3 workbook style/formula integration check via `@' ... '@ | python -`
- `git diff --check -- template3_report.py .agent\tasks\xlsx-extended-row-styles\spec.md`

## Raw artifacts
- .agent/tasks/xlsx-extended-row-styles/raw/build.txt
- .agent/tasks/xlsx-extended-row-styles/raw/test-unit.txt
- .agent/tasks/xlsx-extended-row-styles/raw/test-integration.txt
- .agent/tasks/xlsx-extended-row-styles/raw/lint.txt
- .agent/tasks/xlsx-extended-row-styles/raw/screenshot-1.png

## Known gaps
- Existing `.xlsx` files are not modified; reports must be regenerated.
