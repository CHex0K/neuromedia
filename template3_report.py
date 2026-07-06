# -*- coding: utf-8 -*-
"""Build a Template_3_with_frames.xlsx report from TRIBE pipeline artifacts.

Instead of reconstructing the 6-sheet "Neurosemantic Correlation Dashboard"
layout by hand, this fills the shipped ``Template_3_with_frames.xlsx`` as a
skeleton (preserving sheets, styles, README and 5_WEIGHTS_REF) and writes one
data row per TRIBE segment.

Data sources (all produced by the existing pipeline):
  - decoded_terms.csv    : per-segment (time_index) x per-term (feature) Pearson r
  - marketing_scores.csv : per-segment per-group mean_r
  - tribe_segments.tsv   : segment timing (index/offset/duration)
  - words TSV (optional) : transcript words for scene_description alignment
  - frame_png_provider   : optional callable(offset, duration) -> PNG bytes | None

Manual creative markup (2_FRAME_MARKUP flags and markup-dependent windows) is left
as an empty skeleton for a human to fill.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

LOGGER = logging.getLogger("template3_report")

DATA_START_ROW = 4  # sheets 1/2/3 have headers on rows 2-3 and data from row 4

# decoder group (as stored in decoded_terms/marketing_scores) -> template index code
GROUP_TO_INDEX = {
    "attention": "ATT",
    "affect_arousal": "AFF-A",
    "affect_valence": "AFF-V",
    "memory": "MEM",
    "reward": "REW",
    "social": "SOC",
    "cog_clarity": "COG-CL",
    "cog_load": "COG-LD",
}
# canonical index order used by sheets 3/4
INDEX_ORDER = ["ATT", "AFF-A", "AFF-V", "MEM", "REW", "SOC", "COG-CL", "COG-LD"]

FramePngProvider = Callable[[Optional[float], Optional[float]], Optional[bytes]]


def _canon(code: object) -> str:
    """Canonicalize an index code: 'AFF_A', 'AFF-A\\nИнт' -> 'AFFA'."""

    text = str(code or "").split("\n", 1)[0]
    return "".join(ch for ch in text.upper() if ch.isalnum())


def _norm_term(term: object) -> str:
    """Normalize a term/feature for matching: 'visual attention' -> 'visual_attention'."""

    return str(term or "").strip().lower().replace(" ", "_").replace("-", "_")


def _find_column(frame: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    normalized = {str(c).strip().lower(): c for c in frame.columns}
    for cand in candidates:
        if cand in normalized:
            return normalized[cand]
    return None


def _safe_zscore(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    std = values.std(ddof=0)
    if not np.isfinite(std) or std == 0:
        return np.zeros_like(values)
    return (values - values.mean()) / std


def _read_header_terms(ws) -> list[tuple[int, str]]:
    """Return (column_index, normalized_term) for the term columns of sheet 1."""

    terms: list[tuple[int, str]] = []
    for col in range(5, ws.max_column + 1):
        name = ws.cell(3, col).value
        if name:
            terms.append((col, _norm_term(name)))
    return terms


def _index_columns(ws, header_row: int, first_col: int) -> dict[str, int]:
    """Map canonical index code -> column index for an index header row."""

    mapping: dict[str, int] = {}
    for col in range(first_col, ws.max_column + 1):
        canon = _canon(ws.cell(header_row, col).value)
        for code in INDEX_ORDER:
            if canon == _canon(code):
                mapping[code] = col
    return mapping


def _z_columns(ws, header_row: int) -> dict[str, int]:
    """Map canonical index code -> column index for z_<INDEX> columns."""

    mapping: dict[str, int] = {}
    for col in range(1, ws.max_column + 1):
        val = ws.cell(header_row, col).value
        if isinstance(val, str) and val.strip().lower().startswith("z_"):
            mapping[_canon(val[2:])] = col
    return mapping


def _clear_data_rows(ws, start_row: int, end_row: int, first_col: int = 1) -> None:
    for row in range(start_row, end_row + 1):
        for col in range(first_col, ws.max_column + 1):
            ws.cell(row, col).value = None
    # drop skeleton example images
    if hasattr(ws, "_images"):
        ws._images = []


def _segment_frames(
    decoded_terms_csv: Path,
    marketing_scores_csv: Path,
    segments_tsv: Optional[Path],
    words_tsv: Optional[Path],
):
    """Assemble per-segment structures from the pipeline CSVs."""

    terms = pd.read_csv(decoded_terms_csv)
    scores = pd.read_csv(marketing_scores_csv)

    time_indices = sorted(pd.unique(terms["time_index"]))

    # per (time_index, normalized feature) -> r  (dedupe feature repeats across groups)
    terms = terms.copy()
    terms["_feat"] = terms["feature"].map(_norm_term)
    r_by_ti_feat = (
        terms.drop_duplicates(subset=["time_index", "_feat"])
        .set_index(["time_index", "_feat"])["r"]
        .to_dict()
    )

    # per (time_index, index code) -> mean_r
    scores = scores.copy()
    scores["_idx"] = scores["group"].map(GROUP_TO_INDEX)
    score_by_ti_idx = (
        scores.dropna(subset=["_idx"]).set_index(["time_index", "_idx"])["mean_r"].to_dict()
    )

    # segment timing
    offsets: dict[int, Optional[float]] = {}
    durations: dict[int, Optional[float]] = {}
    if segments_tsv and Path(segments_tsv).is_file():
        seg = pd.read_csv(segments_tsv, sep="\t")
        off_col = _find_column(seg, ["offset", "start"])
        dur_col = _find_column(seg, ["duration"])
        idx_col = _find_column(seg, ["index"])
        for i, row in seg.iterrows():
            ti = int(row[idx_col]) if idx_col is not None and pd.notna(row[idx_col]) else i
            offsets[ti] = float(row[off_col]) if off_col and pd.notna(row[off_col]) else None
            durations[ti] = float(row[dur_col]) if dur_col and pd.notna(row[dur_col]) else None

    # transcript words for scene_description
    words = None
    if words_tsv and Path(words_tsv).is_file():
        wdf = pd.read_csv(words_tsv, sep="\t")
        ws_col = _find_column(wdf, ["start", "word_start", "begin"])
        wt_col = _find_column(wdf, ["text", "word", "token", "corrected", "corrected_text"])
        if ws_col and wt_col:
            words = wdf[[ws_col, wt_col]].rename(columns={ws_col: "start", wt_col: "text"})

    def scene_desc(offset: Optional[float], duration: Optional[float]) -> str:
        if words is None or offset is None:
            return ""
        end = offset + (duration or 0.0)
        sel = words[(words["start"] >= offset) & (words["start"] < max(end, offset + 0.001))]
        return " ".join(str(t) for t in sel["text"].tolist()).strip()

    rows = []
    for pos, ti in enumerate(time_indices):
        offset = offsets.get(ti)
        duration = durations.get(ti)
        rows.append(
            {
                "time_index": int(ti),
                "frame_id": f"F{pos + 1:02d}",
                "second": round(offset, 2) if offset is not None else pos + 1,
                "offset": offset,
                "duration": duration,
                "scene_description": scene_desc(offset, duration),
                "r": r_by_ti_feat,
                "scores": {code: score_by_ti_idx.get((int(ti), code)) for code in INDEX_ORDER},
            }
        )
    return rows


def build_template3_workbook(
    *,
    template_path: Path,
    decoded_terms_csv: Path,
    marketing_scores_csv: Path,
    output_xlsx: Path,
    segments_tsv: Optional[Path] = None,
    words_tsv: Optional[Path] = None,
    frame_png_provider: Optional[FramePngProvider] = None,
) -> Path:
    """Fill the shipped template skeleton with this video's data and save it."""

    import openpyxl

    wb = openpyxl.load_workbook(template_path)
    rows = _segment_frames(decoded_terms_csv, marketing_scores_csv, segments_tsv, words_tsv)
    n = len(rows)

    _fill_raw_correlations(wb["1_RAW_CORRELATIONS"], rows, frame_png_provider)
    _fill_frame_markup(wb["2_FRAME_MARKUP"], rows, frame_png_provider)
    index_matrix = _fill_index_scores(wb["3_INDEX_SCORES"], rows)
    _fill_window_aggregates(wb["4_WINDOW_AGGREGATES"], rows, index_matrix)

    output_xlsx = Path(output_xlsx)
    output_xlsx.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_xlsx)
    LOGGER.info("Wrote Template_3 workbook with %d segment rows: %s", n, output_xlsx)
    return output_xlsx


