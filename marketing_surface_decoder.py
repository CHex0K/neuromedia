# -*- coding: utf-8 -*-
"""Surface-to-surface marketing decoder for TRIBE v2 fsaverage5 outputs.

Offline build:
    Neurosynth/NiMARE term maps in MNI volume -> fsaverage5 reference maps.

Runtime decode:
    TRIBE v2 fsaverage5 .npy -> correlations with cached reference maps.

This is a proxy interpretation of brain activation, not a direct prediction of
emotions, preferences, or behavior.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import nibabel as nib
import numpy as np
import pandas as pd
from nilearn import datasets
from nilearn.surface import vol_to_surf
from scipy.stats import zscore

LOGGER = logging.getLogger("marketing_surface_decoder")

FSAVERAGE5_VERTICES_PER_HEMISPHERE = 10242
FSAVERAGE5_TOTAL_VERTICES = FSAVERAGE5_VERTICES_PER_HEMISPHERE * 2
MAX_RESOLVED_FEATURES = 60
DEFAULT_FREQUENCY_THRESHOLD = 0.05
MARKETING_PRESET_NAME = "marketing_v2"
REFERENCE_VERSION = "marketing_surface_v2"
HemisphereOrder = Literal["left_then_right", "right_then_left"]
HTTP_TIMEOUT_SECONDS = 120
HTTP_RETRY_ATTEMPTS = 5
HTTP_RETRY_BASE_SLEEP_SECONDS = 3.0
HTTP_USER_AGENT = "neuromedia-marketing-surface-decoder/1.0"
NEUROSYNTH_BASE_URL = "https://neurosynth.org"
NEUROSYNTH_TERM_NAMES_URL = f"{NEUROSYNTH_BASE_URL}/api/analyses/term_names"

MARKETING_PRESET: dict[str, list[str]] = {
    "attention": [
        "attention",
        "visual attention",
        "attentional",
        "orienting",
        "target detection",
        "salience",
        "visual stimuli",
        "distractor",
    ],
    "affect_arousal": [
        "arousal",
        "affective",
        "emotional",
        "emotional stimuli",
        "emotional responses",
    ],
    "affect_valence": [
        "valence",
        "negative affect",
        "disgust",
        "fear",
        "anxiety",
    ],
    "memory": [
        "encoding",
        "subsequent memory",
        "episodic memory",
        "semantic memory",
        "recall",
        "recognition",
        "familiarity",
    ],
    "reward": [
        "reward",
        "reward anticipation",
        "motivation",
        "value",
        "incentive",
        "preference",
        "approach",
        "monetary reward",
        "craving",
    ],
    "social": [
        "social cognition",
        "mentalizing",
        "theory mind",
        "face",
        "gaze",
        "self referential",
        "empathy",
        "social",
    ],
    "cog_clarity": [
        "language",
        "semantic",
        "sentence comprehension",
        "comprehension",
    ],
    "cog_load": [
        "working memory",
        "cognitive control",
        "executive function",
        "inhibition",
        "task difficulty",
    ],
}

NEUROSYNTH_MARKETING_FALLBACK_TERMS = [
    "attention",
    "visual attention",
    "attentional",
    "orienting",
    "target detection",
    "salience",
    "visual stimuli",
    "distractor",
    "arousal",
    "affective",
    "emotional",
    "emotional stimuli",
    "emotional responses",
    "valence",
    "negative affect",
    "disgust",
    "fear",
    "anxiety",
    "encoding",
    "subsequent memory",
    "episodic memory",
    "semantic memory",
    "recall",
    "recognition",
    "familiarity",
    "reward",
    "reward anticipation",
    "motivation",
    "value",
    "incentive",
    "preference",
    "approach",
    "monetary reward",
    "craving",
    "social cognition",
    "mentalizing",
    "theory mind",
    "face",
    "gaze",
    "self referential",
    "empathy",
    "social",
    "language",
    "semantic",
    "sentence comprehension",
    "comprehension",
    "working memory",
    "cognitive control",
    "executive function",
    "inhibition",
    "task difficulty",
]


@dataclass(frozen=True)
class ResolvedFeature:
    """One marketing alias resolved to a real Neurosynth annotation feature."""

    group: str
    alias: str
    feature: str
    match_type: str


@dataclass(frozen=True)
class ResolvedFeatureSet:
    """Resolved marketing preset features and missing aliases."""

    preset: str
    resolved: list[ResolvedFeature]
    missing_aliases: dict[str, list[str]]

    @property
    def unique_features(self) -> list[str]:
        """Return unique feature names preserving resolver order."""

        seen: set[str] = set()
        out: list[str] = []
        for item in self.resolved:
            if item.feature in seen:
                continue
            seen.add(item.feature)
            out.append(item.feature)
        return out


@dataclass(frozen=True)
class ReferenceMaps:
    """Cached fsaverage5 reference maps."""

    maps: np.ndarray
    features: list[str]
    metadata: dict[str, Any]


def configure_logging(verbose: bool) -> None:
    """Configure logging."""

    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def normalize_feature_name(value: str) -> str:
    """Normalize feature names for exact and substring matching."""

    value = value.lower()
    value = re.sub(r"[_\-:/]+", " ", value)
    value = re.sub(r"[^a-z0-9 ]+", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def feature_tail(value: str) -> str:
    """Return a likely term suffix from a NiMARE annotation column."""

    for separator in ("__", "::", ":", "/"):
        if separator in value:
            value = value.split(separator)[-1]
    return value


def slugify(value: str) -> str:
    """Make a stable filesystem-safe feature slug."""

    out = normalize_feature_name(value).replace(" ", "_")
    return out or "feature"


def safe_zscore(vector: np.ndarray) -> np.ndarray:
    """Return finite z-scored vector; constant vectors become zeros."""

    scored = zscore(np.asarray(vector, dtype=np.float64), nan_policy="omit")
    return np.nan_to_num(scored, nan=0.0, posinf=0.0, neginf=0.0)


def sha256_json(payload: Any) -> str:
    """Short SHA-256 hash for JSON-compatible payloads."""

    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def validate_n_cores(n_cores: int) -> None:
    """Forbid full parallel decode settings."""

    if n_cores <= 0:
        raise ValueError("n_cores must be >= 1; n_cores=-1 is disabled.")


class FeatureResolver:
    """Resolve restricted marketing preset aliases to real Neurosynth features."""

    def __init__(self, preset: dict[str, list[str]], max_features: int) -> None:
        if max_features > MAX_RESOLVED_FEATURES:
            raise ValueError(
                f"max_features cannot exceed {MAX_RESOLVED_FEATURES}; got {max_features}."
            )
        self.preset = preset
        self.max_features = max_features

    def resolve(self, annotation_features: list[str]) -> ResolvedFeatureSet:
        """Resolve aliases by exact, normalized, then substring matching."""

        lookup = self._build_lookup(annotation_features)
        resolved: list[ResolvedFeature] = []
        missing: dict[str, list[str]] = {}

        for group, aliases in self.preset.items():
            missing[group] = []
            for alias in aliases:
                match = self._match_alias(alias, annotation_features, lookup)
                if match is None:
                    missing[group].append(alias)
                    LOGGER.warning("Missing marketing alias '%s' in group '%s'.", alias, group)
                    continue
                feature, match_type = match
                resolved.append(
                    ResolvedFeature(
                        group=group,
                        alias=alias,
                        feature=feature,
                        match_type=match_type,
                    )
                )

        resolved_set = ResolvedFeatureSet(
            preset=MARKETING_PRESET_NAME,
            resolved=resolved,
            missing_aliases={key: value for key, value in missing.items() if value},
        )
        unique_count = len(resolved_set.unique_features)
        if unique_count == 0:
            raise RuntimeError(f"No {MARKETING_PRESET_NAME} aliases matched Neurosynth features.")
        if unique_count > self.max_features:
            raise RuntimeError(
                f"Resolved {unique_count} unique features, but maximum allowed is "
                f"{self.max_features}. Reduce aliases or lower --max-resolved-features."
            )

        LOGGER.info("Resolved %d unique %s features.", unique_count, MARKETING_PRESET_NAME)
        return resolved_set

    @staticmethod
    def _build_lookup(annotation_features: list[str]) -> dict[str, str]:
        lookup: dict[str, str] = {}
        for feature in annotation_features:
            lookup[feature.lower()] = feature
            lookup[normalize_feature_name(feature)] = feature
            lookup[normalize_feature_name(feature_tail(feature))] = feature
        return lookup

    @staticmethod
    def _match_alias(
        alias: str,
        annotation_features: list[str],
        lookup: dict[str, str],
    ) -> tuple[str, str] | None:
        alias_lower = alias.lower()
        alias_norm = normalize_feature_name(alias)

        if alias_lower in lookup:
            return lookup[alias_lower], "exact"
        if alias_norm in lookup:
            return lookup[alias_norm], "normalized"

        substring_matches: list[str] = []
        for feature in annotation_features:
            feature_norm = normalize_feature_name(feature)
            tail_norm = normalize_feature_name(feature_tail(feature))
            if alias_norm and (
                f" {alias_norm} " in f" {feature_norm} "
                or f" {alias_norm} " in f" {tail_norm} "
            ):
                substring_matches.append(feature)

        if substring_matches:
            substring_matches.sort(key=lambda value: (len(value), value))
            return substring_matches[0], "substring"

        return None


def load_neurosynth_studyset(data_dir: Path):
    """Fetch or load Neurosynth term annotations through NiMARE."""

    from nimare.extract import fetch_neurosynth

    studysets = fetch_neurosynth(
        data_dir=str(data_dir),
        version="7",
        source="abstract",
        vocab="terms",
    )
    if not studysets:
        raise RuntimeError("NiMARE did not return a Neurosynth studyset.")
    return studysets[0]


def studyset_to_dataset(studyset):
    """Convert Studyset-like objects to Dataset when needed."""

    return studyset.to_dataset() if hasattr(studyset, "to_dataset") else studyset


def get_annotation_features(studyset) -> list[str]:
    """Read real numeric Neurosynth/NiMARE annotation columns."""

    dataset = studyset_to_dataset(studyset)
    annotations = getattr(dataset, "annotations", None)
    if annotations is None:
        raise RuntimeError("NiMARE dataset has no annotations table.")

    id_cols = {"id", "study_id", "contrast_id"}
    features = [
        column
        for column in annotations.columns
        if column not in id_cols and pd.api.types.is_numeric_dtype(annotations[column])
    ]
    if not features:
        raise RuntimeError("No numeric Neurosynth annotation features found.")
    return features


def http_get_bytes(url: str) -> bytes:
    """Download bytes with retries and clear network errors."""

    request = urllib.request.Request(url, headers={"User-Agent": HTTP_USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(1, HTTP_RETRY_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            last_error = exc
            retryable = exc.code in {429, 500, 502, 503, 504}
            if not retryable or attempt == HTTP_RETRY_ATTEMPTS:
                raise RuntimeError(f"HTTP {exc.code} while downloading {url}") from exc
            sleep_seconds = HTTP_RETRY_BASE_SLEEP_SECONDS * attempt
            LOGGER.warning(
                "HTTP %s while downloading %s; retry %d/%d in %.1fs.",
                exc.code,
                url,
                attempt,
                HTTP_RETRY_ATTEMPTS,
                sleep_seconds,
            )
            time.sleep(sleep_seconds)
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt == HTTP_RETRY_ATTEMPTS:
                raise RuntimeError(f"Network error while downloading {url}: {exc}") from exc
            sleep_seconds = HTTP_RETRY_BASE_SLEEP_SECONDS * attempt
            LOGGER.warning(
                "Network error while downloading %s; retry %d/%d in %.1fs: %s",
                url,
                attempt,
                HTTP_RETRY_ATTEMPTS,
                sleep_seconds,
                exc,
            )
            time.sleep(sleep_seconds)

    raise RuntimeError(f"Could not download {url}: {last_error}")


def read_json_cache(path: Path, default: Any) -> Any:
    """Read a UTF-8 JSON cache file or return a default value."""

    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_cache(path: Path, payload: Any) -> None:
    """Write a UTF-8 JSON cache file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_neurosynth_term_names(cache_dir: Path) -> list[str]:
    """Load real Neurosynth term names without materializing a NiMARE dataset."""

    cache_path = cache_dir / "term_names.json"
    payload = read_json_cache(cache_path, default=None)
    if payload is None:
        LOGGER.info("Fetching Neurosynth term names: %s", NEUROSYNTH_TERM_NAMES_URL)
        try:
            payload = json.loads(http_get_bytes(NEUROSYNTH_TERM_NAMES_URL).decode("utf-8"))
            write_json_cache(cache_path, payload)
        except RuntimeError as exc:
            LOGGER.warning(
                "Could not fetch Neurosynth term_names API; using embedded marketing "
                "fallback terms. Cause: %s",
                exc,
            )
            return list(NEUROSYNTH_MARKETING_FALLBACK_TERMS)

    terms = payload.get("data", payload) if isinstance(payload, dict) else payload
    if not isinstance(terms, list) or not terms:
        raise RuntimeError("Neurosynth term_names API returned no terms.")
    return [str(term) for term in terms]


