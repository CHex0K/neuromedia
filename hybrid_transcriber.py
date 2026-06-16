# -*- coding: utf-8 -*-
"""Hybrid word-level transcription for TRIBE events.

The pipeline intentionally separates timing and text quality:

1. GigaAM produces word-level timings.
2. A multimodal OpenRouter model corrects/translates text while preserving IDs.
3. The resulting words are formatted as TRIBE-compatible ``Word`` events.

The correction step is constrained to keep the same IDs and timestamps. This is
important because TRIBE needs timed events, not free-form subtitles.
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd
import requests

VIDEO_EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov", ".webm"}
DEFAULT_GIGAAM_MODEL = "v3_e2e_rnnt"
DEFAULT_OPENROUTER_MODEL = "google/gemini-3.5-flash"
DEFAULT_TARGET_LANGUAGE = "en"
OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"


def run_cmd(cmd: list[str]) -> None:
    """Run a subprocess and raise a useful UTF-8 error on failure."""

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Command failed:\n"
            + " ".join(cmd)
            + "\n\nSTDOUT:\n"
            + result.stdout
            + "\n\nSTDERR:\n"
            + result.stderr
        )


def get_media_duration_sec(path: str | Path) -> float:
    """Return media duration in seconds using ffprobe."""

    path = Path(path)
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return float(result.stdout.strip())


def extract_audio_16k_mono(video_path: str | Path, wav_path: str | Path) -> Path:
    """Extract 16 kHz mono PCM audio from a video file."""

    video_path = Path(video_path)
    wav_path = Path(wav_path)
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    run_cmd(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(wav_path),
        ]
    )
    return wav_path


def extract_audio_segment(
    wav_path: str | Path,
    out_wav_path: str | Path,
    start_sec: float,
    duration_sec: float,
) -> Path:
    """Extract a short WAV segment for GigaAM chunked inference."""

    wav_path = Path(wav_path)
    out_wav_path = Path(out_wav_path)
    out_wav_path.parent.mkdir(parents=True, exist_ok=True)
    run_cmd(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start_sec:.3f}",
            "-t",
            f"{duration_sec:.3f}",
            "-i",
            str(wav_path),
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(out_wav_path),
        ]
    )
    return out_wav_path


def extract_video_segment_for_correction(
    video_path: str | Path,
    out_video_path: str | Path,
    start_sec: float,
    duration_sec: float,
    height: int = 360,
) -> Path:
    """Create a small video clip for the multimodal correction model."""

    video_path = Path(video_path)
    out_video_path = Path(out_video_path)
    out_video_path.parent.mkdir(parents=True, exist_ok=True)
    run_cmd(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start_sec:.3f}",
            "-t",
            f"{duration_sec:.3f}",
            "-i",
            str(video_path),
            "-vf",
            f"scale=-2:{height}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "28",
            "-c:a",
            "aac",
            "-b:a",
            "64k",
            "-movflags",
            "+faststart",
            str(out_video_path),
        ]
    )
    return out_video_path


def get_attr_or_key(obj: Any, name: str, default: Any = None) -> Any:
    """Read an attribute from either an object or a dictionary."""

    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def parse_gigaam_words(result: Any) -> tuple[str, list[dict[str, Any]]]:
    """Parse common GigaAM word timestamp result shapes."""

    full_text = str(get_attr_or_key(result, "text", ""))
    words = get_attr_or_key(result, "words", [])
    parsed: list[dict[str, Any]] = []
    for word in words:
        text = (
            get_attr_or_key(word, "text")
            or get_attr_or_key(word, "word")
            or get_attr_or_key(word, "token")
            or ""
        )
        start = get_attr_or_key(word, "start")
        end = get_attr_or_key(word, "end")
        if start is None or end is None:
            continue
        text = str(text).strip()
        if not text:
            continue
        parsed.append(
            {
                "text": text,
                "start": float(start),
                "end": float(end),
                "score": get_attr_or_key(word, "score"),
            }
        )
    return full_text, parsed


def transcribe_video_with_gigaam_words(
    video_path: str | Path,
    output_dir: str | Path,
    gigaam_model_name: str = DEFAULT_GIGAAM_MODEL,
    chunk_sec: float = 22.0,
    source_language: str = "ru",
) -> pd.DataFrame:
    """Transcribe video audio with GigaAM and preserve word timestamps."""

    try:
        import gigaam
    except ImportError as exc:
        raise RuntimeError(
            "Hybrid transcription requires the optional `gigaam` package. "
            "Install/update requirements before running hybrid mode."
        ) from exc

    video_path = Path(video_path)
    output_dir = Path(output_dir)
    chunks_dir = output_dir / "gigaam_audio_chunks"
    output_dir.mkdir(parents=True, exist_ok=True)
    chunks_dir.mkdir(parents=True, exist_ok=True)

    full_wav_path = output_dir / f"{video_path.stem}.16k.wav"
    extract_audio_16k_mono(video_path, full_wav_path)
    duration = get_media_duration_sec(full_wav_path)
    model = gigaam.load_model(gigaam_model_name)

    rows: list[dict[str, Any]] = []
    word_id = 0
    sequence_id = 0
    start = 0.0
    while start < duration:
        current_duration = min(chunk_sec, duration - start)
        chunk_wav = chunks_dir / f"chunk_{sequence_id:05d}_{start:.3f}.wav"
        extract_audio_segment(full_wav_path, chunk_wav, start, current_duration)
        result = model.transcribe(str(chunk_wav), word_timestamps=True)
        chunk_text, words = parse_gigaam_words(result)

        for word in words:
            global_start = start + float(word["start"])
            global_end = start + float(word["end"])
            rows.append(
                {
                    "id": word_id,
                    "type": "Word",
                    "text": word["text"],
                    "timing_text": word["text"],
                    "original_text": word["text"],
                    "start": global_start,
                    "end": global_end,
                    "duration": max(0.0, global_end - global_start),
                    "sequence_id": sequence_id,
                    "sentence": chunk_text,
                    "language": source_language,
                    "source_language": source_language,
                    "target_language": source_language,
                    "gigaam_score": word.get("score"),
                }
            )
            word_id += 1
        sequence_id += 1
        start += chunk_sec

    df = pd.DataFrame(rows)
    raw_path = output_dir / "gigaam_raw_words.tsv"
    df.to_csv(raw_path, sep="\t", index=False, encoding="utf-8")
    return df


def file_to_data_url(path: str | Path) -> str:
    """Encode a local media file as a data URL for OpenRouter."""

    path = Path(path)
    mime_type, _ = mimetypes.guess_type(str(path))
    if mime_type is None:
        mime_type = "video/mp4"
    payload = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime_type};base64,{payload}"


def extract_json_object(text: str) -> dict[str, Any]:
    """Extract a JSON object from a model response."""

    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"^```\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def make_word_windows(
    words_df: pd.DataFrame,
    max_words: int = 80,
    max_seconds: float = 20.0,
) -> list[pd.DataFrame]:
    """Group words into bounded correction windows."""

    windows: list[pd.DataFrame] = []
    current_rows: list[dict[str, Any]] = []
    current_start: float | None = None
    for _, row in words_df.sort_values("start").iterrows():
        if current_start is None:
            current_start = float(row["start"])
        too_many = len(current_rows) >= max_words
        too_long = float(row["end"]) - current_start > max_seconds
        if current_rows and (too_many or too_long):
            windows.append(pd.DataFrame(current_rows))
            current_rows = []
            current_start = float(row["start"])
        current_rows.append(row.to_dict())
    if current_rows:
        windows.append(pd.DataFrame(current_rows))
    return windows


def target_language_instruction(target_language: str) -> str:
    """Return concise instruction text for the correction target language."""

    normalized = target_language.strip().lower()
    if normalized in {"en", "english"}:
        return (
            "Return corrected_text in English. Translate each item as well as "
            "possible while preserving the same item count and IDs."
        )
    if normalized in {"ru", "russian"}:
        return "Return corrected_text in Russian. Do not translate to English."
    return (
        f"Return corrected_text in the target language `{target_language}` while "
        "preserving the same item count and IDs."
    )


def call_openrouter_word_corrector(
    video_clip_path: str | Path,
    words: list[dict[str, Any]],
    target_language: str,
    api_key: str | None = None,
    model: str = DEFAULT_OPENROUTER_MODEL,
    temperature: float = 0.0,
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """Ask an OpenRouter multimodal model to correct/translate word text."""

    api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is required for hybrid transcription correction."
        )

    compact_words = [
        {
            "id": int(word["id"]),
            "start": round(float(word["start"]), 3),
            "end": round(float(word["end"]), 3),
            "text": str(word["text"]),
        }
        for word in words
    ]
    prompt = f"""
