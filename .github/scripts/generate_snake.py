#!/usr/bin/env python3
"""Generate GitHub contribution-calendar SVGs with a continuous growing snake."""

from datetime import date, timedelta
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

USERNAME = "Kingdomzhen"
OUTPUT_DIR = Path("dist")
WEEKS = 53
DAYS_PER_WEEK = 7
CELL = 11
GAP = 3
STEP = CELL + GAP
LEFT = 24
TOP = 42
WIDTH = LEFT * 2 + WEEKS * STEP - GAP
HEIGHT = TOP + DAYS_PER_WEEK * STEP - GAP + 24
DURATION = "28s"


class ContributionParser(HTMLParser):
    """Read contribution-cell attributes without relying on HTML attribute order."""

    def __init__(self):
        super().__init__()
        self.days = {}

    def handle_starttag(self, tag, attrs):
        if tag != "td":
            return
        attrs = dict(attrs)
        raw_date = attrs.get("data-date")
        if not raw_date:
            return
        try:
            day = date.fromisoformat(raw_date)
            count = int(attrs.get("data-count", "0"))
            level = int(attrs.get("data-level", "0"))
        except (TypeError, ValueError):
            return
        self.days[day] = (max(0, count), max(0, min(level, 4)))


def fetch_contributions():
    request = Request(
        f"https://github.com/users/{USERNAME}/contributions",
        headers={"User-Agent": "github-contribution-snake/1.0"},
    )
    with urlopen(request, timeout=30) as response:
        parser = ContributionParser()
        parser.feed(response.read().decode("utf-8", errors="replace"))

    if not parser.days:
        raise RuntimeError("No contribution cells found in GitHub response")
    return parser.days


def calendar_grid(contributions):
    """Map actual dates to the same Sunday-first week/weekday grid as GitHub."""
    last_day = max(contributions)
    last_sunday = last_day - timedelta(days=(last_day.weekday() + 1) % 7)
    first_sunday = last_sunday - timedelta(weeks=WEEKS - 1)

    grid = {}
    for day_offset in range(WEEKS * DAYS_PER_WEEK):
        day = first_sunday + timedelta(days=day_offset)
        x = day_offset // DAYS_PER_WEEK
        y = day_offset % DAYS_PER_WEEK
        grid[(x, y)] = contributions.get(day, (0, 0))
    return grid


def make_svg(grid, dark=False):
    background = "#0d1117" if dark else "#ffffff"
    text_color = "#c9d1d9" if dark else "#57606a"
    levels = (
        ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]
        if dark
        else ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]
    )

    # A continuous serpentine route visits every calendar square exactly once.
    route = []
    for x in range(WEEKS):
        rows = range(DAYS_PER_WEEK) if x % 2 == 0 else range(DAYS_PER_WEEK - 1, -1, -1)
        route.extend((x, y) for y in rows)

    # The snake moves one adjacent cell per frame. Only non-zero contribution
    # cells count as food; each one increases its length by one segment.
    food = [grid[cell][0] > 0 for cell in route]
    lengths = []
    length = 1
    for has_food in food:
        if has_food:
            length += 1
        lengths.append(length)
    max_length = max(lengths)

    frame_count = len(route)
    key_times = ";".join(f"{i / (frame_count - 1):.8f}" for i in range(frame_count))
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">',
        f'<rect width="100%" height="100%" fill="{background}"/>',
        f'<text x="{LEFT}" y="24" fill="{text_color}" font-family="sans-serif" font-size="13">{escape(USERNAME)} · Contributions</text>',
    ]

    # Draw all 371 cells from the real contribution data, including empty cells.
    for x in range(WEEKS):
        for y in range(DAYS_PER_WEEK):
            _, level = grid[(x, y)]
            px = LEFT + x * STEP
            py = TOP + y * STEP
            svg.append(
                f'<rect x="{px}" y="{py}" width="{CELL}" height="{CELL}" '
                f'rx="2" fill="{levels[level]}"/>'
            )

    # Each body element follows the head's historical trail. It appears only
    # after food has been eaten enough times to grow the snake to that length.
    head_color = "#2da44e" if not dark else "#7ee787"
    body_color = "#1a7f37" if not dark else "#39d353"
    for segment in range(max_length):
        xs = []
        ys = []
        opacity = []
        for frame in range(frame_count):
            trail_index = max(0, frame - segment)
            x, y = route[trail_index]
            xs.append(str(LEFT + x * STEP))
            ys.append(str(TOP + y * STEP))
            opacity.append("1" if segment < lengths[frame] else "0")

        color = head_color if segment == 0 else body_color
        svg.append(
            f'<rect width="{CELL}" height="{CELL}" rx="3" fill="{color}" '
            f'stroke="{background}" stroke-width="1">'
            f'<animate attributeName="x" values="{";".join(xs)}" keyTimes="{key_times}" '
            f'calcMode="discrete" dur="{DURATION}" repeatCount="indefinite"/>'
            f'<animate attributeName="y" values="{";".join(ys)}" keyTimes="{key_times}" '
            f'calcMode="discrete" dur="{DURATION}" repeatCount="indefinite"/>'
            f'<animate attributeName="opacity" values="{";".join(opacity)}" keyTimes="{key_times}" '
            f'calcMode="discrete" dur="{DURATION}" repeatCount="indefinite"/>'
            "</rect>"
        )

    svg.append("</svg>")
    return "\n".join(svg)


def main():
    contributions = fetch_contributions()
    grid = calendar_grid(contributions)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "github-contribution-grid-snake.svg").write_text(
        make_svg(grid), encoding="utf-8"
    )
    (OUTPUT_DIR / "github-contribution-grid-snake-dark.svg").write_text(
        make_svg(grid, dark=True), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
