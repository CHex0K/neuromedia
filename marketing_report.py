# -*- coding: utf-8 -*-
"""Generate a self-contained HTML report for TRIBE surface decoder outputs."""

from __future__ import annotations

import argparse
import base64
import html
import json
import logging
import subprocess
import tempfile
import wave
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

LOGGER = logging.getLogger("marketing_report")

FSAVERAGE5_TOTAL_VERTICES = 20484
SEGMENT_MAP_ID = "tribe_predictions_fsaverage5"
AGGREGATE_MAP_ID = "tribe_activity_fsaverage5"
GROUP_ORDER = [
    "attention",
    "reward",
    "memory",
    "emotion",
    "social",
    "aversion",
    "language",
    "action",
]
GROUP_LABELS = {
    "attention": "attention_salience",
    "reward": "reward_value",
    "memory": "memory_encoding",
    "emotion": "emotion_affect",
    "social": "social_self",
    "aversion": "aversion_risk",
    "language": "language_narrative",
    "action": "action_embodiment",
}
GROUP_ALIASES = {
    "attention_salience": "attention",
    "reward_value": "reward",
    "memory_encoding": "memory",
    "emotion_affect": "emotion",
    "social_self": "social",
    "aversion_risk": "aversion",
    "language_narrative": "language",
    "action_embodiment": "action",
}
GROUP_EXPLANATIONS = {
    "attention": {
        "meaning": (
            "Внимание и выделение значимого стимула. Группа объединяет карты задач, "
            "где участник должен заметить цель, переключить фокус, обработать визуально "
            "важный сигнал или среагировать на salient cue."
        ),
        "high_score": (
            "Сегмент похож на паттерны задач с фокусом внимания: заметный объект, "
            "контраст, крупный текст, смена сцены, указание на цель или визуальный акцент."
        ),
        "marketing": (
            "Полезно читать как proxy для способности фрагмента зацепить и удержать фокус. "
            "Это не равно интересу или покупке."
        ),
    },
    "reward": {
        "meaning": (
            "Ценность, мотивация и вознаграждение. Группа связана с картами задач про "
            "reward, value, preference, incentive и reinforcement."
        ),
        "high_score": (
            "Сегмент похож на паттерны оценки выгоды или привлекательности: цена, скидка, "
            "выгода, желательность продукта, обещание результата."
        ),
        "marketing": (
            "Можно читать как proxy для ценностного предложения: насколько фрагмент похож "
            "на нейрокогнитивные карты оценки value/reward."
        ),
    },
    "memory": {
        "meaning": (
            "Кодирование и узнавание информации. Группа объединяет memory, encoding, "
            "recognition, recall, retrieval, episodic и familiarity."
        ),
        "high_score": (
            "Сегмент похож на паттерны запоминания или узнавания: повтор бренда, "
            "понятный объект, знакомый образ, структурированный факт или легко кодируемое сообщение."
        ),
        "marketing": (
            "Можно читать как proxy для потенциальной запоминаемости элемента, но не как "
            "гарантию, что зритель реально вспомнит рекламу."
        ),
    },
    "emotion": {
        "meaning": (
            "Эмоциональная окраска и аффективная обработка. Группа связана с emotion, "
            "affective, arousal, valence, pleasant и unpleasant."
        ),
        "high_score": (
            "Сегмент похож на паттерны эмоциональной оценки: выразительный тон, "
            "аффективный образ, приятность/неприятность, эмоциональный контраст."
        ),
        "marketing": (
            "Можно читать как proxy для эмоциональной насыщенности фрагмента, без вывода "
            "о конкретной эмоции зрителя."
        ),
    },
    "social": {
        "meaning": (
            "Социальная и self/other обработка. Группа включает social, mentalizing, "
            "self referential, people, face/faces и theory of mind."
        ),
        "high_score": (
            "Сегмент похож на паттерны обработки людей, лиц, социального контекста, "
            "персонажей, обращения к себе или понимания намерений."
        ),
        "marketing": (
            "Можно читать как proxy для социальной вовлечённости или человекоцентричности "
            "фрагмента. Термин face не означает, что detector нашёл лицо в кадре."
        ),
    },
    "aversion": {
        "meaning": (
            "Негативная значимость, угроза и избегание. Группа связана с fear, threat, "
            "anxiety, pain, disgust, negative и aversive."
        ),
        "high_score": (
            "Сегмент похож на паттерны настороженности или негативной оценки: риск, "
            "опасность, дискомфорт, проблема, боль, неприятный контраст."
        ),
        "marketing": (
            "Можно читать как proxy для проблематизации или напряжения. Высокий score "
            "не обязательно плохо: иногда это механизм привлечения внимания к боли клиента."
        ),
    },
    "language": {
        "meaning": (
            "Речь, текст и смысловая обработка. Группа объединяет language, speech, "
            "semantic, comprehension, narrative, story и sentence."
        ),
        "high_score": (
            "Сегмент похож на паттерны понимания речи/текста: озвучка, субтитры, "
            "слоган, объяснение, история, смысловой блок."
        ),
        "marketing": (
            "Можно читать как proxy для смысловой нагрузки: насколько фрагмент несёт "
            "сообщение, которое требует языковой или нарративной обработки."
        ),
    },
    "action": {
        "meaning": (
            "Действие, движение и телесная/моторная обработка. Группа включает action, "
            "motor, movement, hand, gesture и execution."
        ),
        "high_score": (
            "Сегмент похож на паттерны наблюдения или представления действия: руки, "
            "жесты, движение, демонстрация использования продукта, операция с объектом."
        ),
        "marketing": (
            "Можно читать как proxy для демонстрационности и embodied response: "
            "насколько фрагмент показывает, что с продуктом делают."
        ),
    },
}
MARKETING_TERMS = {
    "attention": ["attention", "attentional", "salience", "orienting", "target", "visual attention"],
    "reward": ["reward", "value", "valuation", "incentive", "motivation", "preference", "reinforcement"],
    "memory": ["memory", "encoding", "recall", "recognition", "episodic", "retrieval", "familiarity"],
    "emotion": ["emotion", "emotional", "affective", "affect", "arousal", "valence", "pleasant", "unpleasant"],
    "social": ["social", "mentalizing", "self", "self referential", "person", "people", "face", "faces", "theory of mind"],
    "aversion": ["fear", "threat", "anxiety", "pain", "disgust", "negative", "aversive"],
    "language": ["language", "speech", "semantic", "comprehension", "narrative", "story", "sentence"],
    "action": ["action", "motor", "movement", "hand", "gesture", "execution"],
}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov", ".webm"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".mp4", ".avi", ".mkv", ".mov", ".webm"}
TEXT_COLUMN_CANDIDATES = [
    "text",
    "word",
    "words",
    "transcript",
    "sentence",
    "utterance",
    "caption",
    "label",
    "annotation",
]
START_COLUMN_CANDIDATES = ["start", "onset", "offset", "time", "timestamp", "begin", "start_time"]
END_COLUMN_CANDIDATES = ["end", "stop", "end_time", "finish"]
DURATION_COLUMN_CANDIDATES = ["duration", "dur"]
MAX_AUDIO_SECONDS = 30.0


