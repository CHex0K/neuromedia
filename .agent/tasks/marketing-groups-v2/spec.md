# Task Spec: marketing-groups-v2

## Metadata
- Task ID: marketing-groups-v2
- Created: 2026-06-12T06:14:14+00:00
- Repo root: D:\Projects\Projects_Python\Media\neuromedia
- Working directory at init: D:\Projects\Projects_Python\Media\neuromedia

## Guidance sources
- User-provided AGENTS.md instructions from session context: UTF-8 only, PEP8 for Python, Python files must keep `# -*- coding: utf-8 -*-`.
- Repo proof-loop skill: `.agents/skills/repo-task-proof-loop/SKILL.md`.

## Original task statement
Replace current marketing decoder groups with the provided existing Neurosynth term dictionary, remove duplicate terms, rebuild references under a new cache version/path so new terms are downloaded/built, and update reports/notebook accordingly.

## Acceptance criteria
- AC1: `marketing_surface_decoder.py` uses the new 8-group marketing preset with these internal groups and terms, with no term duplicated across groups:
  - `attention`: attention, visual attention, attentional, orienting, target detection, salience, visual stimuli, distractor
  - `affect_arousal`: arousal, affective, emotional, emotional stimuli, emotional responses
  - `affect_valence`: valence, negative affect, disgust, fear, anxiety
  - `memory`: encoding, subsequent memory, episodic memory, semantic memory, recall, recognition, familiarity
  - `reward`: reward, reward anticipation, motivation, value, incentive, preference, approach, monetary reward, craving
  - `social`: social cognition, mentalizing, theory mind, face, gaze, self referential, empathy, social
  - `cog_clarity`: language, semantic, sentence comprehension, comprehension
  - `cog_load`: working memory, cognitive control, executive function, inhibition, task difficulty
- AC2: The decoder/reference metadata version and Colab reference cache path are changed so old `marketing_v1` reference maps are not silently reused for the new preset.
- AC3: `marketing_report.py` reflects the new groups in ordering, labels, aliases, explanations, dictionaries, hidden score columns, Excel export, and timeline chart.
- AC4: `run_surface_decoder_colab.ipynb` writes the updated embedded project files and uses the new reference cache path.
- AC5: Verification proves the new preset resolves against Neurosynth term names with zero missing aliases and no duplicate terms, and the unique resolved feature count stays within the configured 60-feature limit.
- AC6: Existing batch/single-file UI behavior and report ZIP behavior remain intact at the code level.

## Constraints
- Keep all file reads/writes UTF-8.
- Keep Python source files with explicit UTF-8 encoding headers.
- Do not reintroduce full Neurosynth/NiMARE runtime decoding.
- Do not change the TRIBE multimodal behavior.
- Do not run a full Colab/TRIBE job locally.
- Keep changes scoped to decoder/report/notebook configuration and proof artifacts.

## Non-goals
- No redesign of the Gradio UI beyond labels/cache path needed for the new preset.
- No change to TRIBE model dependencies or inference logic.
- No attempt to generate or download large reference map artifacts in the local repo.

## Verification plan
- Build: `python -m py_compile tribe_nimare_interpreter.py marketing_surface_decoder.py marketing_report.py`
- Notebook syntax: parse `run_surface_decoder_colab.ipynb` as JSON and AST-parse code cells.
- Resolver check: fetch Neurosynth `term_names` and run the repo's `FeatureResolver` on the new preset; assert zero missing aliases, zero duplicate configured terms, and `unique_count <= 60`.
- Static checks: confirm notebook cache path references the new preset path, and no stale `marketing_v1` cache path remains in the notebook runtime configuration.