def get_neurosynth_analysis_id(feature: str, cache_dir: Path) -> str:
    """Resolve a Neurosynth term to its analysis id from the public term page."""

    ids_path = cache_dir / "analysis_ids.json"
    analysis_ids: dict[str, str] = read_json_cache(ids_path, default={})
    if feature in analysis_ids:
        return analysis_ids[feature]

    encoded = urllib.parse.quote(feature, safe="")
    url = f"{NEUROSYNTH_BASE_URL}/analyses/terms/{encoded}/"
    LOGGER.info("Resolving Neurosynth analysis id for '%s'", feature)
    html = http_get_bytes(url).decode("utf-8", errors="replace")
    match = re.search(r'var\s+analysis\s*=\s*"(\d+)"', html)
    if match is None:
        raise RuntimeError(
            f"Could not resolve Neurosynth analysis id for feature '{feature}'. "
            "Remove this alias from the preset or choose another Neurosynth term."
        )

    analysis_ids[feature] = match.group(1)
    write_json_cache(ids_path, analysis_ids)
    return analysis_ids[feature]


def download_neurosynth_association_map(
    feature: str,
    cache_dir: Path,
    unthresholded: bool,
) -> tuple[Path, str, str]:
    """Download one precomputed Neurosynth association map and return its path."""

    analysis_id = get_neurosynth_analysis_id(feature, cache_dir)
    map_kind = "association_unthresholded" if unthresholded else "association_fdr001"
    map_dir = cache_dir / "mni_maps" / map_kind
    map_dir.mkdir(parents=True, exist_ok=True)
    target = map_dir / f"{slugify(feature)}_{analysis_id}.nii.gz"
    url = f"{NEUROSYNTH_BASE_URL}/api/analyses/{analysis_id}/images/association"
    if unthresholded:
        url = f"{url}?unthresholded"

    if target.is_file() and target.stat().st_size > 0:
        return target, analysis_id, url

    LOGGER.info("Downloading Neurosynth map for '%s': %s", feature, url)
    tmp_path = target.with_name(f"{target.name}.tmp")
    tmp_path.write_bytes(http_get_bytes(url))

    tmp_path.replace(target)
    return target, analysis_id, url


