# -*- coding: utf-8 -*-
"""TRIBE v2 + NiMARE interpretation pipeline.

Модуль запускает TRIBE v2 для текста, аудио или видео, получает предсказанные
активации на поверхности fsaverage5 и интерпретирует их через term maps,
построенные NiMARE по Neurosynth.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import pickle
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal

import nibabel as nib
import numpy as np
import pandas as pd
from nilearn import datasets
from nilearn.surface import vol_to_surf
from scipy.stats import zscore

LOGGER = logging.getLogger("tribe_nimare")

InputKind = Literal["text", "audio", "video"]
Aggregation = Literal["mean", "median", "max_abs"]
TranscriptBackend = Literal["tribe", "hybrid"]

RUNNER_BUILD_ID = "hybrid-transcription-20260615-01"
FSAVERAGE5_VERTICES_PER_HEMISPHERE = 10242
FSAVERAGE5_TOTAL_VERTICES = FSAVERAGE5_VERTICES_PER_HEMISPHERE * 2
TRIBE_INFERENCE_CONFIG_UPDATE = {
    # The pretrained config stores study transforms as an exca.ConfDict mapping,
    # while current pydantic validation expects a list or an OrderedDict.
    # We build inference events from the input file directly, so study transforms
    # are not needed for TRIBE prediction on user-provided media.
    "data.study.transforms": [],
}


@dataclass(frozen=True)
class TribePrediction:
    """Predicted TRIBE v2 activity aligned to fsaverage5 vertices."""

    activity: np.ndarray
    segments_path: Path
    prediction_path: Path


@dataclass(frozen=True)
class SurfaceTermMaps:
    """NiMARE feature maps projected from MNI volume to fsaverage5 surface."""

    features: list[str]
    maps: np.ndarray


def configure_logging(verbose: bool) -> None:
    """Configure process-wide logging."""

    level = logging.INFO if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def format_gib_from_kib(value_kib: int | None) -> str:
    """Format a KiB value from /proc/meminfo as GiB."""

    if value_kib is None:
        return "n/a"
    return f"{value_kib / 1024 / 1024:.1f} GiB"


def read_meminfo() -> dict[str, int]:
    """Read selected /proc/meminfo values in KiB."""

    out: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, raw_value = line.split(":", 1)
            value = raw_value.strip().split()[0]
            if value.isdigit():
                out[key] = int(value)
    except Exception:
        pass
    return out


def short_command_output(cmd: list[str], timeout: float = 5.0) -> str:
    """Run a small diagnostic command and return compact stdout/stderr."""

    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    text = (completed.stdout or completed.stderr or "").strip()
    return text or f"exit={completed.returncode}; no output"


def log_resource_snapshot(label: str) -> None:
    """Log RAM/GPU diagnostics for TRIBE subprocess debugging."""

    meminfo = read_meminfo()
    total = meminfo.get("MemTotal")
    available = meminfo.get("MemAvailable")
    used = total - available if total is not None and available is not None else None
    swap_total = meminfo.get("SwapTotal")
    swap_free = meminfo.get("SwapFree")
    swap_used = (
        swap_total - swap_free
        if swap_total is not None and swap_free is not None
        else None
    )
    LOGGER.info(
        "[diag] %s pid=%s RAM used/total/available: %s / %s / %s",
        label,
        os.getpid(),
        format_gib_from_kib(used),
        format_gib_from_kib(total),
        format_gib_from_kib(available),
    )
    LOGGER.info(
        "[diag] %s swap used/total/free: %s / %s / %s",
        label,
        format_gib_from_kib(swap_used),
        format_gib_from_kib(swap_total),
        format_gib_from_kib(swap_free),
    )
    gpu_output = short_command_output(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu",
            "--format=csv,noheader,nounits",
        ]
    )
    LOGGER.info("[diag] %s GPU name,mem_used,mem_total,util,temp: %s", label, gpu_output)
    gpu_processes = short_command_output(
        [
            "nvidia-smi",
            "--query-compute-apps=pid,process_name,used_memory",
            "--format=csv,noheader,nounits",
        ]
    )
    LOGGER.info("[diag] %s GPU processes pid,name,mem: %s", label, gpu_processes)


def ensure_output_dir(path: Path) -> Path:
    """Create output directory if it is missing."""

    path.mkdir(parents=True, exist_ok=True)
    return path


def detect_input_kind(path: Path) -> InputKind:
    """Detect TRIBE v2 input modality from file extension."""

    suffix = path.suffix.lower()
    if suffix == ".txt":
        return "text"
    if suffix in {".wav", ".mp3", ".flac", ".ogg"}:
        return "audio"
    if suffix in {".mp4", ".avi", ".mkv", ".mov", ".webm"}:
        return "video"

    raise ValueError(
        "Не удалось определить тип входа. Поддерживаются .txt, аудио "
        "(.wav/.mp3/.flac/.ogg) и видео (.mp4/.avi/.mkv/.mov/.webm)."
    )


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


def run_tribe_v2(
    input_path: Path,
    output_dir: Path,
    checkpoint: str,
    cache_dir: Path,
    device: str,
    aggregation: Aggregation,
    verbose: bool,
    transcript_backend: TranscriptBackend,
    transcript_source_language: str,
    transcript_target_language: str,
    gigaam_model: str,
    gigaam_download_root: Path,
    openrouter_model: str,
    gigaam_chunk_sec: float,
    correction_max_words: int,
    correction_max_seconds: float,
    correction_min_confidence: float,
    correction_retries: int,
) -> TribePrediction:
    """Run TRIBE v2 and aggregate time-resolved surface activations.

    Thin wrapper kept for backwards compatibility: it loads the model and then
    processes a single input. The two steps are factored into
    ``load_tribe_model`` and ``process_input_with_model`` so a long-lived worker
    (``tribe_worker.py``) can load the checkpoint once and reuse it across many
    inputs.
    """

    model = load_tribe_model(checkpoint=checkpoint, cache_dir=cache_dir, device=device)
    return process_input_with_model(
        model=model,
        input_path=input_path,
        output_dir=output_dir,
        aggregation=aggregation,
        verbose=verbose,
        transcript_backend=transcript_backend,
        transcript_source_language=transcript_source_language,
        transcript_target_language=transcript_target_language,
        gigaam_model=gigaam_model,
        gigaam_download_root=gigaam_download_root,
        openrouter_model=openrouter_model,
        gigaam_chunk_sec=gigaam_chunk_sec,
        correction_max_words=correction_max_words,
        correction_max_seconds=correction_max_seconds,
        correction_min_confidence=correction_min_confidence,
        correction_retries=correction_retries,
    )


def load_tribe_model(checkpoint: str, cache_dir: Path, device: str):
    """Load a TRIBE v2 model once so it can be reused across many inputs."""

    patch_exca_no_value_compat()
    from tribev2 import TribeModel

    LOGGER.info("Loading TRIBE v2 checkpoint: %s", checkpoint)
    log_resource_snapshot("before TribeModel.from_pretrained")
    model = TribeModel.from_pretrained(
        checkpoint,
        cache_folder=str(cache_dir),
        device=device,
        config_update=TRIBE_INFERENCE_CONFIG_UPDATE,
    )
    log_resource_snapshot("after TribeModel.from_pretrained")
    return model


def process_input_with_model(
    model,
    input_path: Path,
    output_dir: Path,
    aggregation: Aggregation,
    verbose: bool,
    transcript_backend: TranscriptBackend,
    transcript_source_language: str,
    transcript_target_language: str,
    gigaam_model: str,
    gigaam_download_root: Path,
    openrouter_model: str,
    gigaam_chunk_sec: float,
    correction_max_words: int,
    correction_max_seconds: float,
    correction_min_confidence: float,
    correction_retries: int,
) -> TribePrediction:
    """Run TRIBE v2 inference for one input using a preloaded model."""

    if not input_path.is_file():
        raise FileNotFoundError(f"Входной файл не найден: {input_path}")

    input_kind = detect_input_kind(input_path)
    LOGGER.info("Preparing %s events from %s", input_kind, input_path)
    if transcript_backend == "hybrid":
        events = prepare_hybrid_transcript_events(
            input_path=input_path,
            input_kind=input_kind,
            output_dir=output_dir,
            transcript_source_language=transcript_source_language,
            transcript_target_language=transcript_target_language,
            gigaam_model=gigaam_model,
            gigaam_download_root=gigaam_download_root,
            openrouter_model=openrouter_model,
            gigaam_chunk_sec=gigaam_chunk_sec,
            correction_max_words=correction_max_words,
            correction_max_seconds=correction_max_seconds,
            correction_min_confidence=correction_min_confidence,
            correction_retries=correction_retries,
        )
    else:
        events_kwargs = {
            "text_path": None,
            "audio_path": None,
            "video_path": None,
        }
        events_kwargs[f"{input_kind}_path"] = str(input_path)
        events = model.get_events_dataframe(**events_kwargs)
    write_transcription_metadata(
        output_dir=output_dir,
        backend=transcript_backend,
        source_language=transcript_source_language,
        target_language=transcript_target_language,
        gigaam_model=gigaam_model,
        gigaam_download_root=gigaam_download_root,
        openrouter_model=openrouter_model,
    )
    LOGGER.info(
        "Prepared events: rows=%d, types=%s",
        len(events),
        sorted(str(value) for value in events["type"].dropna().unique()),
    )
    log_resource_snapshot("after get_events_dataframe")

    LOGGER.info("Running TRIBE v2 inference")
    log_resource_snapshot("before model.predict")
    predictions, segments = model.predict(events=events, verbose=verbose)
    log_resource_snapshot("after model.predict")
    predictions = np.asarray(predictions, dtype=np.float32)
    segments = list(segments)
    validate_tribe_predictions(predictions)

    prediction_path = output_dir / "tribe_predictions_fsaverage5.npy"
    np.save(prediction_path, predictions)

    segments_path = output_dir / "tribe_segments.tsv"
    write_segments(segments, segments_path)
    write_segments_pickle(segments, output_dir / "tribe_segments.pkl")

    activity = aggregate_predictions(predictions, aggregation)
    activity_path = output_dir / "tribe_activity_fsaverage5.npy"
    np.save(activity_path, activity.astype(np.float32))

    LOGGER.info("Saved aggregated TRIBE activity to %s", activity_path)
    return TribePrediction(
        activity=activity,
        segments_path=segments_path,
        prediction_path=prediction_path,
    )


def write_transcription_metadata(
    output_dir: Path,
    backend: str,
    source_language: str,
    target_language: str,
    gigaam_model: str,
    gigaam_download_root: Path | None,
    openrouter_model: str,
) -> None:
    """Persist non-secret transcription settings next to TRIBE outputs."""

    metadata = {
        "backend": backend,
        "source_language": source_language,
        "target_language": target_language,
        "gigaam_model": gigaam_model if backend == "hybrid" else "",
        "gigaam_download_root": str(gigaam_download_root) if backend == "hybrid" and gigaam_download_root else "",
        "openrouter_model": openrouter_model if backend == "hybrid" else "",
    }
    (output_dir / "tribe_transcription_backend.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def prepare_hybrid_transcript_events(
    input_path: Path,
    input_kind: InputKind,
    output_dir: Path,
    transcript_source_language: str,
    transcript_target_language: str,
    gigaam_model: str,
    gigaam_download_root: Path,
    openrouter_model: str,
    gigaam_chunk_sec: float,
    correction_max_words: int,
    correction_max_seconds: float,
    correction_min_confidence: float,
    correction_retries: int,
) -> pd.DataFrame:
    """Build TRIBE events with hybrid Word events and preserved video/audio."""

    if input_kind != "video":
        raise ValueError(
            "--transcript-backend hybrid currently supports video inputs only. "
            f"Got {input_kind}: {input_path}"
        )
    if not os.environ.get("OPENROUTER_API_KEY"):
        raise RuntimeError(
            "OPENROUTER_API_KEY is required for --transcript-backend hybrid. "
            "Set it in the notebook UI or environment."
        )

    patch_exca_no_value_compat()
    from neuralset.events.transforms import (
        AddContextToWords,
        AddSentenceToWords,
        AddText,
        ChunkEvents,
        ExtractAudioFromVideo,
        RemoveMissing,
    )
    from neuralset.events.utils import standardize_events

    from hybrid_transcriber import transcribe_video_for_tribe

    hybrid_dir = output_dir / "hybrid_transcription"
    LOGGER.info(
        "Running hybrid transcription: GigaAM=%s, download_root=%s, correction=%s, target_language=%s",
        gigaam_model,
        gigaam_download_root,
        openrouter_model,
        transcript_target_language,
    )
    corrected_df, word_events = transcribe_video_for_tribe(
        video_path=input_path,
        output_dir=hybrid_dir,
        gigaam_model_name=gigaam_model,
        gigaam_download_root=gigaam_download_root,
        openrouter_model=openrouter_model,
        source_language=transcript_source_language,
        target_language=transcript_target_language,
        gigaam_chunk_sec=gigaam_chunk_sec,
        max_words_per_request=correction_max_words,
        max_seconds_per_request=correction_max_seconds,
        min_replace_confidence=correction_min_confidence,
        correction_retries=correction_retries,
    )
    if word_events.empty:
        raise RuntimeError("Hybrid transcription produced no word events.")

    transcript_path = output_dir / "tribe_transcript.tsv"
    corrected_df.to_csv(transcript_path, sep="\t", index=False, encoding="utf-8")
    LOGGER.info("Saved hybrid transcript to %s", transcript_path)

    word_events = word_events.copy()
    word_events["timeline"] = "default"
    word_events["subject"] = "default"
    media_event = pd.DataFrame(
        [
            {
                "type": "Video",
                "filepath": str(input_path),
                "start": 0.0,
                "timeline": "default",
                "subject": "default",
            }
        ]
    )
    raw_events = pd.concat([media_event, word_events], ignore_index=True)
    transforms = [
        ExtractAudioFromVideo(),
        ChunkEvents(event_type_to_chunk="Audio", max_duration=60, min_duration=30),
        ChunkEvents(event_type_to_chunk="Video", max_duration=60, min_duration=30),
        AddText(),
        AddSentenceToWords(max_unmatched_ratio=0.05),
        AddContextToWords(
            sentence_only=False,
            max_context_len=1024,
            split_field="",
        ),
        RemoveMissing(),
    ]
    events = standardize_events(raw_events)
    for transform in transforms:
        events = transform(events)
    events = standardize_events(events)
    events_path = output_dir / "tribe_events_hybrid.tsv"
    events.to_csv(events_path, sep="\t", index=False, encoding="utf-8")
    LOGGER.info("Saved hybrid TRIBE events to %s", events_path)
    return events


def load_cached_tribe_prediction(output_dir: Path) -> TribePrediction:
    """Load previously saved TRIBE v2 activity from an output directory."""

    activity_path = output_dir / "tribe_activity_fsaverage5.npy"
    prediction_path = output_dir / "tribe_predictions_fsaverage5.npy"
    segments_path = output_dir / "tribe_segments.tsv"

    if not activity_path.is_file():
        raise FileNotFoundError(
            f"Cached TRIBE activity not found: {activity_path}. "
            "Run without --reuse-tribe first."
        )

    activity = np.load(activity_path).astype(np.float32)
    validate_surface_vector(activity, "cached TRIBE activity")
    LOGGER.info("Loaded cached TRIBE activity from %s", activity_path)

    return TribePrediction(
        activity=activity,
        segments_path=segments_path,
        prediction_path=prediction_path,
    )


def validate_tribe_predictions(predictions: np.ndarray) -> None:
    """Validate TRIBE v2 output shape."""

    if predictions.ndim != 2:
        raise ValueError(
            f"TRIBE v2 должен вернуть 2D массив (time, vertices), "
            f"получено shape={predictions.shape}."
        )

    if predictions.shape[1] != FSAVERAGE5_TOTAL_VERTICES:
        raise ValueError(
            "Ожидались предсказания TRIBE v2 в fsaverage5: "
            f"{FSAVERAGE5_TOTAL_VERTICES} вершин, получено "
            f"{predictions.shape[1]}."
        )


def write_segments(segments: Iterable[object], path: Path) -> None:
    """Write TRIBE segment metadata to UTF-8 TSV."""

    rows: list[dict[str, object]] = []
    for index, segment in enumerate(segments):
        rows.append(
            {
                "index": index,
                "offset": getattr(segment, "offset", None),
                "duration": getattr(segment, "duration", None),
                "start": getattr(segment, "start", None),
                "timeline": getattr(segment, "timeline", None),
                "subject": getattr(segment, "subject", None),
                "n_events": len(getattr(segment, "ns_events", []) or []),
            }
        )

    pd.DataFrame(rows).to_csv(path, sep="\t", index=False, encoding="utf-8")


def write_segments_pickle(segments: Iterable[object], path: Path) -> None:
    """Persist full TRIBE segment objects for official plotting."""

    try:
        with path.open("wb") as handle:
            pickle.dump(list(segments), handle, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception as exc:
        LOGGER.warning("Could not save full TRIBE segments to %s: %s", path, exc)


def aggregate_predictions(predictions: np.ndarray, method: Aggregation) -> np.ndarray:
    """Aggregate TRIBE v2 predictions over time."""

    if method == "mean":
        activity = predictions.mean(axis=0)
    elif method == "median":
        activity = np.median(predictions, axis=0)
    elif method == "max_abs":
        max_indices = np.argmax(np.abs(predictions), axis=0)
        activity = predictions[max_indices, np.arange(predictions.shape[1])]
    else:
        raise ValueError(f"Unknown aggregation method: {method}")

    return np.nan_to_num(activity, nan=0.0, posinf=0.0, neginf=0.0)


def load_or_fit_nimare_decoder(
    data_dir: Path,
    decoder_cache: Path,
    frequency_threshold: float,
    n_cores: int,
    max_features: int,
    min_feature_study_fraction: float,
    max_feature_study_fraction: float,
):
    """Load cached NiMARE decoder or fit it on Neurosynth term annotations."""

    from nimare.decode.continuous import CorrelationDecoder
    from nimare.extract import fetch_neurosynth
    from nimare.meta.cbma import mkda

    if decoder_cache.is_file():
        LOGGER.info("Loading cached NiMARE decoder: %s", decoder_cache)
        return CorrelationDecoder.load(str(decoder_cache))

    LOGGER.info("Fetching Neurosynth term annotations for NiMARE")
    studysets = fetch_neurosynth(
        data_dir=str(data_dir),
        version="7",
        source="abstract",
        vocab="terms",
    )
    if not studysets:
        raise RuntimeError("NiMARE не вернул Neurosynth studyset.")

    features = select_nimare_features(
        studyset=studysets[0],
        frequency_threshold=frequency_threshold,
        max_features=max_features,
        min_fraction=min_feature_study_fraction,
        max_fraction=max_feature_study_fraction,
    )

    LOGGER.info("Fitting NiMARE CorrelationDecoder")
    decoder = CorrelationDecoder(
        features=features,
        frequency_threshold=frequency_threshold,
        meta_estimator=mkda.MKDAChi2,
        target_image="z_desc-association",
        n_cores=n_cores,
    )
    decoder.fit(studysets[0])
    decoder.save(str(decoder_cache))

    return decoder


def select_nimare_features(
    studyset,
    frequency_threshold: float,
    max_features: int,
    min_fraction: float,
    max_fraction: float,
) -> list[str] | None:
    """Select a memory-bounded subset of NiMARE annotation features."""

    if max_features <= 0 and min_fraction <= 0 and max_fraction >= 1:
        return None

    dataset = studyset.to_dataset() if hasattr(studyset, "to_dataset") else studyset
    annotations = getattr(dataset, "annotations", None)
    if annotations is None:
        LOGGER.warning("Could not inspect NiMARE annotations; using all features.")
        return None

    id_cols = {"id", "study_id", "contrast_id"}
    feature_cols = [
        column
        for column in annotations.columns
        if column not in id_cols and pd.api.types.is_numeric_dtype(annotations[column])
    ]
    if not feature_cols:
        LOGGER.warning("No numeric NiMARE annotation features found; using all features.")
        return None

    feature_values = annotations[feature_cols]
    n_studies = feature_values.shape[0]
    feature_counts = (feature_values >= frequency_threshold).sum(axis=0)
    min_count = int(np.ceil(n_studies * min_fraction))
    max_count = int(np.floor(n_studies * max_fraction))

    selected = feature_counts[
        (feature_counts >= min_count) & (feature_counts <= max_count)
    ].sort_values(ascending=False)

    if max_features > 0:
        selected = selected.head(max_features)

    if selected.empty:
        raise RuntimeError(
            "No NiMARE features left after filtering. Lower "
            "--frequency-threshold or --min-feature-study-fraction."
        )

    LOGGER.info(
        "Selected %d/%d NiMARE features for decoder fitting "
        "(frequency_threshold=%.4f, min_count=%d, max_count=%d).",
        len(selected),
        len(feature_cols),
        frequency_threshold,
        min_count,
        max_count,
    )
    return selected.index.tolist()


def load_or_project_surface_term_maps(
    decoder,
    surface_cache: Path,
    radius: float,
    interpolation: str,
) -> SurfaceTermMaps:
    """Load cached surface maps or project NiMARE maps to fsaverage5."""

    if surface_cache.is_file():
        LOGGER.info("Loading cached surface term maps: %s", surface_cache)
        payload = np.load(surface_cache, allow_pickle=False)
        return SurfaceTermMaps(
            features=[str(feature) for feature in payload["features"]],
            maps=np.asarray(payload["maps"], dtype=np.float32),
        )

    LOGGER.info("Fetching fsaverage5 meshes")
    fsaverage = datasets.fetch_surf_fsaverage(mesh="fsaverage5")

    features = list(decoder.results_.maps.keys())
    if not features:
        raise RuntimeError("В NiMARE decoder нет карт для декодирования.")

    projected_maps: list[np.ndarray] = []
    for index, feature in enumerate(features, start=1):
        LOGGER.info("Projecting term map %d/%d: %s", index, len(features), feature)
        img = decoder.results_.get_map(feature, return_type="image")
        projected_maps.append(
            project_volume_to_fsaverage5(
                img=img,
                fsaverage=fsaverage,
                radius=radius,
                interpolation=interpolation,
            )
        )

    maps = np.vstack(projected_maps).astype(np.float32)
    np.savez_compressed(
        surface_cache,
        features=np.asarray(features, dtype="U"),
        maps=maps,
    )
    LOGGER.info("Saved surface term maps to %s", surface_cache)

    return SurfaceTermMaps(features=features, maps=maps)


def project_volume_to_fsaverage5(
    img: nib.Nifti1Image,
    fsaverage,
    radius: float,
    interpolation: str,
) -> np.ndarray:
    """Project one MNI volume to left+right fsaverage5 surface vertices."""

    left = vol_to_surf(
        img,
        surf_mesh=fsaverage.pial_left,
        inner_mesh=fsaverage.white_left,
        radius=radius,
        interpolation=interpolation,
    )
    right = vol_to_surf(
        img,
        surf_mesh=fsaverage.pial_right,
        inner_mesh=fsaverage.white_right,
        radius=radius,
        interpolation=interpolation,
    )
    surface = np.concatenate([left, right]).astype(np.float32)

    if surface.shape[0] != FSAVERAGE5_TOTAL_VERTICES:
        raise ValueError(
            "Проекция NiMARE карты дала неожиданное число вершин: "
            f"{surface.shape[0]}."
        )

    return np.nan_to_num(surface, nan=0.0, posinf=0.0, neginf=0.0)


def correlate_activity_with_terms(
    activity: np.ndarray,
    term_maps: SurfaceTermMaps,
    top_k: int,
    min_abs_r: float,
) -> pd.DataFrame:
    """Correlate one TRIBE surface activation vector with NiMARE term maps."""

    validate_surface_vector(activity, "activity")
    if term_maps.maps.ndim != 2:
        raise ValueError(f"term_maps.maps должен быть 2D, получено {term_maps.maps.ndim}D.")
    if term_maps.maps.shape[1] != activity.shape[0]:
        raise ValueError(
            "Размерность term maps не совпадает с TRIBE activity: "
            f"{term_maps.maps.shape[1]} != {activity.shape[0]}."
        )

    activity_z = safe_zscore(activity)
    maps_z = np.vstack([safe_zscore(row) for row in term_maps.maps])
    correlations = maps_z @ activity_z / max(activity_z.size, 1)

    out = pd.DataFrame(
        {
            "feature": term_maps.features,
            "r": correlations.astype(float),
            "abs_r": np.abs(correlations).astype(float),
        }
    )
    out = out.replace([np.inf, -np.inf], np.nan).dropna(subset=["r"])
    out = out.loc[out["abs_r"] >= min_abs_r]
    out = out.sort_values(["r", "abs_r"], ascending=[False, False])

    if top_k > 0:
        out = out.head(top_k)

    return out.reset_index(drop=True)


def validate_surface_vector(vector: np.ndarray, name: str) -> None:
    """Validate fsaverage5 surface vector."""

    if vector.ndim != 1:
        raise ValueError(f"{name} должен быть 1D вектором, получено {vector.ndim}D.")
    if vector.shape[0] != FSAVERAGE5_TOTAL_VERTICES:
        raise ValueError(
            f"{name} должен содержать {FSAVERAGE5_TOTAL_VERTICES} вершин "
            f"fsaverage5, получено {vector.shape[0]}."
        )


def safe_zscore(vector: np.ndarray) -> np.ndarray:
    """Return a finite z-scored vector; constant vectors become zeros."""

    scored = zscore(np.asarray(vector, dtype=np.float64), nan_policy="omit")
    return np.nan_to_num(scored, nan=0.0, posinf=0.0, neginf=0.0)


def save_results(results: pd.DataFrame, output_path: Path) -> None:
    """Save interpretation table as UTF-8 TSV."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(output_path, sep="\t", index=False, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Run TRIBE v2 on text/audio/video and interpret predicted "
            "fsaverage5 activations using NiMARE/Neurosynth term maps."
        )
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Path to .txt, audio, or video file.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/tribe_nimare"),
        help="Directory for predictions, caches, and interpretation TSV.",
    )
    parser.add_argument(
        "--checkpoint",
        default="facebook/tribev2",
        help="TRIBE v2 checkpoint path or HuggingFace repo id.",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("cache/tribev2"),
        help="TRIBE v2 feature/model cache directory.",
    )
    parser.add_argument(
        "--nimare-data-dir",
        type=Path,
        default=Path("cache/nimare"),
        help="Directory where NiMARE downloads Neurosynth data.",
    )
    parser.add_argument(
        "--decoder-cache",
        type=Path,
        default=Path("cache/nimare/correlation_decoder.pkl.gz"),
        help="Path to cached fitted NiMARE CorrelationDecoder.",
    )
    parser.add_argument(
        "--surface-cache",
        type=Path,
        default=Path("cache/nimare/surface_term_maps_fsaverage5.npz"),
        help="Path to cached NiMARE term maps projected to fsaverage5.",
    )
    parser.add_argument(
        "--device",
        default="auto",
        help='Torch device for TRIBE v2, e.g. "auto", "cuda", or "cpu".',
    )
    parser.add_argument(
        "--aggregation",
        choices=("mean", "median", "max_abs"),
        default="mean",
        help="How to aggregate TRIBE time-resolved predictions.",
    )
    parser.add_argument(
        "--transcript-backend",
        choices=("tribe", "hybrid"),
        default="tribe",
        help=(
            "Word transcription backend for video input. `tribe` uses the "
            "default TRIBE/WhisperX path. `hybrid` uses GigaAM timings plus "
            "OpenRouter correction/translation and does not fall back to WhisperX."
        ),
    )
    parser.add_argument(
        "--transcript-source-language",
        default="ru",
        help="Source speech language hint for hybrid transcription.",
    )
    parser.add_argument(
        "--transcript-target-language",
        default="en",
        help="Target language for corrected hybrid text, for example `en` or `ru`.",
    )
    parser.add_argument(
        "--gigaam-model",
        default="v3_e2e_rnnt",
        help="GigaAM model name for hybrid word timing.",
    )
    parser.add_argument(
        "--gigaam-download-root",
        type=Path,
        default=None,
        help=(
            "Directory containing cached GigaAM files named "
            "<model>.ckpt and <model>_tokenizer.model. Defaults to --cache-dir."
        ),
    )
    parser.add_argument(
        "--openrouter-model",
        default="google/gemini-3.5-flash",
        help="OpenRouter model id for hybrid correction/translation.",
    )
    parser.add_argument(
        "--gigaam-chunk-sec",
        type=float,
        default=22.0,
        help="Audio chunk duration for GigaAM hybrid transcription.",
    )
    parser.add_argument(
        "--correction-max-words",
        type=int,
        default=80,
        help="Maximum words per OpenRouter correction request.",
    )
    parser.add_argument(
        "--correction-max-seconds",
        type=float,
        default=20.0,
        help="Maximum media seconds per OpenRouter correction request.",
    )
    parser.add_argument(
        "--correction-min-confidence",
        type=float,
        default=0.55,
        help="Minimum correction confidence needed to replace/translate a word.",
    )
    parser.add_argument(
        "--correction-retries",
        type=int,
        default=2,
        help="Retry count for each OpenRouter correction window.",
    )
    parser.add_argument(
        "--reuse-tribe",
        action="store_true",
        help=(
            "Reuse output-dir/tribe_activity_fsaverage5.npy and skip TRIBE v2 "
            "inference. Useful after NiMARE crashes or for parameter tuning."
        ),
    )
    parser.add_argument(
        "--tribe-only",
        action="store_true",
        help="Run or reuse TRIBE v2 only and skip all NiMARE decoding.",
    )
    parser.add_argument(
        "--frequency-threshold",
        type=float,
        default=0.001,
        help="NiMARE feature frequency threshold.",
    )
    parser.add_argument(
        "--max-features",
        type=int,
        default=0,
        help=(
            "Maximum number of NiMARE annotation features to fit. "
            "Use 0 for all features."
        ),
    )
    parser.add_argument(
        "--min-feature-study-fraction",
        type=float,
        default=0.0,
        help="Drop NiMARE features present in less than this fraction of studies.",
    )
    parser.add_argument(
        "--max-feature-study-fraction",
        type=float,
        default=1.0,
        help="Drop NiMARE features present in more than this fraction of studies.",
    )
    parser.add_argument(
        "--n-cores",
        type=int,
        default=1,
        help="Number of CPU cores for fitting NiMARE decoder.",
    )
    parser.add_argument(
        "--projection-radius",
        type=float,
        default=3.0,
        help="Nilearn vol_to_surf sampling radius in millimeters.",
    )
    parser.add_argument(
        "--projection-interpolation",
        choices=("linear", "nearest"),
        default="linear",
        help="Nilearn vol_to_surf interpolation mode.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=50,
        help="Number of top positive correlations to save. Use 0 for all.",
    )
    parser.add_argument(
        "--min-abs-r",
        type=float,
        default=0.0,
        help="Drop terms with absolute correlation below this threshold.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Reduce logging and hide TRIBE progress bars.",
    )

    return parser.parse_args()


