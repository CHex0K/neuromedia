# -*- coding: utf-8 -*-
"""Lightweight marketing decoder for NIfTI brain activation maps.

Decoder принимает только валидные NIfTI карты активации мозга и считает
маркетинговые индексы по заранее заданным neurocognitive feature groups.
Полный Neurosynth/NiMARE decode намеренно не поддерживается.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np
import pandas as pd

LOGGER = logging.getLogger("marketing_nifti_decoder")

MAX_RESOLVED_FEATURES = 60
DEFAULT_FREQUENCY_THRESHOLD = 0.05

MARKETING_V1: dict[str, list[str]] = {
    "attention_salience": [
        "attention",
        "attentional",
        "salience",
        "orienting",
        "target",
        "visual attention",
    ],
    "reward_value": [
        "reward",
        "value",
        "valuation",
        "incentive",
        "motivation",
        "preference",
        "reinforcement",
    ],
    "memory_encoding": [
        "memory",
        "encoding",
        "recall",
        "recognition",
        "episodic",
        "retrieval",
        "familiarity",
    ],
    "emotion_affect": [
        "emotion",
        "emotional",
        "affective",
        "affect",
        "arousal",
        "valence",
        "pleasant",
        "unpleasant",
    ],
    "social_self": [
        "social",
        "mentalizing",
        "self",
        "self referential",
        "person",
        "people",
        "face",
        "faces",
        "theory of mind",
    ],
    "aversion_risk": [
        "fear",
        "threat",
        "anxiety",
        "pain",
        "disgust",
        "negative",
        "aversive",
    ],
    "language_narrative": [
        "language",
        "speech",
        "semantic",
        "comprehension",
        "narrative",
        "story",
        "sentence",
    ],
    "action_embodiment": [
        "action",
        "motor",
        "movement",
        "hand",
        "gesture",
        "execution",
    ],
}


@dataclass(frozen=True)
class ResolvedFeature:
    """One matched preset alias and the real NiMARE annotation feature."""

    group: str
    alias: str
    feature: str
    match_type: str


@dataclass(frozen=True)
class ResolvedFeatureSet:
    """Resolved features plus missing preset aliases."""

    preset: str
    resolved: list[ResolvedFeature]
    missing_aliases: dict[str, list[str]]

    @property
    def unique_features(self) -> list[str]:
        """Return unique features preserving resolver order."""

        seen: set[str] = set()
        features: list[str] = []
        for item in self.resolved:
            if item.feature in seen:
                continue
            seen.add(item.feature)
            features.append(item.feature)
        return features


def configure_logging(verbose: bool) -> None:
    """Configure process-wide logging."""

    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def normalize_feature_name(value: str) -> str:
    """Normalize feature labels for robust exact/substring matching."""

    value = value.lower()
    value = re.sub(r"[_\-:/]+", " ", value)
    value = re.sub(r"[^a-z0-9 ]+", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def feature_tail(value: str) -> str:
    """Return likely term suffix from a NiMARE annotation column."""

    for separator in ("__", "::", ":", "/"):
        if separator in value:
            value = value.split(separator)[-1]
    return value


def is_nifti_path(path: Path) -> bool:
    """Check NIfTI extension without accepting raw arrays or embeddings."""

    name = path.name.lower()
    return name.endswith(".nii") or name.endswith(".nii.gz")


def map_id_from_path(path: Path) -> str:
    """Create a stable map identifier from a NIfTI path."""

    name = path.name
    if name.endswith(".nii.gz"):
        return name[:-7]
    if name.endswith(".nii"):
        return name[:-4]
    return path.stem


def collect_nifti_inputs(paths: list[Path]) -> list[Path]:
    """Collect valid NIfTI inputs from files and directories."""

    out: list[Path] = []
    for path in paths:
        if path.is_dir():
            out.extend(
                sorted(
                    candidate
                    for candidate in path.rglob("*")
                    if candidate.is_file() and is_nifti_path(candidate)
                )
            )
        elif path.is_file() and is_nifti_path(path):
            out.append(path)
        elif path.exists():
            raise ValueError(
                f"Unsupported input file: {path}. Decoder accepts only .nii/.nii.gz."
            )
        else:
            raise FileNotFoundError(f"Input path not found: {path}")

    if not out:
        raise FileNotFoundError("No .nii/.nii.gz activation maps found.")

    return out


def validate_nifti_map(path: Path) -> nib.Nifti1Image:
    """Load and validate a 3D NIfTI activation map."""

    if not is_nifti_path(path):
        raise ValueError(f"Not a NIfTI file: {path}")

    img = nib.load(str(path))
    if not isinstance(img, nib.Nifti1Image):
        raise ValueError(f"Expected Nifti1Image, got {type(img).__name__}: {path}")
    if len(img.shape) != 3:
        raise ValueError(f"Expected a 3D NIfTI activation map, got shape={img.shape}: {path}")

    data = np.asanyarray(img.dataobj)
    if not np.isfinite(data).any():
        raise ValueError(f"NIfTI map has no finite values: {path}")

    return img


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
    """Read real numeric NiMARE/Neurosynth annotation columns."""

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
        raise RuntimeError("No numeric Neurosynth annotation features were found.")

    return features


class FeatureResolver:
    """Resolve marketing_v1 aliases to real NiMARE/Neurosynth features."""

    def __init__(self, preset: dict[str, list[str]], max_features: int) -> None:
        if max_features > MAX_RESOLVED_FEATURES:
            raise ValueError(
                f"max_features cannot exceed {MAX_RESOLVED_FEATURES}; got {max_features}."
            )
        self.preset = preset
        self.max_features = max_features

    def resolve(self, annotation_features: list[str]) -> ResolvedFeatureSet:
        """Resolve aliases with exact, normalized, then substring matching."""

        lookup = self._build_lookup(annotation_features)
        resolved: list[ResolvedFeature] = []
        missing: dict[str, list[str]] = {}

        for group, aliases in self.preset.items():
            missing[group] = []
            for alias in aliases:
                match = self._match_alias(alias, annotation_features, lookup)
                if match is None:
                    missing[group].append(alias)
                    LOGGER.warning("Missing alias for group '%s': %s", group, alias)
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
            preset="marketing_v1",
            resolved=resolved,
            missing_aliases={key: value for key, value in missing.items() if value},
        )
        n_unique = len(resolved_set.unique_features)
        if n_unique == 0:
            raise RuntimeError("No marketing_v1 aliases matched Neurosynth features.")
        if n_unique > self.max_features:
            raise RuntimeError(
                f"Resolved {n_unique} unique features, but max allowed is "
                f"{self.max_features}. Reduce aliases or lower --max-resolved-features."
            )

        LOGGER.info("Resolved %d unique marketing_v1 features.", n_unique)
        return resolved_set

    @staticmethod
    def _build_lookup(annotation_features: list[str]) -> dict[str, str]:
        lookup: dict[str, str] = {}
        for feature in annotation_features:
            candidates = {
                feature.lower(): feature,
                normalize_feature_name(feature): feature,
                normalize_feature_name(feature_tail(feature)): feature,
            }
            lookup.update(candidates)
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
            if alias_norm in {feature_norm, tail_norm}:
                return feature, "normalized"
            if alias_norm and (
                f" {alias_norm} " in f" {feature_norm} "
                or f" {alias_norm} " in f" {tail_norm} "
            ):
                substring_matches.append(feature)

        if substring_matches:
            substring_matches.sort(key=lambda item: (len(item), item))
            return substring_matches[0], "substring"

        return None


def save_resolved_features(
    resolved: ResolvedFeatureSet,
    annotation_features: list[str],
    output_path: Path,
) -> None:
    """Save resolved feature metadata to UTF-8 JSON."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "preset": resolved.preset,
        "max_resolved_features": MAX_RESOLVED_FEATURES,
        "n_annotation_features": len(annotation_features),
        "n_unique_resolved_features": len(resolved.unique_features),
        "unique_features": resolved.unique_features,
        "resolved": [asdict(item) for item in resolved.resolved],
        "missing_aliases": resolved.missing_aliases,
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def features_hash(features: list[str]) -> str:
    """Hash feature list for decoder cache validation."""

    encoded = json.dumps(features, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def decoder_meta_path(decoder_cache: Path) -> Path:
    """Return metadata sidecar path for a decoder cache."""

    return decoder_cache.with_suffix(decoder_cache.suffix + ".json")


def load_or_fit_decoder(
    studyset,
    features: list[str],
    decoder_cache: Path,
    frequency_threshold: float,
    n_cores: int,
    fit_if_missing: bool,
    overwrite_cache: bool,
):
    """Load cached NiMARE decoder or fit the marketing-only feature subset."""

    from nimare.decode.continuous import CorrelationDecoder
    from nimare.meta.cbma import mkda

    if n_cores <= 0:
        raise ValueError("n_cores must be >= 1. Full parallel decode is disabled.")
    if len(features) > MAX_RESOLVED_FEATURES:
        raise ValueError(
            f"Refusing to fit {len(features)} features. Maximum is {MAX_RESOLVED_FEATURES}."
        )

    meta_path = decoder_meta_path(decoder_cache)
    expected_meta = {
        "preset": "marketing_v1",
        "features_hash": features_hash(features),
        "features": features,
        "frequency_threshold": frequency_threshold,
        "target_image": "z_desc-association",
        "estimator": "MKDAChi2",
    }

    if decoder_cache.is_file() and meta_path.is_file() and not overwrite_cache:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta != expected_meta:
            raise RuntimeError(
                f"Decoder cache metadata mismatch: {meta_path}. "
                "Use --overwrite-cache or a different --decoder-cache."
            )
        LOGGER.info("Loading cached marketing decoder: %s", decoder_cache)
        return CorrelationDecoder.load(str(decoder_cache))

    if decoder_cache.is_file() and not meta_path.is_file() and not overwrite_cache:
        raise RuntimeError(
            f"Decoder cache exists without metadata: {decoder_cache}. "
            "Use --overwrite-cache or remove the stale cache."
        )

    if not fit_if_missing and not decoder_cache.is_file():
        raise FileNotFoundError(
            f"Decoder cache not found: {decoder_cache}. "
            "Run once without --no-fit-if-missing to create it."
        )

    if overwrite_cache:
        decoder_cache.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)

    LOGGER.info(
        "Fitting marketing-only NiMARE decoder with %d features. This is not full decode.",
        len(features),
    )
    decoder_cache.parent.mkdir(parents=True, exist_ok=True)
    decoder = CorrelationDecoder(
        features=features,
        frequency_threshold=frequency_threshold,
        meta_estimator=mkda.MKDAChi2,
        target_image="z_desc-association",
        n_cores=n_cores,
    )
    decoder.fit(studyset)
    decoder.save(str(decoder_cache))
    meta_path.write_text(
        json.dumps(expected_meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return decoder


def score_feature_correlations(
    map_path: Path,
    img: nib.Nifti1Image,
    decoder,
    resolved: ResolvedFeatureSet,
) -> pd.DataFrame:
    """Decode one NIfTI map and return feature-level marketing scores."""

    decoded = decoder.transform(img)
    decoded = decoded.reset_index()
    if "feature" not in decoded.columns or "r" not in decoded.columns:
        raise RuntimeError("Unexpected NiMARE decoder output; expected feature/r columns.")

    resolved_df = pd.DataFrame([asdict(item) for item in resolved.resolved])
    out = resolved_df.merge(decoded, on="feature", how="inner")
    out.insert(0, "map_id", map_id_from_path(map_path))
    out.insert(1, "map_path", str(map_path))
    out["r"] = out["r"].astype(float)
    out["abs_r"] = out["r"].abs()
    return out.sort_values(["group", "r"], ascending=[True, False]).reset_index(drop=True)


def aggregate_group_indices(feature_scores: pd.DataFrame) -> pd.DataFrame:
    """Aggregate feature correlations into marketing group indices."""

    rows: list[dict[str, Any]] = []
    for (map_id, map_path, group), group_df in feature_scores.groupby(
        ["map_id", "map_path", "group"], sort=True
    ):
        unique = group_df.drop_duplicates(subset=["feature"])
        r = unique["r"].to_numpy(dtype=np.float64)
        clipped = np.clip(r, -0.999999, 0.999999)
        mean_z = float(np.mean(np.arctanh(clipped)))
        mean_r = float(np.tanh(mean_z))
        rows.append(
            {
                "map_id": map_id,
                "map_path": map_path,
                "group": group,
                "index_0_100": 50.0 + 50.0 * mean_r,
                "mean_r": mean_r,
                "mean_abs_r": float(np.mean(np.abs(r))),
                "n_features": int(unique.shape[0]),
                "features": ", ".join(unique["feature"].tolist()),
                "aliases": ", ".join(sorted(set(group_df["alias"].tolist()))),
            }
        )

    return pd.DataFrame(rows).sort_values(["map_id", "index_0_100"], ascending=[True, False])


def write_tables(
    output_dir: Path,
    feature_scores: pd.DataFrame,
    group_indices: pd.DataFrame,
) -> None:
    """Write decoder outputs as UTF-8 TSV files."""

    output_dir.mkdir(parents=True, exist_ok=True)
    feature_scores.to_csv(
        output_dir / "marketing_feature_scores.tsv",
        sep="\t",
        index=False,
        encoding="utf-8",
    )
    group_indices.to_csv(
        output_dir / "marketing_indices.tsv",
        sep="\t",
        index=False,
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Lightweight zero-shot marketing decoder for valid NIfTI brain maps. "
            "Full Neurosynth term decode is intentionally disabled."
        )
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        type=Path,
        help="NIfTI .nii/.nii.gz activation map(s) or directories containing them.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/marketing_nifti_decoder"),
        help="Directory for TSV outputs and resolved_features.json.",
    )
    parser.add_argument(
        "--nimare-data-dir",
        type=Path,
        default=Path("cache/nimare"),
        help="Directory where NiMARE stores Neurosynth data.",
    )
    parser.add_argument(
        "--decoder-cache",
        type=Path,
        default=Path("cache/nimare/marketing_v1_decoder.pkl.gz"),
        help="Cached marketing-only NiMARE decoder.",
    )
    parser.add_argument(
        "--frequency-threshold",
        type=float,
        default=DEFAULT_FREQUENCY_THRESHOLD,
        help="NiMARE feature membership threshold.",
    )
    parser.add_argument(
        "--max-resolved-features",
        type=int,
        default=MAX_RESOLVED_FEATURES,
        help=f"Hard maximum resolved features. Cannot exceed {MAX_RESOLVED_FEATURES}.",
    )
    parser.add_argument(
        "--n-cores",
        type=int,
        default=1,
        help="CPU cores for one-time decoder fitting. Must be >= 1.",
    )
    parser.add_argument(
        "--no-fit-if-missing",
        action="store_true",
        help="Require an existing compatible decoder cache; do not fit a new decoder.",
    )
    parser.add_argument(
        "--overwrite-cache",
        action="store_true",
        help="Overwrite an existing decoder cache and metadata.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Reduce logging.",
    )
    return parser.parse_args()