def resolved_features_payload(
    resolved: ResolvedFeatureSet,
    annotation_feature_count: int,
    feature_source: str,
) -> dict[str, Any]:
    """Build serializable resolver metadata."""

    return {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "preset": resolved.preset,
        "groups": list(MARKETING_PRESET.keys()),
        "max_resolved_features": MAX_RESOLVED_FEATURES,
        "feature_source": feature_source,
        "n_annotation_features": annotation_feature_count,
        "n_unique_resolved_features": len(resolved.unique_features),
        "unique_features": resolved.unique_features,
        "resolved": [asdict(item) for item in resolved.resolved],
        "missing_aliases": resolved.missing_aliases,
    }


def fit_restricted_decoder(
    studyset,
    features: list[str],
    frequency_threshold: float,
    n_cores: int,
):
    """Fit a restricted NiMARE decoder only for the configured marketing preset."""

    from nimare.decode.continuous import CorrelationDecoder
    from nimare.meta.cbma import mkda

    validate_n_cores(n_cores)
    if len(features) > MAX_RESOLVED_FEATURES:
        raise ValueError(
            f"Refusing to fit {len(features)} features. Maximum is {MAX_RESOLVED_FEATURES}."
        )

    LOGGER.info(
        "Fitting restricted NiMARE decoder for %d features. Full decode is disabled.",
        len(features),
    )
    decoder = CorrelationDecoder(
        features=features,
        frequency_threshold=frequency_threshold,
        meta_estimator=mkda.MKDAChi2,
        target_image="z_desc-association",
        n_cores=n_cores,
    )
    decoder.fit(studyset)
    return decoder


