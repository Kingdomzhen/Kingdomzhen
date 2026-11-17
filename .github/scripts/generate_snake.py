#!/usr/bin/env python3
"""Generate GitHub contribution-calendar SVGs with a continuous growing snake."""

import hashlib
import random
import re
from datetime import date, timedelta
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

USERNAME = "Kingdomzhen"
OUTPUT_DIR = Path("snake")
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
FRAMES = WEEKS * DAYS_PER_WEEK
# A hand-played snake mostly heads for the next pellet but takes wrong turns
# now and then, and keeps gliding straight rather than twitching every cell.
FOOD_BIAS = 0.72
STRAIGHT_BIAS = 0.55
# Chance per step that the snake loses interest in its current pellet and picks
# another of the nearest three.
TARGET_SWITCH = 0.12
# When heading for a pellet, how often it keeps the current heading instead of
# turning. A player holds an arrow key and runs a few cells before turning; a
# 50/50 tie-break here produced a twitchy, nervous-looking wiggle.
CONTINUE_BIAS = 0.7
NEIGHBOUR_STEPS = ((1, 0), (-1, 0), (0, 1), (0, -1))


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


def contribution_seed(grid):
    """Deterministic seed so the same contribution data always animates the same."""
    payload = ";".join(
        f"{x},{y},{grid[(x, y)][0]}"
        for x in range(WEEKS)
        for y in range(DAYS_PER_WEEK)
    )
    return int(hashlib.sha256(payload.encode("ascii")).hexdigest()[:16], 16)


def nearest_tour_cost(position, pellets):
    """Steps a greedy nearest-pellet tour would need from ``position``."""
    cost = 0
    current = position
    remaining = sorted(pellets)
    while remaining:
        best = min(
            remaining,
            key=lambda cell: (abs(cell[0] - current[0]) + abs(cell[1] - current[1]), cell),
        )
        cost += abs(best[0] - current[0]) + abs(best[1] - current[1])
        remaining.remove(best)
        current = best
    return cost


def choose_step(position, previous, target, direction, rng, rush=False):
    """Pick the next cell the way a person with the arrow keys would."""
    options = [
        (position[0] + dx, position[1] + dy)
        for dx, dy in NEIGHBOUR_STEPS
        if 0 <= position[0] + dx < WEEKS and 0 <= position[1] + dy < DAYS_PER_WEEK
    ]
    if previous is None:
        forward = options
    else:
        forward = [cell for cell in options if cell != previous]
    if not forward:
        return previous  # cornered into its own tail: the only way off is back
    if target is not None and (rush or rng.random() < FOOD_BIAS):
        distances = [abs(cell[0] - target[0]) + abs(cell[1] - target[1]) for cell in forward]
        closest = min(distances)
        if rush:
            # Straight at the pellet, no wobble: this branch only runs when the
            # clock is about to run out with pellets still on the board.
            return min(
                (cell for cell, d in zip(forward, distances) if d == closest),
                key=lambda cell: cell,
            )
        closest_cells = [cell for cell, d in zip(forward, distances) if d == closest]
        if direction in closest_cells and rng.random() < CONTINUE_BIAS:
            return direction
        return rng.choice(closest_cells)
    straight = (position[0] + direction[0], position[1] + direction[1])
    if not rush and straight in forward and rng.random() < STRAIGHT_BIAS:
        return straight
    return rng.choice(forward)


def snake_walk(grid, rng, frames=FRAMES):
    """Wander the calendar the way a player chases pellets.

    While pellets are left the snake heads for one of the three nearest, so it
    still clears the board without ever repeating the same tidy sweep. Once the
    board is empty it picks random spots across the whole calendar and keeps
    gliding instead of stopping. Every step is one neighbouring cell, so the
    rendered body always stays connected. Returns the frame-by-frame route and
    the frame at which each pellet was first eaten; later passes over a cleared
    cell are just travel, not a second meal.
    """
    pellets = {cell for cell in grid if grid[cell][0] > 0}
    position = (0, 0)
    route = [position]
    eaten_at = {}
    if position in pellets:
        eaten_at[position] = 0
        pellets.discard(position)

    previous = None
    goal = None
    while len(route) < frames:
        direction = (1, 0) if previous is None else (
            position[0] - previous[0],
            position[1] - previous[1],
        )
        rush = False
        if pellets:
            # A player locks onto one pellet and only occasionally changes their
            # mind. Re-picking a target every single step made the head dither
            # between two equidistant pellets and burn half the run, so the
            # choice is sticky: one of the three nearest, kept until it is eaten
            # or the attention wanders. Ties break by coordinates, not by set
            # iteration order, so the route stays identical everywhere.
            if goal not in pellets or rng.random() < TARGET_SWITCH:
                nearest = sorted(
                    pellets,
                    key=lambda cell: (
                        abs(cell[0] - position[0]) + abs(cell[1] - position[1]),
                        cell,
                    ),
                )[:3]
                goal = rng.choice(nearest)
            # If the run is about to end with pellets still on the board, and a
            # straight tour could still sweep them up, stop wandering and go.
            # With a densely covered calendar a tour cannot fit anyway, so the
            # snake keeps roaming instead of turning into a beeline robot.
            tour = nearest_tour_cost(position, pellets)
            budget = frames - len(route)
            rush = budget < tour + 8 and tour <= budget
        elif goal is None or goal == position:
            goal = (rng.randrange(WEEKS), rng.randrange(DAYS_PER_WEEK))
        previous, position = position, choose_step(
            position, previous, goal, direction, rng, rush=rush
        )
        route.append(position)
        if position in pellets:
            eaten_at[position] = len(route) - 1
            pellets.discard(position)
    return route, eaten_at