def _embed_frame(ws, row: int, png_bytes: Optional[bytes]) -> None:
    if not png_bytes:
        return
    try:
        from openpyxl.drawing.image import Image as XLImage

        image = XLImage(io.BytesIO(png_bytes))
        image.width, image.height = 140, 80
        ws.row_dimensions[row].height = 64
        ws.add_image(image, f"D{row}")
    except Exception as exc:  # pragma: no cover - PIL/openpyxl optional at runtime
        LOGGER.warning("Could not embed frame at row %d: %s", row, exc)


def _fill_raw_correlations(ws, rows, frame_png_provider) -> None:
    term_cols = _read_header_terms(ws)  # [(col, norm_term)]
    _clear_data_rows(ws, DATA_START_ROW, ws.max_row)
    for i, seg in enumerate(rows):
        r = DATA_START_ROW + i
        ws.cell(r, 1).value = seg["frame_id"]
        ws.cell(r, 2).value = seg["second"]
        ws.cell(r, 3).value = seg["scene_description"]
        for col, term in term_cols:
            val = seg["r"].get((seg["time_index"], term))
            ws.cell(r, col).value = float(val) if val is not None else None
        if frame_png_provider is not None:
            _embed_frame(ws, r, frame_png_provider(seg["offset"], seg["duration"]))


