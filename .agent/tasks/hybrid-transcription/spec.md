# Task Spec: hybrid-transcription

## Metadata
- Task ID: hybrid-transcription
- Created: 2026-06-15
- Repo root: D:\Projects\Projects_Python\Media\neuromedia

## Original Task Statement
Replace the TRIBE/WhisperX transcription path with a hybrid transcription pipeline based on `new_transc.txt`: one model for word timings, another model for text correction, and an added option to translate corrected text to English or another selected target language. Integrate this system instead of WhisperX while preserving all TRIBE modalities.

## Acceptance Criteria
- AC1: Add a repo-local hybrid transcription implementation based on `new_transc.txt` that uses GigaAM for word timings and an OpenRouter multimodal correction model for text correction/translation.
- AC2: The hybrid pipeline must preserve word-level `start`, `end`, and `duration` from the timing model and must not let the correction/translation model add, remove, split, or reorder word IDs.
- AC3: The correction model must support a configurable target language, including English (`en`), so corrected text can be translated before being passed to TRIBE.
- AC4: `tribe_nimare_interpreter.py` must support an explicit transcription backend option. When hybrid mode is selected, it must avoid TRIBE's default WhisperX path and fail clearly if required dependencies or API credentials are missing.
- AC5: Hybrid mode must preserve video and audio modalities for TRIBE inference. It may replace only the word/text events, not degrade the run to text-only inference.
- AC6: The Colab/Gradio notebook must expose the hybrid transcription controls, pass them into the TRIBE run, write the new project file to `/content/neuromedia`, and include the corrected transcript in downloadable/report artifacts where practical.
- AC7: The project must keep UTF-8 handling explicit and update embedded notebook base64 payloads so Colab runs the same code as the local repo.

## Constraints
- Use UTF-8 for all files and text reads/writes.
- Python source files created or modified for this task must start with `# -*- coding: utf-8 -*-`.
- Do not silently fall back from hybrid transcription to WhisperX when hybrid mode is selected.
- Do not remove the old TRIBE/WhisperX path entirely; keep it as an explicit selectable backend for compatibility/debugging.
- Do not persist OpenRouter API keys to repository files, notebooks, reports, logs, or command-line arguments.
- Keep changes scoped to transcription integration and required notebook/report wiring.

## Non-Goals
- Do not train or fine-tune TRIBE, GigaAM, Gemini, or any decoder model.
- Do not guarantee that token-level translation is linguistically perfect; timing preservation takes priority over free-form translation quality.
- Do not redesign the surface decoder or marketing report scoring logic.
- Do not implement a non-OpenRouter correction provider unless needed for a local test seam.

## Verification Plan
- Build: compile modified Python files with `python -m py_compile`.
- Unit-style checks: run AST/import-light checks for the hybrid module without requiring GigaAM/OpenRouter calls.
- Integration checks: verify `tribe_nimare_interpreter.py --help` exposes the new transcription options and that notebook embedded payloads contain the updated files.
- Lint/static checks: inspect for accidental WhisperX fallback in hybrid path and for API key leakage through CLI args.
- Manual checks: verify Gradio has backend, target-language, model, and OpenRouter token controls.