You are an ASR correction and translation editor.

Input:
1. A short video clip with audio.
2. A list of GigaAM-recognized words with id/start/end/text.

Task:
Correct obvious ASR mistakes and output the text in the selected target language.

Target language:
{target_language_instruction(target_language)}

Critical rules:
- Return exactly the same number of items as the input list.
- Return the same ids in the same order.
- Do not change start/end timing.
- Do not add words.
- Do not delete words.
- Do not split one id into multiple ids.
- Do not merge several ids into one id.
- If unsure, keep the source meaning close and use the original text.
- corrected_text may be a short translated token or phrase, but must stay aligned
  to that same id.
- Do not describe the visual scene.

Input words:
{json.dumps(compact_words, ensure_ascii=False, indent=2)}

Return JSON only:
{{
  "items": [
    {{
      "id": 0,
      "corrected_text": "word",
      "action": "keep|replace|translate",
      "confidence": 0.0,
      "reason": "brief reason"
    }}
  ]
}}
""".strip()

    schema = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "corrected_text": {"type": "string"},
                        "action": {
                            "type": "string",
                            "enum": ["keep", "replace", "translate"],
                        },
                        "confidence": {"type": "number"},
                        "reason": {"type": "string"},
                    },
                    "required": [
                        "id",
                        "corrected_text",
                        "action",
                        "confidence",
                        "reason",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    }
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "video_url",
                        "video_url": {"url": file_to_data_url(video_clip_path)},
                    },
                ],
            }
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "word_corrections",
                "strict": True,
                "schema": schema,
            },
        },
    }
    response = requests.post(
        OPENROUTER_CHAT_COMPLETIONS_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=300,
    )
    if response.status_code != 200:
        raise RuntimeError(f"OpenRouter error {response.status_code}:\n{response.text}")
    content = response.json()["choices"][0]["message"]["content"]
    parsed = extract_json_object(content)
    parsed["_raw_model_text"] = content
    return parsed


def validate_and_index_corrections(
    corrections: dict[str, Any],
    expected_ids: list[int],
) -> dict[int, dict[str, Any]]:
    """Validate model output preserves the exact input IDs and order."""

    items = corrections.get("items", [])
    returned_ids = [int(item["id"]) for item in items if "id" in item]
    if returned_ids != expected_ids:
        missing = sorted(set(expected_ids) - set(returned_ids))
        extra = sorted(set(returned_ids) - set(expected_ids))
        raise ValueError(
            "Correction model returned wrong ids or order. "
            f"Expected first ids={expected_ids[:20]}, got first ids={returned_ids[:20]}, "
            f"Missing={missing[:20]}, Extra={extra[:20]}"
        )
    by_id: dict[int, dict[str, Any]] = {}
    for item in items:
        by_id[int(item["id"])] = item
    return by_id


def join_words(words: list[str]) -> str:
    """Join corrected words while avoiding spaces before punctuation."""

    text = " ".join(str(word).strip() for word in words if str(word).strip())
    text = re.sub(r"\s+([,.;:!?%)»])", r"\1", text)
    text = re.sub(r"([«(])\s+", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def rebuild_sentences_for_tribe(words_df: pd.DataFrame) -> pd.DataFrame:
    """Rebuild the per-word sentence/context field for TRIBE text features."""

    df = words_df.copy()
    sequence_to_sentence: dict[Any, str] = {}
    for sequence_id, group in df.groupby("sequence_id", sort=True):
        sentence = join_words(group.sort_values("start")["text"].astype(str).tolist())
        sequence_to_sentence[sequence_id] = sentence
    df["sentence"] = df["sequence_id"].map(sequence_to_sentence)
    df["duration"] = df["end"] - df["start"]
    return df


def correct_words_with_openrouter(
    video_path: str | Path,
    words_df: pd.DataFrame,
    output_dir: str | Path,
    target_language: str = DEFAULT_TARGET_LANGUAGE,
    api_key: str | None = None,
    model: str = DEFAULT_OPENROUTER_MODEL,
    max_words_per_request: int = 80,
    max_seconds_per_request: float = 20.0,
    context_pad_sec: float = 0.7,
    min_replace_confidence: float = 0.55,
    save_debug_json: bool = True,
) -> pd.DataFrame:
    """Correct and optionally translate GigaAM words with OpenRouter."""

    video_path = Path(video_path)
    output_dir = Path(output_dir)
    clips_dir = output_dir / "correction_video_clips"
    debug_dir = output_dir / "correction_debug"
    clips_dir.mkdir(parents=True, exist_ok=True)
    debug_dir.mkdir(parents=True, exist_ok=True)

    corrected_df = words_df.copy()
    if "original_text" not in corrected_df.columns:
        corrected_df["original_text"] = corrected_df["text"]
    corrected_df["target_language"] = target_language
    corrected_df["correction_action"] = "not_processed"
    corrected_df["correction_confidence"] = None
    corrected_df["correction_reason"] = ""

    windows = make_word_windows(
        corrected_df,
        max_words=max_words_per_request,
        max_seconds=max_seconds_per_request,
    )
    video_duration = get_media_duration_sec(video_path)

    for window_idx, window_df in enumerate(windows):
        expected_ids = [int(value) for value in window_df["id"].tolist()]
        start_sec = max(0.0, float(window_df["start"].min()) - context_pad_sec)
        end_sec = min(video_duration, float(window_df["end"].max()) + context_pad_sec)
        duration_sec = max(0.1, end_sec - start_sec)
        clip_path = clips_dir / f"clip_{window_idx:05d}_{start_sec:.3f}_{end_sec:.3f}.mp4"
        extract_video_segment_for_correction(
            video_path=video_path,
            out_video_path=clip_path,
            start_sec=start_sec,
            duration_sec=duration_sec,
        )
        corrections = call_openrouter_word_corrector(
            video_clip_path=clip_path,
            words=window_df.to_dict("records"),
            target_language=target_language,
            api_key=api_key,
            model=model,
        )
        if save_debug_json:
            debug_path = debug_dir / f"corrections_{window_idx:05d}.json"
            debug_path.write_text(
                json.dumps(corrections, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        by_id = validate_and_index_corrections(corrections, expected_ids)
        for word_id in expected_ids:
            item = by_id[word_id]
            row_mask = corrected_df["id"] == word_id
            original_text = str(corrected_df.loc[row_mask, "text"].iloc[0])
            corrected_text = str(item.get("corrected_text", "")).strip()
            action = str(item.get("action", "keep")).strip()
            confidence = float(item.get("confidence", 0.0))
            reason = str(item.get("reason", "")).strip()
            should_replace = (
                action in {"replace", "translate"}
                and confidence >= min_replace_confidence
                and bool(corrected_text)
            )
            corrected_df.loc[row_mask, "text"] = (
                corrected_text if should_replace else original_text
            )
            corrected_df.loc[row_mask, "correction_action"] = (
                action if should_replace else "keep"
            )
            corrected_df.loc[row_mask, "correction_confidence"] = confidence
            corrected_df.loc[row_mask, "correction_reason"] = reason

    corrected_df = rebuild_sentences_for_tribe(corrected_df)
    out_path = output_dir / "gigaam_openrouter_corrected_words.tsv"
    corrected_df.to_csv(out_path, sep="\t", index=False, encoding="utf-8")
    return corrected_df


def make_tribe_events_dataframe(corrected_df: pd.DataFrame) -> pd.DataFrame:
    """Return a minimal TRIBE-compatible ``Word`` events DataFrame."""

    required = ["type", "text", "start", "duration", "sequence_id", "sentence", "language"]
    missing = [column for column in required if column not in corrected_df.columns]
    if missing:
        raise ValueError(f"Corrected transcript is missing columns: {missing}")
    return corrected_df[required].copy()


def transcribe_video_for_tribe(
    video_path: str | Path,
    output_dir: str | Path,
    gigaam_model_name: str = DEFAULT_GIGAAM_MODEL,
    openrouter_model: str = DEFAULT_OPENROUTER_MODEL,
    openrouter_api_key: str | None = None,
    source_language: str = "ru",
    target_language: str = DEFAULT_TARGET_LANGUAGE,
    gigaam_chunk_sec: float = 22.0,
    max_words_per_request: int = 80,
    max_seconds_per_request: float = 20.0,
    min_replace_confidence: float = 0.55,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the full hybrid transcription pipeline for one video."""

    video_path = Path(video_path)
    if video_path.suffix.lower() not in VIDEO_EXTENSIONS:
        raise ValueError(
            "Hybrid transcription currently supports video inputs only; got "
            f"{video_path}"
        )
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_df = transcribe_video_with_gigaam_words(
        video_path=video_path,
        output_dir=output_dir,
        gigaam_model_name=gigaam_model_name,
        chunk_sec=gigaam_chunk_sec,
        source_language=source_language,
    )
    corrected_df = correct_words_with_openrouter(
        video_path=video_path,
        words_df=raw_df,
        output_dir=output_dir,
        target_language=target_language,
        api_key=openrouter_api_key,
        model=openrouter_model,
        max_words_per_request=max_words_per_request,
        max_seconds_per_request=max_seconds_per_request,
        min_replace_confidence=min_replace_confidence,
    )
    tribe_df = make_tribe_events_dataframe(corrected_df)
    corrected_df.to_csv(
        output_dir / "corrected_full_debug.tsv",
        sep="\t",
        index=False,
        encoding="utf-8",
    )
    tribe_df.to_csv(
        output_dir / "tribe_word_events.tsv",
        sep="\t",
        index=False,
        encoding="utf-8",
    )
    return corrected_df, tribe_df


