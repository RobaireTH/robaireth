import argparse
import calendar
import json
import math
import re
import subprocess
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path


def graphql(query):
    result = subprocess.run(
        ["gh", "api", "graphql", "--input", "-"],
        input=json.dumps({"query": query}), capture_output=True, text=True, check=True,
    )
    response = json.loads(result.stdout)
    if response.get("errors"):
        raise RuntimeError("Incomplete GitHub contribution response")
    return response["data"]


def dates_between(start, end):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def rolling_start(today):
    day = min(today.day, calendar.monthrange(today.year - 1, today.month)[1])
    return today.replace(year=today.year - 1, day=day) + timedelta(days=1)


def summarize(days, today, created):
    expected = set(dates_between(created, today))
    if not expected.issubset(days):
        raise ValueError("Incomplete history; keeping existing graphics")
    if any(not isinstance(days[d], int) or days[d] < 0 for d in expected):
        raise ValueError("Contribution counts must be nonnegative integers")
    best_start = best_end = run_start = None
    longest = run = 0
    for day in sorted(expected):
        if days[day] > 0:
            if run == 0:
                run_start = day
            run += 1
            if run > longest:
                longest, best_start, best_end = run, run_start, day
        else:
            run, run_start = 0, None
    current_end = today if days[today] else today - timedelta(days=1)
    current_start = None
    current = 0
    day = current_end
    while day >= created and days.get(day, 0) > 0:
        current += 1
        current_start = day
        day -= timedelta(days=1)
    start = max(rolling_start(today), created)
    return {
        "username": "robaireth",
        "window": {"start": start.isoformat(), "end": today.isoformat(),
                   "contributions": sum(days[d] for d in dates_between(start, today))},
        "current": {"days": current,
                    "start": current_start.isoformat() if current_start else None,
                    "end": current_end.isoformat() if current else None},
        "longest": {"days": longest,
                    "start": best_start.isoformat() if best_start else None,
                    "end": best_end.isoformat() if best_end else None},
        "progress": current / longest if longest else 0,
    }


def fetch_stats(username, now):
    if not re.fullmatch(r"[A-Za-z0-9-]+", username):
        raise ValueError("Invalid GitHub username")
    user = graphql(f'query {{ user(login: "{username}") {{ createdAt }} }}')["user"]
    created = date.fromisoformat(user["createdAt"][:10])
    today = now.date()
    fields = []
    for year in range(created.year, today.year + 1):
        start, end = max(date(year, 1, 1), created), min(date(year, 12, 31), today)
        fields.append(
            f'y{year}: contributionsCollection(from: "{start}T00:00:00Z", '
            f'to: "{end}T23:59:59Z") {{ contributionCalendar {{ weeks {{ '
            "contributionDays { date contributionCount } } } }"
        )
    history = graphql(f'query {{ user(login: "{username}") {{ {" ".join(fields)} }} }}')["user"]
    days = {}
    for key, collection in history.items():
        year = int(key[1:])
        lower, upper = max(date(year, 1, 1), created), min(date(year, 12, 31), today)
        for week in collection["contributionCalendar"]["weeks"]:
            for entry in week["contributionDays"]:
                day = date.fromisoformat(entry["date"])
                if lower <= day <= upper:
                    previous = days.get(day)
                    if previous is not None and previous != entry["contributionCount"]:
                        raise ValueError("Overlapping calendar dates disagree")
                    days[day] = entry["contributionCount"]
    stats = summarize(days, today, created)
    stats["username"] = username
    stats["updated_at"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    return stats


def short_date(value):
    day = date.fromisoformat(value)
    return f"{day.day} {day:%b %Y}"


def date_range(item):
    return f'{short_date(item["start"])} – {short_date(item["end"])}' if item["start"] else "No active streak"


def render(stats, theme):
    bg, ink, muted, border, accent = (
        ("#0d1117", "#e6edf3", "#9199a4", "#30363d", "#ed9ca9") if theme == "dark"
        else ("#ffffff", "#1f2328", "#656d76", "#d1d9e0", "#b03e56")
    )
    width, height = 720, 250
    current, longest, progress = stats["current"], stats["longest"], stats["progress"]
    percentage = round(progress * 100)
    title = (
        f'{stats["window"]["contributions"]:,} contributions, {date_range(stats["window"])}. '
        f'Current streak: {current["days"]} days, {date_range(current)}. '
        f'Longest streak: {longest["days"]} days, {date_range(longest)}. '
        f'Ring: {percentage}% of longest streak.'
    )
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        f'<title id="title">{escape(title)}</title>',
        '<desc id="desc">Consecutive contribution days from the full GitHub history. '
        'The ring compares the current streak with the personal record. A zero-contribution '
        'current day does not break a streak until the day ends. Dates use UTC.</desc>',
        f'<rect width="{width}" height="{height}" fill="{bg}"/>',
    ]

    def text(x, y, value, size=12, color=muted, weight=400):
        parts.append(
            f'<text x="{x}" y="{y}" text-anchor="middle" fill="{color}" '
            f'font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" '
            f'font-size="{size}" font-weight="{weight}">{escape(str(value))}</text>'
        )

    cx, cy, radius = 360, 76, 43
    circumference = 2 * math.pi * radius
    parts.append(f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="{border}" stroke-width="3"/>')
    if progress > 0:
        parts.append(
            f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="{accent}" '
            f'stroke-width="3" stroke-linecap="round" '
            f'stroke-dasharray="{progress * circumference:.3f} {circumference:.3f}" '
            f'transform="rotate(-90 {cx} {cy})"/>'
        )
    text(cx, cy + 6, current["days"], 30, accent, 600)
    text(cx, cy + 23, "days", 10)
    label = "Personal best" if current["days"] and current["days"] == longest["days"] else f"{percentage}% of personal best"
    parts.append(f'<path d="M240 39V190M480 39V190" stroke="{border}"/>')
    text(120, 86, f'{stats["window"]["contributions"]:,}', 34, ink, 600)
    text(600, 86, longest["days"], 34, ink, 600)
    text(600, 105, "days", 10)
    for x, label_text in [(120, "Contributions · past 12 months"), (360, "Current streak"), (600, "Longest streak · all time")]:
        text(x, 140, label_text, 12, ink)
    for x, value in [(120, stats["window"]), (360, current), (600, longest)]:
        text(x, 163, date_range(value), 11)
    text(360, 185, label, 11, accent)
    updated_y = 228
    updated = datetime.fromisoformat(stats["updated_at"].replace("Z", "+00:00"))
    text(width / 2, updated_y, f"Updated {updated.day} {updated:%b %Y, %H:%M} UTC · refreshes hourly", 10)
    parts.append("</svg>")
    return "".join(parts)


def write_assets(stats, output):
    output.mkdir(parents=True, exist_ok=True)
    for theme in ("dark", "light"):
        for mobile in (False, True):
            suffix = f"mobile-{theme}" if mobile else theme
            (output / f"streak-{suffix}.svg").write_text(render(stats, theme))
    (output / "stats.json").write_text(json.dumps(stats, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default="robaireth")
    parser.add_argument("--output", type=Path, default=Path("assets"))
    args = parser.parse_args()
    stats = fetch_stats(args.username, datetime.now(timezone.utc).replace(microsecond=0))
    write_assets(stats, args.output)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
