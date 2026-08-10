"""scripts/build/chart_svg_builder.py — XSS-safe markdown table OR inline SVG charts.

Per claude-blog XSS-safe SVG pattern:
  - NO inline <script>
  - NO event attributes (onclick, onmouseover, ...)
  - NO external URLs / xlink:href
  - CSS-only hover (no JS)
  - Escaped text via html.escape

Generates either:
  - Markdown table (default; safer + universally supported)
  - Inline SVG (when chart_type requires visual: bar / pie / line)
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


ChartType = Literal["table", "bar", "pie", "line", "comparison"]


@dataclass
class ChartData:
    title: str
    columns: list[str]
    rows: list[list[str]]


def render_markdown_table(data: ChartData) -> str:
    """Render as GFM markdown table. Always safe."""
    if not data.columns or not data.rows:
        return ""
    lines = []
    if data.title:
        lines.append(f"**{data.title}**\n")
    # Header
    lines.append("| " + " | ".join(html.escape(c) for c in data.columns) + " |")
    lines.append("|" + "|".join("---" for _ in data.columns) + "|")
    # Rows
    for row in data.rows:
        cells = [html.escape(str(c)) for c in row]
        # Pad to column count
        while len(cells) < len(data.columns):
            cells.append("")
        lines.append("| " + " | ".join(cells[:len(data.columns)]) + " |")
    return "\n".join(lines)


def render_bar_svg(data: ChartData, *, width: int = 600, height: int = 400) -> str:
    """Render simple bar chart as inline SVG. Numeric values in first column after labels."""
    if not data.rows:
        return ""

    # Assume: row[0] = label, row[1] = numeric value
    try:
        values = []
        labels = []
        for r in data.rows:
            if len(r) < 2:
                continue
            v = str(r[1]).strip().rstrip("%").rstrip("$")
            try:
                values.append(float(v))
                labels.append(str(r[0]))
            except ValueError:
                continue
    except Exception:
        return render_markdown_table(data)

    if not values:
        return render_markdown_table(data)

    max_val = max(values) or 1
    bar_width = (width - 100) / len(values)

    parts = [
        f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg" '
        'role="img" aria-label="Chart">',
        '<style>',
        '.bar { fill: #4a90e2; }',
        '.bar:hover { fill: #2e6da4; }',
        '.label { font: 12px sans-serif; }',
        '.title { font: bold 14px sans-serif; }',
        '</style>',
    ]
    parts.append(f'<text x="{width//2}" y="20" class="title" text-anchor="middle">{html.escape(data.title)}</text>')

    for i, (label, val) in enumerate(zip(labels, values)):
        bar_height = (val / max_val) * (height - 100)
        x = 50 + i * bar_width
        y = height - 50 - bar_height
        parts.append(
            f'<rect class="bar" x="{x:.1f}" y="{y:.1f}" '
            f'width="{bar_width-10:.1f}" height="{bar_height:.1f}" />'
        )
        parts.append(
            f'<text x="{x + (bar_width-10)/2:.1f}" y="{height-30}" '
            f'class="label" text-anchor="middle">{html.escape(label)}</text>'
        )
        parts.append(
            f'<text x="{x + (bar_width-10)/2:.1f}" y="{y - 5:.1f}" '
            f'class="label" text-anchor="middle">{val:.1f}</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def render(data: ChartData, chart_type: ChartType = "table",
           width: int = 600, height: int = 400) -> str:
    """Dispatch to correct renderer. XSS-safe markdown table for all default cases."""
    if chart_type == "table" or chart_type == "comparison":
        return render_markdown_table(data)
    if chart_type == "bar":
        return render_bar_svg(data, width=width, height=height)
    # pie / line: fall back to table for now (more renderers can be added)
    return render_markdown_table(data)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, help="JSON file with {title, columns, rows}")
    ap.add_argument("--type", choices=["table", "bar", "pie", "line", "comparison"], default="table")
    ap.add_argument("--width", type=int, default=600)
    ap.add_argument("--height", type=int, default=400)
    args = ap.parse_args()

    if not args.input or not args.input.exists():
        print("Provide --input pointing to JSON {title, columns, rows}", file=sys.stderr)
        return 2

    obj = json.loads(args.input.read_text(encoding="utf-8"))
    data = ChartData(
        title=obj.get("title", ""),
        columns=obj.get("columns", []),
        rows=obj.get("rows", []),
    )
    print(render(data, chart_type=args.type, width=args.width, height=args.height))
    return 0


if __name__ == "__main__":
    sys.exit(main())
