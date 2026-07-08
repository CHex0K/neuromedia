# Evidence Bundle: dynamic-finale-3sec-window

## Summary
- Overall status: PASS
- Last updated: 2026-07-08T08:55:00+00:00

## Acceptance criteria evidence

### AC1
- Status: PASS
- Proof:
  - Template inspection found fixed `Finale` formulas like `=AVERAGE('3_INDEX_SCORES'!D21:D23)`.
  - See `.agent/tasks/dynamic-finale-3sec-window/raw/build.txt`.
- Gaps:
  - None.

### AC2
- Status: PASS
- Proof:
  - `_finale_window_rows()` computes segment intervals from `offset` and `duration`.
  - Synthetic workbook with 2-second segments rewrote `C8` to `=AVERAGE('3_INDEX_SCORES'!D7:D8)`, matching the rows overlapping final `[7, 10)` seconds.
  - See `.agent/tasks/dynamic-finale-3sec-window/raw/test-integration.txt`.
- Gaps:
  - None.

### AC3
- Status: PASS
- Proof:
  - Unit test proves the selected rows are `(7, 8)`, not rows 21-23 and not the last three rows `(6, 8)`, when timing exists.
  - See `.agent/tasks/dynamic-finale-3sec-window/raw/test-unit.txt`.
- Gaps:
  - None.

### AC4
- Status: PASS
- Proof:
  - Unit and integration checks without timing fall back to rows `(6, 8)` for five rows.
  - See `.agent/tasks/dynamic-finale-3sec-window/raw/test-unit.txt` and `.agent/tasks/dynamic-finale-3sec-window/raw/test-integration.txt`.
- Gaps:
  - None.

### AC5
- Status: PASS
- Proof:
  - Generated workbook row label is `Finale last 3s`.
  - The fixed `18-20с` label is overwritten during generation.
  - See `.agent/tasks/dynamic-finale-3sec-window/raw/test-integration.txt`.
- Gaps:
  - None.

### AC6
- Status: PASS
- Proof:
  - `python -m py_compile template3_report.py` passed.
  - Synthetic workbook generation passed.
  - `git diff --check` passed.
  - Proof-loop validation passed.
- Gaps:
  - None.

## Commands run
- `python -m py_compile template3_report.py`
- Unit helper check via `@' ... '@ | python -`
- Synthetic workbook generation with timing via `@' ... '@ | python -`
- Synthetic workbook generation without timing via `@' ... '@ | python -`
- `rg -n "FINALE_WINDOW_SECONDS|_finale_window_rows|_rewrite_finale_window|Finale last|последние 3" template3_report.py`
- `git diff --check -- template3_report.py .agent\tasks\dynamic-finale-3sec-window\spec.md`
- `python .agents\skills\repo-task-proof-loop\scripts\task_loop.py validate --task-id dynamic-finale-3sec-window`

## Commands for fresh verifier
- `python -m py_compile template3_report.py`
- `rg -n "FINALE_WINDOW_SECONDS|_finale_window_rows|_rewrite_finale_window|Finale last|последние 3" template3_report.py`
- Generate a synthetic workbook with 5 two-second segments and inspect `4_WINDOW_AGGREGATES!C8`.
- Generate a synthetic workbook without `segments.tsv` and inspect `4_WINDOW_AGGREGATES!C8`.
- `git diff --check -- template3_report.py .agent\tasks\dynamic-finale-3sec-window\spec.md .agent\tasks\dynamic-finale-3sec-window\evidence.md .agent\tasks\dynamic-finale-3sec-window\evidence.json`
- `python .agents\skills\repo-task-proof-loop\scripts\task_loop.py validate --task-id dynamic-finale-3sec-window`

## Raw artifacts
- `.agent/tasks/dynamic-finale-3sec-window/raw/build.txt`
- `.agent/tasks/dynamic-finale-3sec-window/raw/test-unit.txt`
- `.agent/tasks/dynamic-finale-3sec-window/raw/test-integration.txt`
- `.agent/tasks/dynamic-finale-3sec-window/raw/lint.txt`
- `.agent/tasks/dynamic-finale-3sec-window/raw/screenshot-1.png`

## Changed files
- `template3_report.py`
- `.agent/tasks/dynamic-finale-3sec-window/spec.md`
- `.agent/tasks/dynamic-finale-3sec-window/evidence.md`
- `.agent/tasks/dynamic-finale-3sec-window/evidence.json`
- `.agent/tasks/dynamic-finale-3sec-window/raw/build.txt`
- `.agent/tasks/dynamic-finale-3sec-window/raw/test-unit.txt`
- `.agent/tasks/dynamic-finale-3sec-window/raw/test-integration.txt`
- `.agent/tasks/dynamic-finale-3sec-window/raw/lint.txt`

## Known gaps
- Excel formula recalculation itself was not evaluated in desktop Excel/LibreOffice; formulas were inspected structurally.