def main() -> None:
    """CLI entry point."""

    args = parse_args()
    configure_logging(verbose=not args.quiet)

    if args.max_resolved_features > MAX_RESOLVED_FEATURES:
        raise ValueError(
            f"--max-resolved-features cannot exceed {MAX_RESOLVED_FEATURES}."
        )
    if args.n_cores <= 0:
        raise ValueError("--n-cores must be >= 1. n_cores=-1 is disabled.")

    input_paths = collect_nifti_inputs(args.inputs)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.nimare_data_dir.mkdir(parents=True, exist_ok=True)
    args.decoder_cache.parent.mkdir(parents=True, exist_ok=True)

    studyset = load_neurosynth_studyset(args.nimare_data_dir)
    annotation_features = get_annotation_features(studyset)
    resolver = FeatureResolver(MARKETING_V1, max_features=args.max_resolved_features)
    resolved = resolver.resolve(annotation_features)
    save_resolved_features(
        resolved=resolved,
        annotation_features=annotation_features,
        output_path=args.output_dir / "resolved_features.json",
    )

    decoder = load_or_fit_decoder(
        studyset=studyset,
        features=resolved.unique_features,
        decoder_cache=args.decoder_cache,
        frequency_threshold=args.frequency_threshold,
        n_cores=args.n_cores,
        fit_if_missing=not args.no_fit_if_missing,
        overwrite_cache=args.overwrite_cache,
    )

    all_feature_scores: list[pd.DataFrame] = []
    for path in input_paths:
        LOGGER.info("Decoding NIfTI map: %s", path)
        img = validate_nifti_map(path)
        all_feature_scores.append(
            score_feature_correlations(
                map_path=path,
                img=img,
                decoder=decoder,
                resolved=resolved,
            )
        )

    feature_scores = pd.concat(all_feature_scores, ignore_index=True)
    group_indices = aggregate_group_indices(feature_scores)
    write_tables(args.output_dir, feature_scores, group_indices)

    print(group_indices.to_string(index=False))
    print(f"\nSaved UTF-8 TSV: {args.output_dir / 'marketing_indices.tsv'}")
    print(f"Saved UTF-8 TSV: {args.output_dir / 'marketing_feature_scores.tsv'}")
    print(f"Saved UTF-8 JSON: {args.output_dir / 'resolved_features.json'}")


if __name__ == "__main__":
    main()
