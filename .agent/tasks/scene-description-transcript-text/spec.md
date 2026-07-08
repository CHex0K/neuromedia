# Task Spec: scene-description-transcript-text

## Metadata
- Task ID: scene-description-transcript-text
- Created: 2026-07-08T08:50:48+00:00
- Repo root: D:\Projects\Projects_Python\Media\neuromedia
- Working directory at init: D:\Projects\Projects_Python\Media\neuromedia

## Guidance sources
- AGENTS.md
- CLAUDE.md

## Original task statement
Fix Template_3 Excel scene_description population: generated reports currently show blank/0 scene_description because the report generator looks for the wrong transcript words file. It must use available TRIBE/hybrid transcript artifacts so scene_description contains transcript snippets aligned to each segment, preserving Russian text when the transcript artifact is Russian.

## Acceptance criteria
- AC1: The root cause is documented: generated Template_3 workbooks show blank/`0` `scene_description` because `write_template3_report()` only looks for `tribe_dir/gigaam_openrouter_corrected_words.tsv`, while the hybrid pipeline writes the main transcript to `tribe_dir/tribe_transcript.tsv` and the detailed corrected words file under `tribe_dir/hybrid_transcription/`.
- AC2: The Template_3 report path discovers transcript word artifacts in the locations produced by the current TRIBE/hybrid pipeline, with a deterministic preference order.
- AC3: `scene_description` cells in generated workbooks contain transcript snippets aligned to segment timing when transcript words and segment timing are available.
- AC4: Russian transcript text is preserved as UTF-8 in generated workbooks when the selected transcript artifact contains Russian text.
- AC5: Existing fallback behavior remains safe: if no transcript artifact is available, report generation still succeeds and leaves `scene_description` blank rather than failing.
- AC6: Focused checks prove Python syntax, transcript artifact selection, workbook generation, and diff hygiene.

## Constraints
- Preserve UTF-8 encoding for all touched files.
- Keep the change focused on Template_3 report generation/transcript selection.
- Do not edit generated user Drive files or existing `.xlsx` outputs.
- Do not change the transcript target language default unless explicitly requested.

## Non-goals
- Do not rerun GigaAM/OpenRouter/TRIBE transcription.
- Do not change neural scoring, segmentation, or marketing aggregate formulas.
- Do not evaluate Excel formulas in desktop Excel/LibreOffice.
- Do not guarantee Russian output when the run was configured to translate/correct transcript text to English.

## Verification plan
- Build: Run `python -m py_compile marketing_report.py template3_report.py`.
- Unit tests: Exercise transcript artifact selection against temporary TRIBE directories containing root `tribe_transcript.tsv`, hybrid corrected words, and missing files.
- Integration tests: Generate a synthetic Template_3 workbook with Russian words and segment timing, then inspect `1_RAW_CORRELATIONS!C4:C*`.
- Fallback tests: Generate without transcript words and confirm generation succeeds with blank descriptions.
- Lint: Run `git diff --check` on changed code and task artifacts.
- Manual checks: Inspect the existing local `marketing_report.xlsx`/template behavior to confirm why blank raw cells show as `0` through formula references.