def build_scene(grid):
    """Route plus per-frame length, shared by the light and dark renderings."""
    rng = random.Random(contribution_seed(grid))
    route, eaten_at = snake_walk(grid, rng)
    lengths = []
    length = 1
    for frame, cell in enumerate(route):
        if eaten_at.get(cell) == frame:
            length += 1
        lengths.append(length)
    return route, eaten_at, lengths, max(lengths)


def make_svg(grid, dark=False, scene=None):
    background = "#0d1117" if dark else "#ffffff"
    text_color = "#c9d1d9" if dark else "#57606a"
    levels = (
        ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]
        if dark
        else ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]
    )

    route, eaten_at, lengths, max_length = scene or build_scene(grid)

    frame_count = len(route)
    # Discrete animations without keyTimes give every value an equal slice of the
    # duration, which is exactly one calendar cell per frame. Spelling out 371
    # keyTimes for each of the four animations only bloats the SVG - it grows by
    # roughly 11 KB per snake segment, and the file is re-served on every profile
    # view, so keeping it lean matters as the year accumulates more pellets.
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">',
        f'<rect width="100%" height="100%" fill="{background}"/>',
        f'<text x="{LEFT}" y="24" fill="{text_color}" font-family="sans-serif" font-size="13">{escape(USERNAME)} · Contributions</text>',
    ]

    # Draw all 371 cells from the real contribution data, including empty cells.
    cleared_color = levels[0]
    for x in range(WEEKS):
        for y in range(DAYS_PER_WEEK):
            level = grid[(x, y)][1]
            px = LEFT + x * STEP
            py = TOP + y * STEP
            eat_frame = eaten_at.get((x, y))
            if eat_frame is None:
                svg.append(
                    f'<rect x="{px}" y="{py}" width="{CELL}" height="{CELL}" '
                    f'rx="2" fill="{levels[level]}"/>'
                )
                continue
            # Discrete fill animation: the cell keeps its colour until the head
            # reaches it, then stays empty for the rest of the run. One value per
            # frame keeps it in lock-step with the snake's own animation.
            fills = [levels[level]] * eat_frame + [cleared_color] * (frame_count - eat_frame)
            svg.append(
                f'<rect x="{px}" y="{py}" width="{CELL}" height="{CELL}" '
                f'rx="2" fill="{levels[level]}">'
                f'<animate attributeName="fill" values="{";".join(fills)}" '
                f'calcMode="discrete" dur="{DURATION}" repeatCount="indefinite"/>'
                "</rect>"
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
            # x/y are seeded with frame 0 so a renderer that drops the animation
            # still shows the snake where it starts instead of stacked at the origin.
            f'<rect x="{xs[0]}" y="{ys[0]}" width="{CELL}" height="{CELL}" rx="3" '
            f'fill="{color}" stroke="{background}" stroke-width="1">'
            f'<animate attributeName="x" values="{";".join(xs)}" '
            f'calcMode="discrete" dur="{DURATION}" repeatCount="indefinite"/>'
            f'<animate attributeName="y" values="{";".join(ys)}" '
            f'calcMode="discrete" dur="{DURATION}" repeatCount="indefinite"/>'
            f'<animate attributeName="opacity" values="{";".join(opacity)}" '
            f'calcMode="discrete" dur="{DURATION}" repeatCount="indefinite"/>'
            "</rect>"
        )

    svg.append("</svg>")
    return "\n".join(svg)


def main():
    contributions = fetch_contributions()
    grid = calendar_grid(contributions)
    pellets = sum(1 for cell in grid if grid[cell][0] > 0)
    total = sum(grid[cell][0] for cell in grid)
    scene = build_scene(grid)
    _, eaten_at, _, max_length = scene
    # The snake starts with one segment and gains one per pellet it reaches.
    print(
        f"{pellets} pellets, {total} contributions, "
        f"{len(eaten_at)} eaten, snake length {max_length}"
    )
    if pellets == 0:
        print("warning: no contribution counts found, the snake cannot grow")
    elif len(eaten_at) < pellets:
        print(f"warning: {pellets - len(eaten_at)} pellets were never reached")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "github-contribution-grid-snake.svg").write_text(
        make_svg(grid, scene=scene), encoding="utf-8"
    )
    (OUTPUT_DIR / "github-contribution-grid-snake-dark.svg").write_text(
        make_svg(grid, dark=True, scene=scene), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