def main() -> None:
    """CLI entry point."""

    args = parse_args()
    configure_logging(verbose=not args.quiet)
    LOGGER.info("tribe_nimare_interpreter build: %s", RUNNER_BUILD_ID)

    output_dir = ensure_output_dir(args.output_dir)
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    args.nimare_data_dir.mkdir(parents=True, exist_ok=True)
    args.decoder_cache.parent.mkdir(parents=True, exist_ok=True)
    args.surface_cache.parent.mkdir(parents=True, exist_ok=True)

    if args.reuse_tribe:
        prediction = load_cached_tribe_prediction(output_dir)
    else:
        prediction = run_tribe_v2(
            input_path=args.input,
            output_dir=output_dir,
            checkpoint=args.checkpoint,
            cache_dir=args.cache_dir,
            device=args.device,
            aggregation=args.aggregation,
            verbose=not args.quiet,
            transcript_backend=args.transcript_backend,
            transcript_source_language=args.transcript_source_language,
            transcript_target_language=args.transcript_target_language,
            gigaam_model=args.gigaam_model,
            gigaam_download_root=args.gigaam_download_root or args.cache_dir,
            openrouter_model=args.openrouter_model,
            gigaam_chunk_sec=args.gigaam_chunk_sec,
            correction_max_words=args.correction_max_words,
            correction_max_seconds=args.correction_max_seconds,
            correction_min_confidence=args.correction_min_confidence,
            correction_retries=args.correction_retries,
        )

    if args.tribe_only:
        print(f"Saved TRIBE predictions: {prediction.prediction_path}")
        print(f"Saved TRIBE activity: {output_dir / 'tribe_activity_fsaverage5.npy'}")
        print(f"Saved TRIBE segments: {prediction.segments_path}")
        return

    decoder = load_or_fit_nimare_decoder(
        data_dir=args.nimare_data_dir,
        decoder_cache=args.decoder_cache,
        frequency_threshold=args.frequency_threshold,
        n_cores=args.n_cores,
        max_features=args.max_features,
        min_feature_study_fraction=args.min_feature_study_fraction,
        max_feature_study_fraction=args.max_feature_study_fraction,
    )
    term_maps = load_or_project_surface_term_maps(
        decoder=decoder,
        surface_cache=args.surface_cache,
        radius=args.projection_radius,
        interpolation=args.projection_interpolation,
    )

    results = correlate_activity_with_terms(
        activity=prediction.activity,
        term_maps=term_maps,
        top_k=args.top_k,
        min_abs_r=args.min_abs_r,
    )
    output_path = output_dir / "nimare_interpretation.tsv"
    save_results(results, output_path)

    print(results.to_string(index=False))
    print(f"\nSaved UTF-8 TSV: {output_path}")
    print(f"Saved TRIBE predictions: {prediction.prediction_path}")
    print(f"Saved TRIBE segments: {prediction.segments_path}")


if __name__ == "__main__":
    main()
