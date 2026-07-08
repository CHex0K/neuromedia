# Evidence Bundle: xlsx-overlap-scene-transcript

## Summary
- Overall status: PASS
- Last updated: 2026-07-08T13:28:00+00:00

## Acceptance criteria evidence

### AC1
- Status: PASS
- Proof:
  - `_segment_rows()` now uses interval overlap when transcript `end` or `duration` is available.
  - Unit and integration checks prove `0.8-1.2` appears in both `[0,1]` and `[1,2]` segment rows.
  - See `.agent/tasks/xlsx-overlap-scene-transcript/raw/test-unit.txt` and `.agent/tasks/xlsx-overlap-scene-transcript/raw/test-integration.txt`.
- Gaps:
  - None.

### AC2
- Status: PASS
- Proof:
  - Integration workbook generated `1_RAW_CORRELATIONS!C4 = смотри` and `C5 = смотри` for one boundary-crossing transcript row.
  - See `.agent/tasks/xlsx-overlap-scene-transcript/raw/test-integration.txt`.
- Gaps:
  - None.

### AC3
- Status: PASS
- Proof:
  - Integration input had `target_language=en`, `text=look`, and `original_text=смотри`; generated XLSX used `смотри`.
  - This proves existing XLSX display text-column selection is preserved.
  - See `.agent/tasks/xlsx-overlap-scene-transcript/raw/test-integration.txt`.
- Gaps:
  - None.

### AC4
- Status: PASS
- Proof:
  - Unit and integration fallback checks with only `start` and no interval columns produced first-row-only text.
  - See `.agent/tasks/xlsx-overlap-scene-transcript/raw/test-unit.txt` and `.agent/tasks/xlsx-overlap-scene-transcript/raw/test-integration.txt`.
- Gaps:
  - None.

### AC5
- Status: PASS
- Proof:
  - `python -m py_compile template3_report.py` passed.
  - Unit and integration checks passed.
  - `git diff --check` passed.
  - See `.agent/tasks/xlsx-overlap-scene-transcript/raw/lint.txt`.
- Gaps:
  - None.

## Commands run
- `python -m py_compile template3_report.py`
- Unit `_segment_rows()` overlap/fallback check via `@' ... '@ | python -`
- Synthetic Template_3 workbook overlap/fallback generation through `build_template3_workbook()` via `@' ... '@ | python -`
- `git diff --check -- template3_report.py .agent\tasks\xlsx-overlap-scene-transcript\spec.md`

## Raw artifacts
- .agent/tasks/xlsx-overlap-scene-transcript/raw/build.txt
- .agent/tasks/xlsx-overlap-scene-transcript/raw/test-unit.txt
- .agent/tasks/xlsx-overlap-scene-transcript/raw/test-integration.txt
- .agent/tasks/xlsx-overlap-scene-transcript/raw/lint.txt
- .agent/tasks/xlsx-overlap-scene-transcript/raw/screenshot-1.png

## Changed files
- `template3_report.py`
- `.agent/tasks/xlsx-overlap-scene-transcript/spec.md`
- `.agent/tasks/xlsx-overlap-scene-transcript/evidence.md`
- `.agent/tasks/xlsx-overlap-scene-transcript/evidence.json`
- `.agent/tasks/xlsx-overlap-scene-transcript/raw/build.txt`
- `.agent/tasks/xlsx-overlap-scene-transcript/raw/test-unit.txt`
- `.agent/tasks/xlsx-overlap-scene-transcript/raw/test-integration.txt`
- `.agent/tasks/xlsx-overlap-scene-transcript/raw/lint.txt`

## Known gaps
- Existing `.xlsx` files are not modified; reports must be regenerated.
- The HTML report was not changed because the task was to make XLSX match existing HTML overlap behavior.