def configure_logging() -> None:
    """Configure process logging."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description="Build a downloadable HTML report from TRIBE and surface decoder outputs."
    )
    parser.add_argument("--tribe-dir", type=Path, required=True)
    parser.add_argument("--surface-dir", type=Path, required=True)
    parser.add_argument("--output-html", type=Path, required=True)
    parser.add_argument("--input-media", type=Path)
    parser.add_argument("--title", default="TRIBE v2 surface marketing report")
    parser.add_argument("--top-terms", type=int, default=5)
    parser.add_argument("--top-groups", type=int, default=3)
    return parser.parse_args()


def load_predictions(tribe_dir: Path) -> tuple[np.ndarray, np.ndarray | None]:
    """Load TRIBE segment-level and whole-video surface maps."""

    predictions_path = tribe_dir / "tribe_predictions_fsaverage5.npy"
    activity_path = tribe_dir / "tribe_activity_fsaverage5.npy"
    if not predictions_path.is_file():
        raise FileNotFoundError(f"TRIBE predictions not found: {predictions_path}")

    predictions = np.load(predictions_path).astype(np.float32)
    if predictions.ndim != 2 or predictions.shape[1] != FSAVERAGE5_TOTAL_VERTICES:
        raise ValueError(
            "TRIBE predictions must have shape (T, 20484), "
            f"got {predictions.shape}: {predictions_path}"
        )

    activity = None
    if activity_path.is_file():
        activity = np.load(activity_path).astype(np.float32)
        if activity.shape != (FSAVERAGE5_TOTAL_VERTICES,):
            raise ValueError(
                "TRIBE aggregate activity must have shape (20484,), "
                f"got {activity.shape}: {activity_path}"
            )

    return predictions, activity


def load_decoder_tables(surface_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Load decoder output tables."""

    scores_path = surface_dir / "marketing_scores.csv"
    terms_path = surface_dir / "decoded_terms.csv"
    report_path = surface_dir / "report.json"
    missing = [path for path in (scores_path, terms_path, report_path) if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing decoder outputs: " + ", ".join(str(path) for path in missing))

    scores = pd.read_csv(scores_path)
    terms = pd.read_csv(terms_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if scores.empty:
        raise RuntimeError(f"Marketing scores are empty: {scores_path}")
    if terms.empty:
        raise RuntimeError(f"Decoded terms are empty: {terms_path}")
    return scores, terms, report


def load_segments(tribe_dir: Path) -> pd.DataFrame:
    """Load optional segment metadata saved by TRIBE."""

    segments_path = tribe_dir / "tribe_segments.tsv"
    if not segments_path.is_file():
        return pd.DataFrame()
    return pd.read_csv(segments_path, sep="\t")


def load_sidecar_transcript(input_media: Path | None) -> pd.DataFrame:
    """Load transcript/caption text from a sidecar file next to the input media."""

    if input_media is None:
        return pd.DataFrame()

    candidates = [
        input_media.with_suffix(".tsv"),
        input_media.with_suffix(".csv"),
        input_media.with_suffix(".txt"),
    ]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            if path.suffix.lower() == ".tsv":
                return pd.read_csv(path, sep="\t")
            if path.suffix.lower() == ".csv":
                return pd.read_csv(path)
            return pd.DataFrame({"text": [path.read_text(encoding="utf-8")]})
        except Exception as exc:
            LOGGER.warning("Could not read sidecar transcript %s: %s", path, exc)
    return pd.DataFrame()


def escape(value: Any) -> str:
    """HTML-escape a value."""

    if pd.isna(value):
        return ""
    return html.escape(str(value), quote=True)


def fmt_float(value: Any, digits: int = 2) -> str:
    """Format a numeric value for report tables."""

    try:
        if pd.isna(value):
            return ""
        return f"{float(value):.{digits}f}"
    except Exception:
        return escape(value)


def normalize_group(value: Any) -> str:
    """Normalize legacy and current marketing group names to decoder keys."""

    group = str(value)
    return GROUP_ALIASES.get(group, group)


def patch_exca_no_value_compat() -> None:
    """Restore the exca API path expected by neuralset 0.0.2."""

    try:
        from exca.steps import base, identity
    except Exception as exc:
        LOGGER.warning("Could not inspect exca compatibility: %s", exc)
        return

    if not hasattr(base, "NoValue") and hasattr(identity, "NoValue"):
        base.NoValue = identity.NoValue
        LOGGER.info("Patched exca.steps.base.NoValue from exca.steps.identity.NoValue.")


def normalize_column_name(value: Any) -> str:
    """Normalize a dataframe column name for loose matching."""

    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def find_column(frame: pd.DataFrame, candidates: list[str]) -> str | None:
    """Find the first dataframe column matching a list of normalized names."""

    by_normalized = {normalize_column_name(column): str(column) for column in frame.columns}
    for candidate in candidates:
        column = by_normalized.get(normalize_column_name(candidate))
        if column is not None:
            return column
    return None


def safe_float(value: Any, default: float | None = None) -> float | None:
    """Convert a scalar value to float, returning default on invalid input."""

    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def png_data_uri(png_bytes: bytes) -> str:
    """Return a data URI for PNG bytes."""

    encoded = base64.b64encode(png_bytes).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def render_surface_png(surface: np.ndarray, title: str) -> bytes:
    """Render one fsaverage5 surface map as PNG bytes."""

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    try:
        patch_exca_no_value_compat()
        from tribev2.plotting.cortical import PlotBrainNilearn

        plotter = PlotBrainNilearn(mesh="fsaverage5", inflate="half")
        fig = plt.figure(figsize=(5.8, 2.5))
        plotter.plot_surf(
            surface,
            views=["left", "right"],
            cmap="fire",
            norm_percentile=99,
            vmin=0.6,
            alpha_cmap=(0, 0.2),
            colorbar=False,
        )
        fig = plt.gcf()
        fig.suptitle(title, fontsize=10)
    except Exception as exc:
        LOGGER.warning("Surface rendering failed for %s; using heatmap fallback: %s", title, exc)
        fig, ax = plt.subplots(figsize=(5.8, 1.4))
        ax.imshow(surface.reshape(1, -1), aspect="auto", interpolation="nearest", cmap="inferno")
        ax.set_title(f"{title} (fallback)", fontsize=10)
        ax.set_yticks([])
        ax.set_xlabel("fsaverage5 vertex")

    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    return buffer.getvalue()


def run_ffmpeg(command: list[str]) -> bytes | None:
    """Run ffmpeg and return the produced output file bytes."""

    output_path = Path(command[-1])
    try:
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if output_path.is_file() and output_path.stat().st_size > 0:
            return output_path.read_bytes()
    except FileNotFoundError:
        LOGGER.warning("ffmpeg is not available; stimulus media will be omitted.")
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else str(exc)
        LOGGER.warning("ffmpeg failed: %s", stderr[:500])
    return None


def extract_video_frame(input_media: Path | None, start: float | None, duration: float | None) -> str:
    """Extract a representative frame for a segment and return an HTML image tag."""

    if input_media is None or input_media.suffix.lower() not in VIDEO_EXTENSIONS or not input_media.is_file():
        return ""
    if start is None:
        return ""
    timestamp = max(start + max(duration or 0.0, 0.0) / 2.0, 0.0)
    with tempfile.TemporaryDirectory() as tmp_dir:
        output_path = Path(tmp_dir) / "frame.png"
        command = [
            "ffmpeg",
            "-nostdin",
            "-y",
            "-loglevel",
            "error",
            "-ss",
            f"{timestamp:.3f}",
            "-i",
            str(input_media),
            "-frames:v",
            "1",
            "-vf",
            "scale=320:-1",
            str(output_path),
        ]
        frame_bytes = run_ffmpeg(command)
    if not frame_bytes:
        return ""
    return f"<img class=\"stimulus-frame\" src=\"{png_data_uri(frame_bytes)}\" alt=\"video frame\">"


def render_waveform_png(wav_bytes: bytes) -> bytes:
    """Render WAV bytes as a compact waveform PNG."""

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    with wave.open(BytesIO(wav_bytes), "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        sample_width = wav_file.getsampwidth()
        n_channels = wav_file.getnchannels()
        frames = wav_file.readframes(wav_file.getnframes())

    if sample_width == 1:
        samples = np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0
    elif sample_width == 2:
        samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
    elif sample_width == 4:
        samples = np.frombuffer(frames, dtype=np.int32).astype(np.float32)
    else:
        raise ValueError(f"Unsupported WAV sample width: {sample_width}")

    if n_channels > 1:
        samples = samples.reshape(-1, n_channels).mean(axis=1)
    if samples.size == 0:
        raise ValueError("WAV contains no samples")
    original_samples = samples.size

    max_abs = float(np.max(np.abs(samples)))
    if max_abs > 0:
        samples = samples / max_abs

    max_points = 900
    if samples.size > max_points:
        step = int(np.ceil(samples.size / max_points))
        samples = samples[: step * (samples.size // step)].reshape(-1, step).mean(axis=1)

    duration_seconds = original_samples / max(sample_rate, 1)
    time_axis = np.linspace(0.0, duration_seconds, samples.size, endpoint=False)
    fig, ax = plt.subplots(figsize=(3.2, 0.9))
    ax.plot(time_axis[: samples.size], samples, color="#111111", linewidth=0.8)
    ax.fill_between(time_axis[: samples.size], samples, 0, color="#111111", alpha=0.18)
    ax.axhline(0, color="#777777", linewidth=0.4)
    ax.set_ylim(-1.05, 1.05)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_frame_on(False)
    fig.tight_layout(pad=0.05)

    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=130, bbox_inches="tight", transparent=False)
    plt.close(fig)
    return buffer.getvalue()


def extract_audio_waveform(input_media: Path | None, start: float | None, duration: float | None) -> str:
    """Extract segment audio and return an embedded waveform image."""

    if input_media is None or input_media.suffix.lower() not in AUDIO_EXTENSIONS or not input_media.is_file():
        return ""
    if start is None:
        return ""
    clip_duration = duration if duration is not None and duration > 0 else 1.0
    clip_duration = min(float(clip_duration), MAX_AUDIO_SECONDS)
    with tempfile.TemporaryDirectory() as tmp_dir:
        output_path = Path(tmp_dir) / "audio.wav"
        command = [
            "ffmpeg",
            "-nostdin",
            "-y",
            "-loglevel",
            "error",
            "-ss",
            f"{max(start, 0.0):.3f}",
            "-t",
            f"{clip_duration:.3f}",
            "-i",
            str(input_media),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-acodec",
            "pcm_s16le",
            str(output_path),
        ]
        audio_bytes = run_ffmpeg(command)
    if not audio_bytes:
        return ""
    try:
        waveform = png_data_uri(render_waveform_png(audio_bytes))
    except Exception as exc:
        LOGGER.warning("Could not render audio waveform: %s", exc)
        return ""
    return f"<img class=\"stimulus-waveform\" src=\"{waveform}\" alt=\"audio waveform\">"


def row_text(row: pd.Series, text_columns: list[str]) -> str:
    """Extract text from one transcript row."""

    parts: list[str] = []
    for column in text_columns:
        value = row.get(column, "")
        if pd.isna(value):
            continue
        text = str(value).strip()
        if text:
            parts.append(text)
    return " ".join(parts)


def transcript_text_for_segment(
    transcript: pd.DataFrame,
    start: float | None,
    duration: float | None,
) -> str:
    """Return transcript text overlapping the current segment."""

    if transcript.empty:
        return ""

    text_column = find_column(transcript, TEXT_COLUMN_CANDIDATES)
    text_columns = [text_column] if text_column else [
        str(column)
        for column in transcript.columns
        if pd.api.types.is_object_dtype(transcript[column])
    ]
    if not text_columns:
        return ""

    start_column = find_column(transcript, START_COLUMN_CANDIDATES)
    end_column = find_column(transcript, END_COLUMN_CANDIDATES)
    duration_column = find_column(transcript, DURATION_COLUMN_CANDIDATES)

    selected_texts: list[str] = []
    if start is not None and start_column is not None:
        segment_end = start + (duration if duration is not None and duration > 0 else 1.0)
        for _, row in transcript.iterrows():
            row_start = safe_float(row.get(start_column))
            if row_start is None:
                continue
            row_end = safe_float(row.get(end_column)) if end_column else None
            if row_end is None and duration_column:
                row_duration = safe_float(row.get(duration_column), 0.0) or 0.0
                row_end = row_start + row_duration
            if row_end is None:
                row_end = row_start
            if row_start <= segment_end and row_end >= start:
                text = row_text(row, text_columns)
                if text:
                    selected_texts.append(text)
    else:
        selected_texts = [
            text
            for _, row in transcript.iterrows()
            if (text := row_text(row, text_columns))
        ]

    if not selected_texts:
        return ""

    compact: list[str] = []
    previous = ""
    for text in selected_texts:
        if text != previous:
            compact.append(text)
        previous = text
    return " ".join(compact)


def group_scores_for_time(scores: pd.DataFrame, map_id: str, time_index: int | str) -> pd.DataFrame:
    """Return score rows for one map/timepoint."""

    time_key = str(time_index)
    frame = scores[
        (scores["map_id"].astype(str) == map_id)
        & (scores["time_index"].astype(str) == time_key)
    ].copy()
    if frame.empty:
        return frame
    order = {name: idx for idx, name in enumerate(GROUP_ORDER)}
    frame["_group_key"] = frame["group"].map(normalize_group)
    frame["_order"] = frame["_group_key"].map(order).fillna(10_000)
    return frame.sort_values(["_order", "group"]).drop(columns=["_order", "_group_key"])


def top_groups_text(score_rows: pd.DataFrame, top_n: int) -> str:
    """Format top marketing groups for one timepoint."""

    if score_rows.empty:
        return ""
    top_rows = score_rows.sort_values("mean_r", ascending=False).head(top_n)
    return "<br>".join(
        f"{escape(row.group)}: <b>{fmt_float(row.mean_r, 3)}</b>"
        for row in top_rows.itertuples(index=False)
    )


def top_terms_text(
    terms: pd.DataFrame,
    map_id: str,
    time_index: int | str,
    top_n: int,
) -> str:
    """Format top decoded Neurosynth terms for one timepoint."""

    time_key = str(time_index)
    frame = terms[
        (terms["map_id"].astype(str) == map_id)
        & (terms["time_index"].astype(str) == time_key)
    ].copy()
    if frame.empty:
        return ""
    frame = frame.sort_values("r", ascending=False).head(top_n)
    return "<br>".join(
        f"{escape(row.feature)} ({escape(row.group)}): {fmt_float(row.r, 3)}"
        for row in frame.itertuples(index=False)
    )


def scores_cells(score_rows: pd.DataFrame) -> str:
    """Build score cells for all configured marketing groups."""

    by_group = {
        normalize_group(row.group): row
        for row in score_rows.itertuples(index=False)
    }
    cells: list[str] = []
    for group in GROUP_ORDER:
        row = by_group.get(group)
        if row is None:
            cells.append("<td class=\"score-cell\"></td>")
        else:
            cells.append(f"<td class=\"score-cell\">{fmt_float(row.mean_r, 3)}</td>")
    return "".join(cells)


def segment_metadata(segments: pd.DataFrame, index: int) -> dict[str, Any]:
    """Return segment metadata for a row index."""

    if segments.empty or index >= len(segments):
        return {}
    row = segments.iloc[index].to_dict()
    return {
        "start": row.get("start", row.get("offset", "")),
        "duration": row.get("duration", ""),
        "timeline": row.get("timeline", ""),
        "n_events": row.get("n_events", ""),
    }


def build_segment_rows(
    predictions: np.ndarray,
    scores: pd.DataFrame,
    terms: pd.DataFrame,
    segments: pd.DataFrame,
    input_media: Path | None,
    transcript: pd.DataFrame,
    top_terms: int,
    top_groups: int,
) -> str:
    """Build the per-segment interpretation table."""

    rows: list[str] = []
    for index, surface in enumerate(predictions):
        LOGGER.info("Rendering segment %d/%d", index + 1, predictions.shape[0])
        image = png_data_uri(render_surface_png(surface, f"segment {index}"))
        metadata = segment_metadata(segments, index)
        start = safe_float(metadata.get("start"))
        duration = safe_float(metadata.get("duration"))
        video_frame = extract_video_frame(input_media, start, duration)
        audio_waveform = extract_audio_waveform(input_media, start, duration)
        transcript_text = transcript_text_for_segment(transcript, start, duration)
        score_rows = group_scores_for_time(scores, SEGMENT_MAP_ID, index)
        rows.append(
            "<tr>"
            f"<td>{index}</td>"
            f"<td>{escape(metadata.get('start', ''))}</td>"
            f"<td>{escape(metadata.get('duration', ''))}</td>"
            f"<td><img class=\"brain\" src=\"{image}\" alt=\"segment {index} brain map\"></td>"
            f"<td>{video_frame}</td>"
            f"<td>{audio_waveform}</td>"
            f"<td class=\"stimulus-text\">{escape(transcript_text)}</td>"
            f"<td class=\"top-groups-cell\">{top_groups_text(score_rows, top_groups)}</td>"
            f"<td class=\"top-terms-cell\">{top_terms_text(terms, SEGMENT_MAP_ID, index, top_terms)}</td>"
            f"{scores_cells(score_rows)}"
            "</tr>"
        )
    return "\n".join(rows)


def build_aggregate_rows(
    activity: np.ndarray | None,
    scores: pd.DataFrame,
    terms: pd.DataFrame,
    top_terms: int,
    top_groups: int,
) -> str:
    """Build the whole-video interpretation table."""

    rows: list[str] = []
    aggregate_map_ids = [SEGMENT_MAP_ID, AGGREGATE_MAP_ID]
    for map_id in aggregate_map_ids:
        score_rows = group_scores_for_time(scores, map_id, "aggregate")
        if score_rows.empty:
            continue
        if map_id == AGGREGATE_MAP_ID and activity is not None:
            image = png_data_uri(render_surface_png(activity, "whole video"))
            image_cell = f"<img class=\"brain\" src=\"{image}\" alt=\"whole video brain map\">"
            label = "whole-video activity map"
        elif map_id == SEGMENT_MAP_ID:
            image_cell = ""
            label = "mean of segment scores"
        else:
            image_cell = ""
            label = map_id
        rows.append(
            "<tr>"
            f"<td>{escape(label)}</td>"
            f"<td>{image_cell}</td>"
            f"<td class=\"top-groups-cell\">{top_groups_text(score_rows, top_groups)}</td>"
            f"<td class=\"top-terms-cell\">{top_terms_text(terms, map_id, 'aggregate', top_terms)}</td>"
            f"{scores_cells(score_rows)}"
            "</tr>"
        )
    return "\n".join(rows)


def table_header(include_time: bool, include_stimuli: bool = False) -> str:
    """Build a common table header."""

    prefix = ""
    if include_time:
        prefix = "<th>segment</th><th>start</th><th>duration</th>"
    else:
        prefix = "<th>summary</th>"
    stimuli_headers = ""
    if include_stimuli:
        stimuli_headers = "<th>video frame</th><th>audio waveform</th><th>text</th>"
    group_headers = "".join(f"<th>{escape(GROUP_LABELS[group])}<br><span class=\"small\">mean_r</span></th>" for group in GROUP_ORDER)
    return (
        "<tr>"
        f"{prefix}"
        "<th>brain map</th>"
        f"{stimuli_headers}"
        "<th class=\"top-groups-cell\">top groups</th>"
        "<th class=\"top-terms-cell\">top terms</th>"
        f"{group_headers}"
        "</tr>"
    )


def build_method_notes() -> str:
    """Build a compact explanation of how decoder scores should be read."""

    return """
  <div class="note">
    <b>Как читать группы и scores:</b>
    <ul>
      <li><b>Группа</b> — это не одна эмоция и не один участок мозга, а набор Neurosynth reference terms, которые мы заранее объединили в маркетинговую категорию.</li>
      <li><b>top terms</b> — отдельные reference terms, отсортированные по корреляции <code>r</code> с TRIBE-картой сегмента.</li>
      <li><b>top groups</b> — группы, отсортированные по <code>mean_r</code>, где <code>mean_r</code> — средняя корреляция terms внутри группы.</li>
      <li><b>Диапазон и top groups, и top terms: -1..+1.</b> Около 0 — нейтрально, выше 0 — положительное сходство с reference maps, ниже 0 — отрицательное сходство.</li>
      <li>Это proxy-интерпретация предсказанной TRIBE brain map, а не прямое измерение мозга зрителя и не object detection в кадре.</li>
    </ul>
  </div>
"""


def resolved_terms_by_group(terms: pd.DataFrame) -> dict[str, list[str]]:
    """Return resolved decoder terms grouped by marketing group."""

    if terms.empty:
        return {}

    out: dict[str, list[str]] = {}
    for row in terms[["feature", "group"]].dropna().drop_duplicates().itertuples(index=False):
        group = normalize_group(row.group)
        out.setdefault(group, []).append(str(row.feature))
    return {group: sorted(set(features)) for group, features in out.items()}


def build_group_dictionary_rows(terms: pd.DataFrame) -> str:
    """Build rows explaining configured marketing groups."""

    resolved = resolved_terms_by_group(terms)
    rows: list[str] = []
    for group in GROUP_ORDER:
        explanation = GROUP_EXPLANATIONS[group]
        resolved_terms = resolved.get(group) or MARKETING_TERMS[group]
        rows.append(
            "<tr>"
            f"<td><b>{escape(GROUP_LABELS[group])}</b><br><span class=\"small\">{escape(group)}</span></td>"
            f"<td>{escape(explanation['meaning'])}</td>"
            f"<td>{escape(explanation['high_score'])}</td>"
            f"<td>{escape(explanation['marketing'])}</td>"
            f"<td>{escape(', '.join(resolved_terms))}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def segment_time_seconds(segments: pd.DataFrame, index: int) -> float:
    """Return segment start time in seconds, falling back to segment index."""

    metadata = segment_metadata(segments, index)
    start = safe_float(metadata.get("start"))
    if start is not None:
        return start
    offset = safe_float(metadata.get("offset"))
    if offset is not None:
        return offset
    return float(index)


def group_timeline_frame(scores: pd.DataFrame, segments: pd.DataFrame) -> pd.DataFrame:
    """Build a time x group dataframe of segment-level mean_r values."""

    frame = scores[
        (scores["map_id"].astype(str) == SEGMENT_MAP_ID)
        & (scores["time_index"].astype(str) != "aggregate")
    ].copy()
    if frame.empty:
        return pd.DataFrame()

    frame["time_index_int"] = frame["time_index"].astype(int)
    frame["time_seconds"] = frame["time_index_int"].map(
        lambda value: segment_time_seconds(segments, int(value))
    )
    frame["group_key"] = frame["group"].map(normalize_group)
    frame = frame[frame["group_key"].isin(GROUP_ORDER)]
    if frame.empty:
        return pd.DataFrame()

    timeline = frame.pivot_table(
        index="time_seconds",
        columns="group_key",
        values="mean_r",
        aggfunc="mean",
    )
    timeline = timeline.sort_index().reindex(columns=GROUP_ORDER)
    return timeline


def render_group_timeline_png(scores: pd.DataFrame, segments: pd.DataFrame) -> bytes | None:
    """Render group mean_r changes over time as a PNG line chart."""

    timeline = group_timeline_frame(scores, segments)
    if timeline.empty:
        return None

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = {
        "attention": "#1f77b4",
        "reward": "#ff7f0e",
        "memory": "#2ca02c",
        "emotion": "#d62728",
        "social": "#9467bd",
        "aversion": "#8c564b",
        "language": "#17becf",
        "action": "#bcbd22",
    }

    fig, ax = plt.subplots(figsize=(12, 4.4))
    plotted = False
    for group in GROUP_ORDER:
        series = timeline[group].dropna()
        if series.empty:
            continue
        ax.plot(
            series.index.to_numpy(dtype=float),
            series.to_numpy(dtype=float),
            marker="o",
            markersize=3.5,
            linewidth=1.8,
            label=GROUP_LABELS[group],
            color=colors[group],
        )
        plotted = True

    if not plotted:
        plt.close(fig)
        return None

    values = timeline.to_numpy(dtype=float)
    finite_values = values[np.isfinite(values)]
    if finite_values.size:
        data_min = float(finite_values.min())
        data_max = float(finite_values.max())
        margin = max((data_max - data_min) * 0.18, 0.03)
        y_min = max(-1.0, data_min - margin)
        y_max = min(1.0, data_max + margin)
        if y_max - y_min < 0.1:
            center = (y_min + y_max) / 2.0
            y_min = max(-1.0, center - 0.05)
            y_max = min(1.0, center + 0.05)
        ax.set_ylim(y_min, y_max)
    else:
        ax.set_ylim(-1.0, 1.0)

    ax.axhline(0.0, color="#333333", linewidth=0.9, alpha=0.5)
    ax.set_title("Marketing group mean_r over time", fontsize=13)
    ax.set_xlabel("time, seconds")
    ax.set_ylabel("mean_r correlation (-1..+1)")
    ax.grid(True, axis="y", color="#d0d7de", linewidth=0.7, alpha=0.8)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=4, fontsize=9)
    fig.tight_layout(rect=(0, 0.08, 1, 1))

    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=140, bbox_inches="tight")
    plt.close(fig)
    return buffer.getvalue()


def build_group_timeline_section(scores: pd.DataFrame, segments: pd.DataFrame) -> str:
    """Build the HTML section with a group correlation timeline chart."""

    timeline_png = render_group_timeline_png(scores, segments)
    if timeline_png is None:
        return """
  <h2>Group correlation timeline</h2>
  <p class="small">No segment-level group scores were available for a timeline chart.</p>
"""

    image = png_data_uri(timeline_png)
    return f"""
  <h2>Group correlation timeline</h2>
  <p class="small">
    X-axis is segment start time in seconds. Y-axis is <code>mean_r</code>, the average
    correlation between the TRIBE map for that segment and the reference maps in each group.
  </p>
  <div class="chart-wrap">
    <img class="timeline-chart" src="{image}" alt="group mean_r timeline">
  </div>
"""


def build_html(
    title: str,
    tribe_dir: Path,
    surface_dir: Path,
    input_media: Path | None,
    predictions: np.ndarray,
    activity: np.ndarray | None,
    scores: pd.DataFrame,
    terms: pd.DataFrame,
    decoder_report: dict[str, Any],
    segments: pd.DataFrame,
    top_terms: int,
    top_groups: int,
) -> str:
    """Assemble the full self-contained HTML report."""

    transcript = load_sidecar_transcript(input_media)
    segment_rows = build_segment_rows(
        predictions=predictions,
        scores=scores,
        terms=terms,
        segments=segments,
        input_media=input_media,
        transcript=transcript,
        top_terms=top_terms,
        top_groups=top_groups,
    )
    aggregate_rows = build_aggregate_rows(
        activity=activity,
        scores=scores,
        terms=terms,
        top_terms=top_terms,
        top_groups=top_groups,
    )
    safe_title = escape(title)
    reference_features = ", ".join(decoder_report.get("reference_features", []))
    proxy_warning = decoder_report.get(
        "proxy_interpretation_warning",
        "Scores are proxy correlations with Neurosynth-derived reference maps.",
    )
    shape = f"{predictions.shape[0]} x {predictions.shape[1]}"
    input_media_text = str(input_media) if input_media is not None else ""
    method_notes = build_method_notes()
    group_dictionary_rows = build_group_dictionary_rows(terms)
    group_timeline_section = build_group_timeline_section(scores, segments)

    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>{safe_title}</title>
  <style>
    body {{
      margin: 24px;
      color: #202124;
      font-family: Arial, sans-serif;
      line-height: 1.35;
    }}
    h1, h2 {{ margin: 0.7em 0 0.35em; }}
    .meta, .note {{
      background: #f6f8fa;
      border: 1px solid #d0d7de;
      border-radius: 6px;
      padding: 12px;
      margin: 12px 0;
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
      margin: 12px 0 28px;
      font-size: 12px;
    }}
    th, td {{
      border: 1px solid #d0d7de;
      padding: 6px;
      vertical-align: top;
    }}
    th {{
      background: #eef2f7;
      position: sticky;
      top: 0;
      z-index: 1;
    }}
    .score-cell {{
      text-align: right;
      white-space: nowrap;
    }}
    .brain {{
      width: 260px;
      max-width: 260px;
      height: auto;
      display: block;
    }}
    .stimulus-frame {{
      width: 220px;
      max-width: 220px;
      height: auto;
      display: block;
    }}
    .stimulus-waveform {{
      width: 180px;
      max-width: 180px;
      height: auto;
      display: block;
    }}
    .stimulus-text {{
      min-width: 180px;
      max-width: 320px;
      white-space: normal;
    }}
    .top-groups-cell {{
      min-width: 240px;
      max-width: 320px;
      width: 18%;
      white-space: normal;
    }}
    .top-terms-cell {{
      min-width: 360px;
      max-width: 520px;
      width: 28%;
      white-space: normal;
    }}
    .dictionary-table td:nth-child(1) {{
      width: 220px;
    }}
    .chart-wrap {{
      border: 1px solid #d0d7de;
      border-radius: 6px;
      padding: 12px;
      margin: 12px 0 28px;
      overflow-x: auto;
    }}
    .timeline-chart {{
      width: 100%;
      min-width: 900px;
      height: auto;
      display: block;
    }}
    code {{
      background: #eef2f7;
      border-radius: 3px;
      padding: 1px 4px;
    }}
    .small {{ font-size: 11px; color: #57606a; }}
  </style>
</head>
<body>
  <h1>{safe_title}</h1>
  <div class="meta">
    <div><b>TRIBE output:</b> {escape(tribe_dir)}</div>
    <div><b>Decoder output:</b> {escape(surface_dir)}</div>
    <div><b>Input media:</b> {escape(input_media_text)}</div>
    <div><b>TRIBE predictions shape:</b> {escape(shape)}</div>
    <div><b>Reference features:</b> {escape(reference_features)}</div>
  </div>
  <div class="note">
    <b>Important:</b> {escape(proxy_warning)}
    This is not a direct measurement of a real viewer's brain activity.
  </div>

  <h2>Whole-video interpretation</h2>
  <table>
    <thead>{table_header(include_time=False)}</thead>
    <tbody>{aggregate_rows}</tbody>
  </table>

  <h2>Per-segment brain activity and decoding</h2>
  <p class="small">Every TRIBE timepoint is included; this table is not truncated to the UI preview limit.</p>
  <table>
    <thead>{table_header(include_time=True, include_stimuli=True)}</thead>
    <tbody>{segment_rows}</tbody>
  </table>

  <h2>Marketing group dictionary and score interpretation</h2>
  {method_notes}

  <h3>Marketing group meanings</h3>
  <table class="dictionary-table">
    <thead>
      <tr>
        <th>group</th>
        <th>what it means</th>
        <th>how to read a high score</th>
        <th>marketing read</th>
        <th>resolved reference terms</th>
      </tr>
    </thead>
    <tbody>{group_dictionary_rows}</tbody>
  </table>

  {group_timeline_section}
</body>
</html>
"""


def generate_report(
    tribe_dir: Path,
    surface_dir: Path,
    output_html: Path,
    input_media: Path | None,
    title: str,
    top_terms: int,
    top_groups: int,
) -> Path:
    """Generate the report and return its path."""

    predictions, activity = load_predictions(tribe_dir)
    scores, terms, decoder_report = load_decoder_tables(surface_dir)
    segments = load_segments(tribe_dir)
    html_text = build_html(
        title=title,
        tribe_dir=tribe_dir,
        surface_dir=surface_dir,
        input_media=input_media,
        predictions=predictions,
        activity=activity,
        scores=scores,
        terms=terms,
        decoder_report=decoder_report,
        segments=segments,
        top_terms=top_terms,
        top_groups=top_groups,
    )
    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(html_text, encoding="utf-8")
    return output_html


def main() -> None:
    """CLI entry point."""

    configure_logging()
    args = parse_args()
    output = generate_report(
        tribe_dir=args.tribe_dir,
        surface_dir=args.surface_dir,
        output_html=args.output_html,
        input_media=args.input_media,
        title=args.title,
        top_terms=args.top_terms,
        top_groups=args.top_groups,
    )
    print(f"Saved HTML report: {output}")


if __name__ == "__main__":
    main()
