# Evidence: marketing-groups-v2

## Summary

Overall evidence status: `PASS`

The marketing surface decoder and reports now use the new `marketing_v2` preset with 8 groups, 51 configured terms, no duplicates, and a new reference cache/version so old `marketing_v1` maps are not reused.

## AC1

Status: `PASS`

Criterion: `marketing_surface_decoder.py` uses the new 8-group marketing preset with no term duplicated across groups.

Proof:
- `marketing_surface_decoder.py` defines `MARKETING_PRESET_NAME = "marketing_v2"` and `MARKETING_PRESET` with groups `attention`, `affect_arousal`, `affect_valence`, `memory`, `reward`, `social`, `cog_clarity`, and `cog_load`.
- Resolver proof in `raw/lint.txt` reports:
  - `configured_terms=51`
  - `unique_configured_terms=51`
  - `duplicates=0`

## AC2

Status: `PASS`

Criterion: The decoder/reference metadata version and Colab reference cache path are changed so old `marketing_v1` reference maps are not silently reused.

Proof:
- `marketing_surface_decoder.py` defines `REFERENCE_VERSION = "marketing_surface_v2"`.
- `run_surface_decoder_colab.ipynb` uses `cache/surface_references/marketing_v2`.
- `raw/test-integration.txt` reports `notebook embedded payloads and cache path PASS`, including assertions that `marketing_v1` is not present in notebook runtime configuration and embedded surface decoder contains `marketing_v2`.

## AC3

Status: `PASS`

Criterion: `marketing_report.py` reflects the new groups in ordering, labels, aliases, explanations, dictionaries, hidden score columns, Excel export, and timeline chart.

Proof:
- `marketing_report.py` updates `GROUP_ORDER`, `GROUP_LABELS`, `GROUP_ALIASES`, `GROUP_EXPLANATIONS`, and `MARKETING_TERMS` for the new 8 groups.
- Existing report rendering functions consume `GROUP_ORDER` and `GROUP_LABELS` for table headers, hidden group score columns, dictionaries, Excel `group_dictionary`, and timeline chart.
- `raw/build.txt` reports `py_compile PASS` for `marketing_report.py`.

## AC4

Status: `PASS`

Criterion: `run_surface_decoder_colab.ipynb` writes the updated embedded project files and uses the new reference cache path.

Proof:
- The notebook base64 constants were refreshed from local `tribe_nimare_interpreter.py`, `marketing_surface_decoder.py`, `marketing_report.py`, and requirements files.
- `raw/test-unit.txt` reports `notebook JSON and code-cell AST parse PASS`.
- `raw/test-integration.txt` reports `notebook embedded payloads and cache path PASS`.

## AC5

Status: `PASS`

Criterion: Verification proves the new preset resolves against Neurosynth term names with zero missing aliases and no duplicate terms, and the unique resolved feature count stays within the configured 60-feature limit.

Proof:
- `raw/lint.txt` fetched live Neurosynth `term_names` and ran the repo `FeatureResolver` against `MARKETING_PRESET`.
- `raw/lint.txt` reports:
  - `resolved_aliases=51`
  - `unique_resolved_features=51`
  - `max_resolved_features=60`
  - `missing_aliases=0`
  - `duplicates=0`

## AC6

Status: `PASS`

Criterion: Existing batch/single-file UI behavior and report ZIP behavior remain intact at the code level.

Proof:
- `run_surface_decoder_colab.ipynb` still contains the existing single-file/folder batch loop and `report_file_output` download behavior.
- `raw/test-unit.txt` validates notebook syntax.
- `raw/test-integration.txt` validates the embedded report and surface decoder payloads after the change.

## Commands

- `python -m py_compile tribe_nimare_interpreter.py marketing_surface_decoder.py marketing_report.py`
  - Exit code: 0
  - Raw output: `raw/build.txt`
- Notebook JSON + AST parse command
  - Exit code: 0
  - Raw output: `raw/test-unit.txt`
- Notebook embedded payload/cache path assertion command
  - Exit code: 0
  - Raw output: `raw/test-integration.txt`
- Neurosynth resolver proof command
  - Exit code: 0
  - Raw output: `raw/lint.txt`
