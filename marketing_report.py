# -*- coding: utf-8 -*-
"""Generate a self-contained HTML report for TRIBE surface decoder outputs."""

from __future__ import annotations

import argparse
import base64
import html
import json
import logging
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
    "attention_salience",
    "reward_value",
    "memory_encoding",
    "emotion_affect",
    "social_self",
    "aversion_risk",
    "language_narrative",
    "action_embodiment",
]


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
    frame["_order"] = frame["group"].map(order).fillna(10_000)
    return frame.sort_values(["_order", "group"]).drop(columns=["_order"])


def top_groups_text(score_rows: pd.DataFrame, top_n: int) -> str:
    """Format top marketing groups for one timepoint."""

    if score_rows.empty:
        return ""
    top_rows = score_rows.sort_values("score_0_100", ascending=False).head(top_n)
    return "<br>".join(
        f"{escape(row.group)}: <b>{fmt_float(row.score_0_100)}</b>"
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
        str(row.group): row
        for row in score_rows.itertuples(index=False)
    }
    cells: list[str] = []
    for group in GROUP_ORDER:
        row = by_group.get(group)
        if row is None:
            cells.append("<td></td>")
        else:
            cells.append(f"<td>{fmt_float(row.score_0_100)}</td>")
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
    top_terms: int,
    top_groups: int,
) -> str:
    """Build the per-segment interpretation table."""

    rows: list[str] = []
    for index, surface in enumerate(predictions):
        LOGGER.info("Rendering segment %d/%d", index + 1, predictions.shape[0])
        image = png_data_uri(render_surface_png(surface, f"segment {index}"))
        metadata = segment_metadata(segments, index)
        score_rows = group_scores_for_time(scores, SEGMENT_MAP_ID, index)
        rows.append(
            "<tr>"
            f"<td>{index}</td>"
            f"<td>{escape(metadata.get('start', ''))}</td>"
            f"<td>{escape(metadata.get('duration', ''))}</td>"
            f"<td><img class=\"brain\" src=\"{image}\" alt=\"segment {index} brain map\"></td>"
            f"<td>{top_groups_text(score_rows, top_groups)}</td>"
            f"<td>{top_terms_text(terms, SEGMENT_MAP_ID, index, top_terms)}</td>"
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
            f"<td>{top_groups_text(score_rows, top_groups)}</td>"
            f"<td>{top_terms_text(terms, map_id, 'aggregate', top_terms)}</td>"
            f"{scores_cells(score_rows)}"
            "</tr>"
        )
    return "\n".join(rows)


def table_header(include_time: bool) -> str:
    """Build a common table header."""

    prefix = ""
    if include_time:
        prefix = "<th>segment</th><th>start</th><th>duration</th>"
    else:
        prefix = "<th>summary</th>"
    group_headers = "".join(f"<th>{escape(group)}</th>" for group in GROUP_ORDER)
    return (
        "<tr>"
        f"{prefix}"
        "<th>brain map</th>"
        "<th>top groups</th>"
        "<th>top terms</th>"
        f"{group_headers}"
        "</tr>"
    )


def build_html(
    title: str,
    tribe_dir: Path,
    surface_dir: Path,
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

    segment_rows = build_segment_rows(
        predictions=predictions,
        scores=scores,
        terms=terms,
        segments=segments,
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
    td:nth-child(n+7) {{
      text-align: right;
      white-space: nowrap;
    }}
    .brain {{
      width: 260px;
      max-width: 260px;
      height: auto;
      display: block;
    }}
    .small {{ font-size: 11px; color: #57606a; }}
  </style>
</head>
<body>
  <h1>{safe_title}</h1>
  <div class="meta">
    <div><b>TRIBE output:</b> {escape(tribe_dir)}</div>
    <div><b>Decoder output:</b> {escape(surface_dir)}</div>
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
    <thead>{table_header(include_time=True)}</thead>
    <tbody>{segment_rows}</tbody>
  </table>
</body>
</html>
"""


def generate_report(
    tribe_dir: Path,
    surface_dir: Path,
    output_html: Path,
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
        title=args.title,
        top_terms=args.top_terms,
        top_groups=args.top_groups,
    )
    print(f"Saved HTML report: {output}")


if __name__ == "__main__":
    main()
