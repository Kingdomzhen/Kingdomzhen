#!/usr/bin/env python3
import re
from datetime import date, timedelta
from pathlib import Path
from urllib.request import Request, urlopen

USERNAME = "Kingdomzhen"
OUTPUT_DIR = Path("dist")
CELL = 12
GAP = 3
STEP = CELL + GAP
LEFT = 20
TOP = 28
WEEKS = 53


def fetch_contributions():
    req = Request(
        f"https://github.com/users/{USERNAME}/contributions",
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urlopen(req, timeout=30) as response:
        html = response.read().decode("utf-8", errors="ignore")
    return html


def parse_contribution_cells(html):
    pattern = r'data-date="(\d{4}-\d{2}-\d{2})".*?data-level="(\d+)"'
    cells = {}
    for d, level in re.findall(pattern, html):
        day = date.fromisoformat(d)
        week_start = day - timedelta(days=(day.weekday() + 1) % 7)
        week_index = (day - week_start).days // 7
        cells[(week_index, day.weekday())] = int(level)
    return cells


def build_path(cells):
    path = []
    for x in range(WEEKS):
        ys = range(7) if x % 2 == 0 else range(6, -1, -1)
        for y in ys:
            if cells.get((x, y), 0) > 0:
                path.append((x, y))
    return path


def make_svg(cells):
    path = build_path(cells)
    frame_count = max(1, len(path))
    key_times = ";".join(
        f"{i / max(1, frame_count - 1):.6f}" for i in range(frame_count)
    )

    bg = "#0d1117"
    palette = ["#161b22", "#006d32", "#26a641", "#39d353", "#7ee787"]

    width = WEEKS * STEP + LEFT * 2
    height = 7 * STEP + TOP * 2
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="100%" height="100%" fill="{bg}"/>',
    ]

    for x in range(WEEKS):
        for y in range(7):
            px = LEFT + x * STEP
            py = TOP + y * STEP
            level = cells.get((x, y), 0)
            color = palette[min(level, 4)]
            svg.append(
                f'<rect x="{px}" y="{py}" width="{CELL}" height="{CELL}" rx="2" fill="{color}"/>'
            )

    # Build the snake route: the head moves through each non-empty cell in order,
    # and each body segment trails behind by one cell, which gives the look of
    # a growing snake that eats a square and gets longer.
    x_values = []
    y_values = []
    opacity_values = []
    for seg in range(max(1, len(path))):
        xs = []
        ys = []
        ops = []
        for frame in range(frame_count):
            if frame < seg:
                x, y = path[0]
                op = "0"
            else:
                idx = frame - seg
                x, y = path[min(max(idx, 0), len(path) - 1)]
                op = "1"
            xs.append(str(LEFT + x * STEP))
            ys.append(str(TOP + y * STEP))
            ops.append(op)
        x_values.append(";".join(xs))
        y_values.append(";".join(ys))
        opacity_values.append(";".join(ops))

    for seg in range(max(1, len(path))):
        svg.append(
            f'<rect width="{CELL}" height="{CELL}" rx="3" fill="#7ee787" opacity="0.9">'
            f'<animate attributeName="x" values="{x_values[seg]}" keyTimes="{key_times}" calcMode="linear" dur="12s" repeatCount="indefinite"/>'
            f'<animate attributeName="y" values="{y_values[seg]}" keyTimes="{key_times}" calcMode="linear" dur="12s" repeatCount="indefinite"/>'
            f'<animate attributeName="opacity" values="{opacity_values[seg]}" keyTimes="{key_times}" calcMode="discrete" dur="12s" repeatCount="indefinite"/>'
            f'</rect>'
        )

    svg.append("</svg>")
    return "\n".join(svg)


def main():
    html = fetch_contributions()
    cells = parse_contribution_cells(html)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    svg = make_svg(cells)
    (OUTPUT_DIR / "github-contribution-grid-snake.svg").write_text(svg, encoding="utf-8")
    (OUTPUT_DIR / "github-contribution-grid-snake-dark.svg").write_text(
        svg.replace("#0d1117", "#ffffff").replace("#161b22", "#dfe3e8").replace("#006d32", "#2a7d3b").replace("#26a641", "#4fbf67").replace("#39d353", "#7adc8d").replace("#7ee787", "#3c9d3f"),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