def parse_args() -> argparse.Namespace:
    """Parse CLI args for standalone transcription debugging."""

    parser = argparse.ArgumentParser(description="Hybrid GigaAM/OpenRouter transcription.")
    parser.add_argument("video", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("hybrid_out"))
    parser.add_argument("--gigaam-model", default=DEFAULT_GIGAAM_MODEL)
    parser.add_argument("--openrouter-model", default=DEFAULT_OPENROUTER_MODEL)
    parser.add_argument("--source-language", default="ru")
    parser.add_argument("--target-language", default=DEFAULT_TARGET_LANGUAGE)
    parser.add_argument("--gigaam-chunk-sec", type=float, default=22.0)
    parser.add_argument("--max-words-per-request", type=int, default=80)
    parser.add_argument("--max-seconds-per-request", type=float, default=20.0)
    parser.add_argument("--min-replace-confidence", type=float, default=0.55)
    return parser.parse_args()


def main() -> None:
    """CLI entrypoint."""

    args = parse_args()
    _, tribe_df = transcribe_video_for_tribe(
        video_path=args.video,
        output_dir=args.output_dir,
        gigaam_model_name=args.gigaam_model,
        openrouter_model=args.openrouter_model,
        source_language=args.source_language,
        target_language=args.target_language,
        gigaam_chunk_sec=args.gigaam_chunk_sec,
        max_words_per_request=args.max_words_per_request,
        max_seconds_per_request=args.max_seconds_per_request,
        min_replace_confidence=args.min_replace_confidence,
    )
    print(f"Saved TRIBE word events: {args.output_dir / 'tribe_word_events.tsv'}")
    print(f"Rows: {len(tribe_df)}")


if __name__ == "__main__":
    main()
