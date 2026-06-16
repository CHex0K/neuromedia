# Evidence Bundle: hybrid-transcription

## Summary
- Overall status: PASS
- Last updated: 2026-06-15T12:30:00+03:00
- Scope verified: local source, notebook embedded payloads, static integration, and unit-style validation of strict correction ID/order handling.

## Acceptance Criteria Evidence

### AC1
- Status: PASS
- Criterion: Add a repo-local hybrid transcription implementation based on `new_transc.txt` that uses GigaAM for word timings and an OpenRouter multimodal correction model for text correction/translation.
- Proof:
  - `hybrid_transcriber.py` implements GigaAM word timing, OpenRouter multimodal correction, video clip extraction, and TRIBE word-event formatting.
  - `requirements.txt` includes `gigaam==0.1.0` and `requests>=2.31,<3`.
  - `.agent/tasks/hybrid-transcription/raw/build.txt` shows `python -m py_compile` passed for `hybrid_transcriber.py`.

### AC2
- Status: PASS
- Criterion: The hybrid pipeline must preserve word-level `start`, `end`, and `duration` from the timing model and must not let the correction/translation model add, remove, split, or reorder word IDs.
- Proof:
  - `hybrid_transcriber.py` keeps timing fields from GigaAM and only changes `text` after correction.
  - `validate_and_index_corrections()` now enforces exact returned ID order, not only set equality.
  - `.agent/tasks/hybrid-transcription/raw/test-unit.txt` proves correct order passes and wrong order raises.

### AC3
- Status: PASS
- Criterion: The correction model must support a configurable target language, including English (`en`), so corrected text can be translated before being passed to TRIBE.
- Proof:
  - `hybrid_transcriber.py` includes `target_language_instruction()` and `target_language` arguments through the correction pipeline.
  - `tribe_nimare_interpreter.py` exposes `--transcript-target-language`.
  - `run_surface_decoder_colab.ipynb` exposes `transcript_target_language_input`.
  - `.agent/tasks/hybrid-transcription/raw/test-unit.txt` validates English and Russian target-language instructions.

### AC4
- Status: PASS
- Criterion: `tribe_nimare_interpreter.py` must support an explicit transcription backend option. When hybrid mode is selected, it must avoid TRIBE's default WhisperX path and fail clearly if required dependencies or API credentials are missing.
- Proof:
  - `tribe_nimare_interpreter.py` exposes `--transcript-backend {tribe,hybrid}`.
  - Hybrid mode requires `OPENROUTER_API_KEY` and raises a clear error if missing.
  - Hybrid mode imports `hybrid_transcriber.transcribe_video_for_tribe`.
  - Hybrid preprocessing uses `ExtractAudioFromVideo`, `ChunkEvents`, `AddText`, `AddSentenceToWords`, `AddContextToWords`, and `RemoveMissing`; it does not call `ExtractWordsFromAudio`.
  - `.agent/tasks/hybrid-transcription/raw/lint.txt` asserts `ExtractWordsFromAudio` is absent from `tribe_nimare_interpreter.py` and no `--openrouter-api-key` CLI secret exists.

### AC5
- Status: PASS
- Criterion: Hybrid mode must preserve video and audio modalities for TRIBE inference. It may replace only the word/text events, not degrade the run to text-only inference.
- Proof:
  - `prepare_hybrid_transcript_events()` creates a `Video` media event, adds hybrid `Word` events, extracts audio from the video, chunks both `Audio` and `Video`, and then applies TRIBE-compatible text/context transforms.
  - `.agent/tasks/hybrid-transcription/raw/lint.txt` asserts `ExtractAudioFromVideo()`, `AddText()`, and `AddContextToWords` are present in the hybrid integration.

### AC6
- Status: PASS
- Criterion: The Colab/Gradio notebook must expose the hybrid transcription controls, pass them into the TRIBE run, write the new project file to `/content/neuromedia`, and include the corrected transcript in downloadable/report artifacts where practical.
- Proof:
  - `run_surface_decoder_colab.ipynb` has OpenRouter key, backend, target-language, GigaAM model, and OpenRouter model UI controls.
  - The notebook writes `hybrid_transcriber.py` into `/content/neuromedia`.
  - The notebook passes `--transcript-backend`, `--transcript-target-language`, `--gigaam-model`, and `--openrouter-model` to `tribe_nimare_interpreter.py`.
  - `marketing_report.py` loads `tribe_dir / "tribe_transcript.tsv"` before sidecar transcript files.
  - `.agent/tasks/hybrid-transcription/raw/test-integration.txt` confirms notebook markers and payloads.

### AC7
- Status: PASS
- Criterion: The project must keep UTF-8 handling explicit and update embedded notebook base64 payloads so Colab runs the same code as the local repo.
- Proof:
  - Modified Python files start with `# -*- coding: utf-8 -*-`.
  - New and modified text reads/writes specify `encoding="utf-8"`.
  - `.agent/tasks/hybrid-transcription/raw/test-integration.txt` confirms all notebook base64 payloads decode exactly to the current local files.
  - `.agent/tasks/hybrid-transcription/raw/lint.txt` checks UTF-8 headers.

## Commands Run
- `python -m py_compile tribe_nimare_interpreter.py hybrid_transcriber.py marketing_report.py marketing_surface_decoder.py .agent\tasks\hybrid-transcription\raw\notebook_cell_1.py`
- Unit-style Python check for `hybrid_transcriber.validate_and_index_corrections()` and target-language instructions.
- Notebook integration Python check for AST parse, UI/CLI markers, and base64 payload equality.
- Static lint Python check for UTF-8 headers, hybrid backend markers, no `ExtractWordsFromAudio` in hybrid integration, and no OpenRouter CLI secret flag.

## Raw Artifacts
- `.agent/tasks/hybrid-transcription/raw/build.txt`
- `.agent/tasks/hybrid-transcription/raw/test-unit.txt`
- `.agent/tasks/hybrid-transcription/raw/test-integration.txt`
- `.agent/tasks/hybrid-transcription/raw/lint.txt`

## Known Gaps / Residual Risk
- No live Colab/GPU run was performed in this local verification pass.
- No live GigaAM inference or OpenRouter request was performed because that requires model downloads, media input, and API credentials.