def project_volume_to_fsaverage5(
    img: nib.Nifti1Image,
    fsaverage,
    radius: float,
    interpolation: str,
) -> np.ndarray:
    """Project one MNI volume to fsaverage5 left-then-right surface vector."""

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
    if surface.shape != (FSAVERAGE5_TOTAL_VERTICES,):
        raise ValueError(
            f"Unexpected fsaverage5 projection shape: {surface.shape}; "
            f"expected {(FSAVERAGE5_TOTAL_VERTICES,)}."
        )
    return np.nan_to_num(surface, nan=0.0, posinf=0.0, neginf=0.0)


def build_reference_maps(args: argparse.Namespace) -> None:
    """Offline reference build command."""

    validate_n_cores(args.n_cores)
    if args.max_resolved_features > MAX_RESOLVED_FEATURES:
        raise ValueError(
            f"--max-resolved-features cannot exceed {MAX_RESOLVED_FEATURES}."
        )

    reference_maps_path = args.references_dir / "reference_maps.npy"
    metadata_path = args.references_dir / "reference_metadata.json"
    resolved_path = args.references_dir / "resolved_features.json"
    individual_dir = args.references_dir / "maps"

    if reference_maps_path.is_file() and metadata_path.is_file() and not args.overwrite:
        existing_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        existing_source = existing_metadata.get("reference_source", "nimare_fit")
        if existing_source == args.reference_source:
            LOGGER.info("Reference maps already exist: %s", reference_maps_path)
            return
        LOGGER.info(
            "Existing references use source '%s'; rebuilding with source '%s'.",
            existing_source,
            args.reference_source,
        )

    args.references_dir.mkdir(parents=True, exist_ok=True)
    individual_dir.mkdir(parents=True, exist_ok=True)

    fsaverage = datasets.fetch_surf_fsaverage(mesh="fsaverage5")
    resolver = FeatureResolver(MARKETING_PRESET, max_features=args.max_resolved_features)

    if args.reference_source == "neurosynth_precomputed":
        cache_dir = args.neurosynth_cache_dir or (args.references_dir / "neurosynth_api_cache")
        cache_dir.mkdir(parents=True, exist_ok=True)
        annotation_features = load_neurosynth_term_names(cache_dir)
        resolved = resolver.resolve(annotation_features)
        features = resolved.unique_features

        maps: list[np.ndarray] = []
        source_maps: list[dict[str, str]] = []
        for index, feature in enumerate(features, start=1):
            LOGGER.info(
                "Projecting precomputed Neurosynth map %d/%d: %s",
                index,
                len(features),
                feature,
            )
            map_path, analysis_id, source_url = download_neurosynth_association_map(
                feature=feature,
                cache_dir=cache_dir,
                unthresholded=not args.use_thresholded_maps,
            )
            img = nib.load(str(map_path))
            surface = project_volume_to_fsaverage5(
                img=img,
                fsaverage=fsaverage,
                radius=args.projection_radius,
                interpolation=args.projection_interpolation,
            )
            maps.append(surface)
            np.save(individual_dir / f"{slugify(feature)}.npy", surface)
            source_maps.append(
                {
                    "feature": feature,
                    "analysis_id": analysis_id,
                    "source_url": source_url,
                    "cached_mni_map": str(map_path),
                }
            )

        reference_source = "neurosynth_precomputed"
        feature_source = NEUROSYNTH_TERM_NAMES_URL
        map_source_metadata: dict[str, Any] = {
            "neurosynth_api_base": NEUROSYNTH_BASE_URL,
            "mni_map_kind": (
                "association_unthresholded"
                if not args.use_thresholded_maps
                else "association_fdr001"
            ),
            "source_maps": source_maps,
        }
    elif args.reference_source == "nimare_fit":
        args.nimare_data_dir.mkdir(parents=True, exist_ok=True)
        studyset = load_neurosynth_studyset(args.nimare_data_dir)
        annotation_features = get_annotation_features(studyset)
        resolved = resolver.resolve(annotation_features)

        decoder = fit_restricted_decoder(
            studyset=studyset,
            features=resolved.unique_features,
            frequency_threshold=args.frequency_threshold,
            n_cores=args.n_cores,
        )

        maps = []
        features = list(decoder.results_.maps.keys())
        if len(features) > MAX_RESOLVED_FEATURES:
            raise RuntimeError("Decoder returned too many features; full decode is disabled.")

        for index, feature in enumerate(features, start=1):
            LOGGER.info("Projecting fitted NiMARE map %d/%d: %s", index, len(features), feature)
            img = decoder.results_.get_map(feature, return_type="image")
            surface = project_volume_to_fsaverage5(
                img=img,
                fsaverage=fsaverage,
                radius=args.projection_radius,
                interpolation=args.projection_interpolation,
            )
            maps.append(surface)
            np.save(individual_dir / f"{slugify(feature)}.npy", surface)

        reference_source = "nimare_fit"
        feature_source = "NiMARE Neurosynth annotations"
        map_source_metadata = {
            "nimare_data_dir": str(args.nimare_data_dir),
            "frequency_threshold": args.frequency_threshold,
        }
    else:
        raise ValueError(f"Unknown reference source: {args.reference_source}")

    reference_maps = np.vstack(maps).astype(np.float32)
    np.save(reference_maps_path, reference_maps)

    resolved_payload = resolved_features_payload(
        resolved=resolved,
        annotation_feature_count=len(annotation_features),
        feature_source=feature_source,
    )
    metadata = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "version": REFERENCE_VERSION,
        "reference_source": reference_source,
        "space": "fsaverage5",
        "hemisphere_order": "left_then_right",
        "shape": list(reference_maps.shape),
        "vertices_per_hemisphere": FSAVERAGE5_VERTICES_PER_HEMISPHERE,
        "features": features,
        "features_hash": sha256_json(features),
        "preset": MARKETING_PRESET_NAME,
        "max_resolved_features": args.max_resolved_features,
        "projection_radius": args.projection_radius,
        "projection_interpolation": args.projection_interpolation,
        "proxy_interpretation_warning": (
            "Scores are proxy correlations with Neurosynth-derived reference maps, "
            "not direct predictions of emotions or behavior."
        ),
    }
    metadata.update(map_source_metadata)
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    resolved_path.write_text(
        json.dumps(resolved_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    LOGGER.info("Saved reference maps: %s", reference_maps_path)


def load_reference_maps(references_dir: Path) -> ReferenceMaps:
    """Load cached fsaverage5 reference maps."""

    maps_path = references_dir / "reference_maps.npy"
    metadata_path = references_dir / "reference_metadata.json"
    if not maps_path.is_file():
        raise FileNotFoundError(
            f"Reference maps not found: {maps_path}. Run build-references first."
        )
    if not metadata_path.is_file():
        raise FileNotFoundError(f"Reference metadata not found: {metadata_path}.")

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    maps = np.load(maps_path).astype(np.float32)
    features = [str(feature) for feature in metadata.get("features", [])]
    if maps.ndim != 2 or maps.shape[1] != FSAVERAGE5_TOTAL_VERTICES:
        raise ValueError(
            f"Reference maps must have shape (n, {FSAVERAGE5_TOTAL_VERTICES}); "
            f"got {maps.shape}."
        )
    if maps.shape[0] != len(features):
        raise ValueError("Reference map count does not match metadata feature count.")
    if len(features) > MAX_RESOLVED_FEATURES:
        raise ValueError("Reference cache contains too many features; full decode is disabled.")
    if metadata.get("hemisphere_order") != "left_then_right":
        raise ValueError("Reference maps must use left_then_right hemisphere order.")
    return ReferenceMaps(maps=maps, features=features, metadata=metadata)


def map_id_from_path(path: Path) -> str:
    """Create stable map id from an input path."""

    return path.stem


def collect_npy_inputs(paths: list[Path]) -> list[Path]:
    """Collect .npy inputs from files and directories."""

    out: list[Path] = []
    for path in paths:
        if path.is_dir():
            out.extend(sorted(candidate for candidate in path.rglob("*.npy") if candidate.is_file()))
        elif path.is_file() and path.suffix.lower() == ".npy":
            out.append(path)
        elif path.exists():
            raise ValueError(f"Runtime input must be .npy fsaverage5 surface map: {path}")
        else:
            raise FileNotFoundError(f"Input path not found: {path}")
    if not out:
        raise FileNotFoundError("No .npy runtime inputs found.")
    return out


def load_tribe_surface(path: Path, hemisphere_order: HemisphereOrder) -> np.ndarray:
    """Load and validate TRIBE fsaverage5 runtime input."""

    arr = np.load(path).astype(np.float32)
    if arr.ndim == 1:
        arr = arr[None, :]
    elif arr.ndim != 2:
        raise ValueError(f"TRIBE input must be 1D or 2D, got shape={arr.shape}: {path}")
    if arr.shape[1] != FSAVERAGE5_TOTAL_VERTICES:
        raise ValueError(
            f"TRIBE input must have {FSAVERAGE5_TOTAL_VERTICES} vertices, "
            f"got shape={arr.shape}: {path}"
        )
    if not np.isfinite(arr).all():
        raise ValueError(f"TRIBE input contains NaN or Inf: {path}")
    if np.all(arr == 0):
        raise ValueError(f"TRIBE input is all zero: {path}")
    zero_rows = np.flatnonzero(np.all(arr == 0, axis=1))
    if zero_rows.size:
        LOGGER.warning(
            "TRIBE input has all-zero timepoints %s; they will decode to neutral scores: %s",
            zero_rows.tolist(),
            path,
        )

    if hemisphere_order == "right_then_left":
        left = arr[:, FSAVERAGE5_VERTICES_PER_HEMISPHERE:]
        right = arr[:, :FSAVERAGE5_VERTICES_PER_HEMISPHERE]
        arr = np.concatenate([left, right], axis=1)
    elif hemisphere_order != "left_then_right":
        raise ValueError(f"Unknown hemisphere order: {hemisphere_order}")

    return arr


def load_resolved_features(references_dir: Path) -> ResolvedFeatureSet:
    """Load resolver output saved during offline reference build."""

    path = references_dir / "resolved_features.json"
    if not path.is_file():
        raise FileNotFoundError(f"Resolved features file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    resolved = [
        ResolvedFeature(
            group=item["group"],
            alias=item["alias"],
            feature=item["feature"],
            match_type=item["match_type"],
        )
        for item in payload["resolved"]
    ]
    return ResolvedFeatureSet(
        preset=payload["preset"],
        resolved=resolved,
        missing_aliases=payload.get("missing_aliases", {}),
    )


def correlate_timepoints(activity: np.ndarray, refs: ReferenceMaps) -> np.ndarray:
    """Correlate each timepoint with each fsaverage5 reference map."""

    activity_z = np.vstack([safe_zscore(row) for row in activity])
    refs_z = np.vstack([safe_zscore(row) for row in refs.maps])
    return activity_z @ refs_z.T / FSAVERAGE5_TOTAL_VERTICES


def build_decoded_terms(
    input_path: Path,
    activity: np.ndarray,
    correlations: np.ndarray,
    refs: ReferenceMaps,
    resolved: ResolvedFeatureSet,
) -> pd.DataFrame:
    """Create term-level decode table."""

    rows: list[dict[str, Any]] = []
    feature_to_indices: dict[str, list[ResolvedFeature]] = {}
    for item in resolved.resolved:
        feature_to_indices.setdefault(item.feature, []).append(item)

    for time_index in range(activity.shape[0]):
        for feature_index, feature in enumerate(refs.features):
            matched_items = feature_to_indices.get(feature, [])
            if not matched_items:
                matched_items = [
                    ResolvedFeature(
                        group="unassigned",
                        alias=feature,
                        feature=feature,
                        match_type="reference",
                    )
                ]
            for item in matched_items:
                rows.append(
                    {
                        "map_id": map_id_from_path(input_path),
                        "map_path": str(input_path),
                        "time_index": time_index,
                        "group": item.group,
                        "alias": item.alias,
                        "feature": feature,
                        "match_type": item.match_type,
                        "r": float(correlations[time_index, feature_index]),
                    }
                )

    return pd.DataFrame(rows)


def aggregate_marketing_scores(decoded_terms: pd.DataFrame) -> pd.DataFrame:
    """Aggregate term correlations into per-group marketing proxy scores."""

    rows: list[dict[str, Any]] = []
    grouped = decoded_terms.groupby(["map_id", "map_path", "time_index", "group"], sort=True)
    for (map_id, map_path, time_index, group), group_df in grouped:
        unique = group_df.drop_duplicates(subset=["feature"])
        r = unique["r"].to_numpy(dtype=np.float64)
        clipped = np.clip(r, -0.999999, 0.999999)
        mean_r = float(np.tanh(np.mean(np.arctanh(clipped))))
        rows.append(
            {
                "map_id": map_id,
                "map_path": map_path,
                "time_index": time_index,
                "group": group,
                "score_0_100": 50.0 + 50.0 * mean_r,
                "mean_r": mean_r,
                "mean_abs_r": float(np.mean(np.abs(r))),
                "n_features": int(unique.shape[0]),
                "features": ", ".join(unique["feature"].tolist()),
            }
        )

    per_time = pd.DataFrame(rows)
    aggregate_rows: list[dict[str, Any]] = []
    for (map_id, map_path, group), group_df in per_time.groupby(["map_id", "map_path", "group"]):
        mean_r = float(group_df["mean_r"].mean())
        aggregate_rows.append(
            {
                "map_id": map_id,
                "map_path": map_path,
                "time_index": "aggregate",
                "group": group,
                "score_0_100": 50.0 + 50.0 * mean_r,
                "mean_r": mean_r,
                "mean_abs_r": float(group_df["mean_abs_r"].mean()),
                "n_features": int(group_df["n_features"].max()),
                "features": group_df["features"].iloc[0],
            }
        )

    out = pd.concat([per_time, pd.DataFrame(aggregate_rows)], ignore_index=True)
    out["_time_sort"] = out["time_index"].apply(
        lambda value: 10**9 if str(value) == "aggregate" else int(value)
    )
    out = out.sort_values(["map_id", "_time_sort", "score_0_100"], ascending=[True, True, False])
    return out.drop(columns=["_time_sort"])


def write_decode_outputs(
    output_dir: Path,
    decoded_terms: pd.DataFrame,
    marketing_scores: pd.DataFrame,
    report: dict[str, Any],
) -> None:
    """Save runtime decode outputs."""

    output_dir.mkdir(parents=True, exist_ok=True)
    decoded_terms.to_csv(output_dir / "decoded_terms.csv", index=False, encoding="utf-8")
    marketing_scores.to_csv(output_dir / "marketing_scores.csv", index=False, encoding="utf-8")
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def decode_runtime(args: argparse.Namespace) -> None:
    """Runtime decode command."""

    refs = load_reference_maps(args.references_dir)
    resolved = load_resolved_features(args.references_dir)
    input_paths = collect_npy_inputs(args.inputs)

    decoded_tables: list[pd.DataFrame] = []
    report_inputs: list[dict[str, Any]] = []
    for path in input_paths:
        activity = load_tribe_surface(path, args.hemisphere_order)
        correlations = correlate_timepoints(activity, refs)
        decoded_tables.append(
            build_decoded_terms(
                input_path=path,
                activity=activity,
                correlations=correlations,
                refs=refs,
                resolved=resolved,
            )
        )
        report_inputs.append(
            {
                "path": str(path),
                "shape": list(activity.shape),
                "hemisphere_order_input": args.hemisphere_order,
                "hemisphere_order_decoded": "left_then_right",
            }
        )

    decoded_terms = pd.concat(decoded_tables, ignore_index=True)
    marketing_scores = aggregate_marketing_scores(decoded_terms)
    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "backend": "SurfaceFsaverageDecoderBackend",
        "reference_version": refs.metadata.get("version"),
        "reference_features": refs.features,
        "reference_features_hash": refs.metadata.get("features_hash"),
        "space": "fsaverage5",
        "runtime_input_contract": {
            "accepted": [".npy shape=(20484,)", ".npy shape=(T, 20484)"],
            "rejected": ["NIfTI runtime input", "raw TRIBE embeddings", "video/audio/text"],
        },
        "inputs": report_inputs,
        "proxy_interpretation_warning": (
            "Scores are proxy correlations with Neurosynth-derived reference maps, "
            "not direct predictions of emotions, preferences, or behavior."
        ),
    }
    write_decode_outputs(args.output_dir, decoded_terms, marketing_scores, report)

    aggregate = marketing_scores[marketing_scores["time_index"].astype(str) == "aggregate"]
    print(aggregate.to_string(index=False))
    print(f"\nSaved CSV: {args.output_dir / 'decoded_terms.csv'}")
    print(f"Saved CSV: {args.output_dir / 'marketing_scores.csv'}")
    print(f"Saved JSON: {args.output_dir / 'report.json'}")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description="SurfaceFsaverageDecoderBackend for TRIBE v2 fsaverage5 outputs."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser(
        "build-references",
        help="Offline build of fsaverage5 Neurosynth reference maps.",
    )
    build.add_argument("--references-dir", type=Path, required=True)
    build.add_argument(
        "--reference-source",
        choices=("neurosynth_precomputed", "nimare_fit"),
        default="neurosynth_precomputed",
        help=(
            "neurosynth_precomputed downloads ready Neurosynth association maps and is "
            "the Colab-safe default. nimare_fit is a legacy heavy mode."
        ),
    )
    build.add_argument(
        "--neurosynth-cache-dir",
        type=Path,
        default=None,
        help="Cache for Neurosynth term names, analysis ids, and downloaded MNI maps.",
    )
    build.add_argument("--nimare-data-dir", type=Path, default=Path("cache/nimare"))
    build.add_argument("--frequency-threshold", type=float, default=DEFAULT_FREQUENCY_THRESHOLD)
    build.add_argument("--max-resolved-features", type=int, default=MAX_RESOLVED_FEATURES)
    build.add_argument("--n-cores", type=int, default=1)
    build.add_argument("--projection-radius", type=float, default=3.0)
    build.add_argument(
        "--projection-interpolation",
        choices=("linear", "nearest"),
        default="linear",
    )
    build.add_argument(
        "--use-thresholded-maps",
        action="store_true",
        help="Use smaller FDR 0.01 thresholded Neurosynth maps instead of unthresholded maps.",
    )
    build.add_argument("--overwrite", action="store_true")
    build.add_argument("--quiet", action="store_true")

    decode = subparsers.add_parser(
        "decode",
        help="Runtime decode TRIBE fsaverage5 .npy maps against cached references.",
    )
    decode.add_argument("inputs", nargs="+", type=Path)
    decode.add_argument("--references-dir", type=Path, required=True)
    decode.add_argument("--output-dir", type=Path, required=True)
    decode.add_argument(
        "--hemisphere-order",
        choices=("left_then_right", "right_then_left"),
        default="left_then_right",
    )
    decode.add_argument("--quiet", action="store_true")

    return parser.parse_args()


def main() -> None:
    """CLI entry point."""

    args = parse_args()
    configure_logging(verbose=not args.quiet)
    if args.command == "build-references":
        build_reference_maps(args)
    elif args.command == "decode":
        decode_runtime(args)
    else:
        raise ValueError(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
