# Evidence Bundle: scene-description-transcript-text

## Summary
- Overall status: PASS
- Last updated: 2026-07-08T09:10:00+00:00

## Acceptance criteria evidence

### AC1
- Status: PASS
- Proof:
  - Root cause inspection showed `write_template3_report()` looked only for the legacy root `gigaam_openrouter_corrected_words.tsv`.
  - The hybrid pipeline writes `tribe_transcript.tsv` at the TRIBE output root and corrected word details under `hybrid_transcription/`.
  - Local `marketing_report.xlsx` had blank `1_RAW_CORRELATIONS!C4:C10`, while `2_FRAME_MARKUP!C4:C10` referenced those blank cells, explaining Excel `0`.
  - See `.agent/tasks/scene-description-transcript-text/raw/build.txt`.
- Gaps:
  - None.

### AC2
- Status: PASS
- Proof:
  - Added `find_template3_words_tsv()` with deterministic preference order for current and legacy pipeline outputs.
  - Unit check proves priority: `tribe_transcript.tsv`, hybrid corrected words, legacy root file, then missing transcript.
  - See `.agent/tasks/scene-description-transcript-text/raw/test-unit.txt`.
- Gaps:
  - None.

### AC3
- Status: PASS
- Proof:
  - Synthetic workbook generated through `write_template3_report()` populated `1_RAW_CORRELATIONS!C4:C6` with transcript snippets aligned to 2-second segments.
  - `2_FRAME_MARKUP!C4` keeps referencing `1_RAW_CORRELATIONS!C4`, so Excel displays the populated scene text instead of a blank-derived `0`.
  - See `.agent/tasks/scene-description-transcript-text/raw/test-integration.txt`.
- Gaps:
  - None.

### AC4
- Status: PASS
- Proof:
  - Synthetic Russian transcript words were written/read with UTF-8 and verified from the generated workbook as:
    `Привет мир`, `это тест`, `финал`.
  - See `.agent/tasks/scene-description-transcript-text/raw/test-integration.txt`.
- Gaps:
  - None.

### AC5
- Status: PASS
- Proof:
  - Fallback workbook generation without any transcript TSV succeeded and left `1_RAW_CORRELATIONS!C4` blank.
  - See `.agent/tasks/scene-description-transcript-text/raw/test-integration.txt`.
- Gaps:
  - None.

### AC6
- Status: PASS
- Proof:
  - `python -m py_compile marketing_report.py template3_report.py` passed.
  - Unit and integration checks passed.
  - `git diff --check` passed.
  - See `.agent/tasks/scene-description-transcript-text/raw/lint.txt`.
- Gaps:
  - None.

## Commands run
- `python -m py_compile marketing_report.py template3_report.py`
- Unit transcript selection check via `@' ... '@ | python -`
- Synthetic Template_3 workbook generation with Russian transcript words via `@' ... '@ | python -`
- Synthetic fallback workbook generation without transcript words via `@' ... '@ | python -`
- `git diff --check -- marketing_report.py template3_report.py .agent\tasks\scene-description-transcript-text\spec.md`

## Raw artifacts
- .agent/tasks/scene-description-transcript-text/raw/build.txt
- .agent/tasks/scene-description-transcript-text/raw/test-unit.txt
- .agent/tasks/scene-description-transcript-text/raw/test-integration.txt
- .agent/tasks/scene-description-transcript-text/raw/lint.txt
- .agent/tasks/scene-description-transcript-text/raw/screenshot-1.png

## Changed files
- `marketing_report.py`
- `template3_report.py`
- `.agent/tasks/scene-description-transcript-text/spec.md`
- `.agent/tasks/scene-description-transcript-text/evidence.md`
- `.agent/tasks/scene-description-transcript-text/evidence.json`
- `.agent/tasks/scene-description-transcript-text/raw/build.txt`
- `.agent/tasks/scene-description-transcript-text/raw/test-unit.txt`
- `.agent/tasks/scene-description-transcript-text/raw/test-integration.txt`
- `.agent/tasks/scene-description-transcript-text/raw/lint.txt`

## Known gaps
- Excel formula recalculation itself was not evaluated in desktop Excel/LibreOffice; generated workbook cell contents and formulas were inspected structurally.
- Russian output depends on the transcript artifact containing Russian text. If the run is configured with target language `en`, the transcript artifact will contain English corrected text.