def _fill_frame_markup(ws, rows, frame_png_provider) -> None:
    _clear_data_rows(ws, DATA_START_ROW, ws.max_row)
    for i, seg in enumerate(rows):
        r = DATA_START_ROW + i
        ws.cell(r, 1).value = seg["frame_id"]
        ws.cell(r, 2).value = seg["second"]
        ws.cell(r, 3).value = seg["scene_description"]
        for col in range(5, 11):  # HOOK/BRAND/PRODUCT/OFFER/CTA/LOGO -> skeleton 0
            ws.cell(r, col).value = 0
        if frame_png_provider is not None:
            _embed_frame(ws, r, frame_png_provider(seg["offset"], seg["duration"]))


def _fill_index_scores(ws, rows) -> dict[str, np.ndarray]:
    idx_cols = _index_columns(ws, header_row=3, first_col=4)
    z_cols = _z_columns(ws, header_row=3)
    _clear_data_rows(ws, DATA_START_ROW, ws.max_row)

    matrix = {code: np.array([_num(seg["scores"].get(code)) for seg in rows], dtype=np.float64)
              for code in INDEX_ORDER}
    z_matrix = {code: _safe_zscore(matrix[code]) for code in INDEX_ORDER}

    for i, seg in enumerate(rows):
        r = DATA_START_ROW + i
        ws.cell(r, 1).value = seg["frame_id"]
        ws.cell(r, 2).value = seg["second"]
        for code in INDEX_ORDER:
            if code in idx_cols:
                v = seg["scores"].get(code)
                ws.cell(r, idx_cols[code]).value = float(v) if v is not None else None
            if code in z_cols:
                ws.cell(r, z_cols[code]).value = float(z_matrix[code][i])
    return matrix


def _num(value) -> float:
    try:
        return float(value) if value is not None else np.nan
    except (TypeError, ValueError):
        return np.nan


def _fill_window_aggregates(ws, rows, index_matrix) -> None:
    idx_cols = _index_columns(ws, header_row=3, first_col=3)
    offsets = np.array([_num(seg["offset"]) for seg in rows], dtype=np.float64)

    def window_mean(lo: float, hi: float) -> dict[str, float]:
        mask = (offsets >= lo) & (offsets < hi)
        if not mask.any():
            return {}
        return {code: float(np.nanmean(index_matrix[code][mask])) for code in INDEX_ORDER}

    full_mean = {code: float(np.nanmean(index_matrix[code])) for code in INDEX_ORDER}
    peak = {code: float(np.nanmax(index_matrix[code])) for code in INDEX_ORDER}
    seg_stats = {
        code: (float(np.nanmean(index_matrix[code])), float(np.nanstd(index_matrix[code])))
        for code in INDEX_ORDER
    }

    def zof(values: dict[str, float]) -> dict[str, float]:
        out = {}
        for code in INDEX_ORDER:
            mean, std = seg_stats[code]
            if code in values and std and np.isfinite(std):
                out[code] = (values[code] - mean) / std
        return out

    # row index in sheet 4 -> values dict (computed windows only; markup windows blank)
    computed = {
        4: window_mean(0.0, 3.0),
        5: window_mean(0.0, 5.0),
        6: full_mean,
        7: peak,
        8: window_mean(18.0, 20.0),
        14: zof(window_mean(0.0, 3.0)),
        15: zof(full_mean),
        18: zof(peak),
    }
    for row, values in computed.items():
        for code, col in idx_cols.items():
            if code in values and np.isfinite(values[code]):
                ws.cell(row, col).value = float(values[code])
