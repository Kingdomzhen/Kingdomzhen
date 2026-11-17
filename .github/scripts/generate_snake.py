#!/usr/bin/env python3
"""Generate GitHub contribution-calendar SVGs with a continuous growing snake."""

import re
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


NO_CONTRIBUTION_RE = re.compile(r"no contributions?", re.IGNORECASE)
CONTRIBUTION_COUNT_RE = re.compile(r"(\d[\d,]*)\s+contributions?", re.IGNORECASE)


def to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_tooltip_count(text):
    """Turn "12 contributions on ..." / "No contributions on ..." into a number."""
    text = " ".join(text.split())
    if not text:
        return None
    if NO_CONTRIBUTION_RE.search(text):
        return 0
    match = CONTRIBUTION_COUNT_RE.search(text)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


class ContributionParser(HTMLParser):
    """Read contribution cells and their per-day counts.

    GitHub no longer puts ``data-count`` on the calendar cell; the cell only
    carries ``data-level``, while the exact number lives in a sibling
    ``<tool-tip for="<cell id>">2 contributions on November 8th.</tool-tip>``.
    Older pages still expose ``data-count``, so both shapes are accepted and
    ``data-level`` is the last-resort fallback (a lit cell means at least one).
    """

    def __init__(self):
        super().__init__()
        self.cells = {}  # cell id (or date) -> (day, level, count or None)
        self.tooltip_counts = {}  # cell id -> count parsed from its tooltip
        self._tooltip_id = None
        self._tooltip_chunks = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "td":
            self._read_cell(attributes)
        elif tag == "tool-tip":
            self._tooltip_id = attributes.get("for")
            self._tooltip_chunks = []

    def handle_data(self, data):
        if self._tooltip_id:
            self._tooltip_chunks.append(data)

    def handle_endtag(self, tag):
        if tag == "tool-tip" and self._tooltip_id:
            count = parse_tooltip_count("".join(self._tooltip_chunks))
            if count is not None:
                self.tooltip_counts[self._tooltip_id] = count
            self._tooltip_id = None
            self._tooltip_chunks = []

    def _read_cell(self, attributes):
        raw_date = attributes.get("data-date")
        if not raw_date:
            return
        try:
            day = date.fromisoformat(raw_date)
        except ValueError:
            return
        level = max(0, min(to_int(attributes.get("data-level")), 4))
        raw_count = attributes.get("data-count")
        count = None if raw_count is None else to_int(raw_count)
        self.cells[attributes.get("id") or raw_date] = (day, level, count)

    def days(self):
        """Resolve every cell to ``{date: (contributions, level)}``."""
        result = {}
        for cell_id, (day, level, count) in self.cells.items():
            if count is None:
                count = self.tooltip_counts.get(cell_id)
            if count is None:
                count = 1 if level > 0 else 0
            result[day] = (max(0, count), level)
        return result


def fetch_contributions():
    request = Request(
        f"https://github.com/users/{USERNAME}/contributions",
        headers={"User-Agent": "github-contribution-snake/1.0"},
    )
    with urlopen(request, timeout=30) as response:
        parser = ContributionParser()
        parser.feed(response.read().decode("utf-8", errors="replace"))

    if not parser.cells:
        raise RuntimeError("No contribution cells found in GitHub response")
    days = parser.days()
    if not days:
        raise RuntimeError("No contribution dates found in GitHub response")
    return days


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
    active_days = sum(1 for cell, (count, _) in contributions.items() if count > 0)
    total = sum(count for count, _ in contributions.values())
    # The snake starts with one segment and gains one per day with contributions.
    print(f"{active_days} active days, {total} contributions, snake length {active_days + 1}")
    if active_days == 0:
        print("warning: no contribution counts found, the snake cannot grow")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "github-contribution-grid-snake.svg").write_text(
        make_svg(grid), encoding="utf-8"
    )
    (OUTPUT_DIR / "github-contribution-grid-snake-dark.svg").write_text(
        make_svg(grid, dark=True), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
