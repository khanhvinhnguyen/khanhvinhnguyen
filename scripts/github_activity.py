#!/usr/bin/env python3
"""Build a dependency-free profile card from GitHub's public contribution calendar."""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
START_MARKER = "<!-- github-activity:start -->"
END_MARKER = "<!-- github-activity:end -->"
DAY = timedelta(days=1)
COLORS = ("#1b252d", "#29482f", "#48783b", "#7eae36", "#b8e600")


def date_range(start: date, end: date):
    while start <= end:
        yield start
        start += DAY


class CalendarParser(HTMLParser):
    """Read exact counts from tooltips, never infer counts from color levels."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cells = {}
        self.tips = {}
        self.tip_id = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "data-date" in attrs:
            day = date.fromisoformat(attrs["data-date"])
            if day in self.cells:
                raise ValueError(f"Duplicate calendar date: {day}")
            self.cells[day] = attrs
        if tag == "tool-tip":
            self.tip_id = attrs.get("for")
            if self.tip_id:
                self.tips[self.tip_id] = ""

    def handle_data(self, value):
        if self.tip_id:
            self.tips[self.tip_id] += value

    def handle_endtag(self, tag):
        if tag == "tool-tip":
            self.tip_id = None

    def counts(self):
        result = {}
        for day, attrs in self.cells.items():
            tooltip = " ".join(self.tips.get(attrs.get("id"), "").split())
            match = re.match(r"^(No|[\d,]+) contributions? on\b", tooltip)
            if not match:
                raise ValueError(f"Missing or unrecognized contribution count for {day}")
            result[day] = 0 if match[1] == "No" else int(match[1].replace(",", ""))
        if not result:
            raise ValueError("GitHub returned no contribution calendar; keeping the existing card")
        return result


def read_calendar(username: str, start: date, end: date):
    url = f"https://github.com/users/{username}/contributions?" + urlencode({
        "from": start.isoformat(), "to": end.isoformat(),
    })
    request = Request(url, headers={
        "User-Agent": f"{username}-profile-activity/1.0",
        "Accept": "text/html", "Accept-Language": "en-US,en;q=0.9",
    })
    for attempt in range(3):
        try:
            with urlopen(request, timeout=20) as response:
                if response.status != 200:
                    raise ValueError(f"Unexpected GitHub response: {response.status}")
                body = response.read().decode("utf-8")
            parser = CalendarParser()
            parser.feed(body)
            return {day: count for day, count in parser.counts().items() if start <= day <= end}
        except HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
        except (URLError, TimeoutError):
            if attempt == 2:
                raise
        time.sleep(2 ** attempt)
    raise RuntimeError("Unable to read GitHub contributions")


def validate_days(days, start: date, today: date):
    result = {day: count for day, count in days.items() if start <= day <= today}
    for day in date_range(start, today):
        # A new local day may not exist on GitHub yet. Only today can be absent.
        if day == today and day not in result:
            result[day] = 0
        if day not in result:
            raise ValueError(f"Incomplete calendar: missing {day}; keeping the existing card")
        if type(result[day]) is not int or result[day] < 0:
            raise ValueError(f"Invalid contribution count for {day}")
    return dict(sorted(result.items()))


def fetch_days(username: str, start: date, today: date):
    windows = [(max(start, date(year, 1, 1)), min(today, date(year, 12, 31)))
               for year in range(start.year, today.year + 1)]
    days = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        for calendar in pool.map(lambda window: read_calendar(username, *window), windows):
            days.update(calendar)
    return validate_days(days, start, today)


def calculate_stats(days, today: date):
    current = longest = run = 0
    longest_start = longest_end = run_start = None
    for day, count in sorted(days.items()):
        if count > 0:
            if run == 0:
                run_start = day
            run += 1
            if run > longest:
                longest, longest_start, longest_end = run, run_start, day
        else:
            run = 0
    end = today if days.get(today, 0) else today - DAY
    cursor = end
    while days.get(cursor, 0) > 0:
        current += 1
        cursor -= DAY
    return {
        "total": sum(days.values()),
        "current": current,
        "current_start": cursor + DAY if current else None,
        "current_end": end if current else None,
        "longest": longest,
        "longest_start": longest_start,
        "longest_end": longest_end,
    }


def short_date(value):
    return f"{value.day} {value:%b %Y}"


def streak_dates(start, end):
    if start is None:
        return "No active streak"
    return short_date(start) if start == end else f"{short_date(start)} – {short_date(end)}"


def render_svg(username: str, days, stats, start: date, now: datetime):
    today = now.date()
    sunday = today - timedelta(days=(today.weekday() + 1) % 7)
    grid_start = sunday - timedelta(weeks=25)
    visible = {day: count for day, count in days.items() if day >= grid_start}
    maximum = max(visible.values(), default=0)
    esc = html.escape
    parts = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="850" height="490" viewBox="0 0 850 490" role="img" aria-labelledby="title description">
<title id="title">{esc(username)}'s GitHub activity</title>
<desc id="description">{stats['current']} day current streak, {stats['longest']} day longest streak, {stats['total']} contributions since {start}. Refreshed {esc(now.isoformat())}. Calendar dates are supplied by GitHub.</desc>
<style>text{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif}}.label{{fill:#9caab6;font-size:13px}}.value{{fill:#eef3f7;font-size:42px;font-weight:700;letter-spacing:-1px}}.detail{{fill:#9caab6;font-size:12px}}.month{{fill:#9caab6;font-size:12px}}</style>
<rect x=".5" y=".5" width="849" height="489" rx="16" fill="#0d1117" stroke="#30363d"/>
<circle cx="33" cy="34" r="4" fill="#b8e600"/>
<text x="46" y="39" fill="#eef3f7" font-size="15" font-weight="600">GitHub Activity</text>
<text x="820" y="39" text-anchor="end" class="label">@{esc(username)}</text>
<path d="M30 177H820" stroke="#29323b"/>
<text x="30" y="210" fill="#eef3f7" font-size="14" font-weight="600">The last 26 weeks</text>
<text x="820" y="210" text-anchor="end" class="label">{sum(visible.values()):,} contributions</text>''']
    metrics = [
        (30, "CURRENT STREAK", stats["current"], streak_dates(stats["current_start"], stats["current_end"])),
        (300, "LONGEST STREAK", stats["longest"], streak_dates(stats["longest_start"], stats["longest_end"])),
        (570, "TOTAL CONTRIBUTIONS", stats["total"], f"Since {short_date(start)}"),
    ]
    for x, label, value, detail in metrics:
        color = ' style="fill:#b8e600"' if label == "CURRENT STREAK" else ""
        parts.append(f'<text x="{x}" y="79" class="label">{label}</text>')
        parts.append(f'<text x="{x}" y="124" class="value"{color}>{value:,}</text>')
        parts.append(f'<text x="{x}" y="149" class="detail">{esc(detail)}</text>')
    for row, label in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        parts.append(f'<text x="67" y="{267 + row * 25}" text-anchor="end" class="month">{label}</text>')
    last_month = None
    for week in range(26):
        week_start = grid_start + timedelta(weeks=week)
        # Use the Thursday to keep month labels near the majority of the week.
        month = (week_start + timedelta(days=4)).month
        x = 84 + week * 28
        if month != last_month:
            parts.append(f'<text x="{x}" y="241" class="month">{(week_start + timedelta(days=4)):%b}</text>')
            last_month = month
        for row in range(7):
            day = week_start + timedelta(days=row)
            if day > today:
                continue
            count = days.get(day, 0)
            level = 0 if count == 0 else min(4, max(1, (count * 4 + maximum - 1) // maximum))
            outline = ' stroke="#b8e600" stroke-width="1.5"' if day == today else ""
            parts.append(f'<rect x="{x}" y="{253 + row * 25}" width="21" height="19" rx="3" fill="{COLORS[level]}"{outline}><title>{day}: {count} contributions</title></rect>')
    parts.append('<text x="84" y="447" class="detail">Less</text>')
    for i, color in enumerate(COLORS):
        parts.append(f'<rect x="{119 + i * 17}" y="436" width="12" height="12" rx="2" fill="{color}"/>')
    parts.append('<text x="209" y="447" class="detail">More</text>')
    parts.append(f'<text x="805" y="447" text-anchor="end" class="detail">Today: {days[today]} contributions</text>')
    parts.append(f'<text x="30" y="475" class="detail">Public GitHub calendar · Updated {now:%d %b %Y, %H:%M} {esc(now.tzname() or "")} · Every 6 hours</text>')
    parts.append('</svg>\n')
    return "\n".join(parts)


def prepare_readme(readme: str, username: str, svg: str):
    if readme.count(START_MARKER) != 1 or readme.count(END_MARKER) != 1:
        raise ValueError("README must contain exactly one pair of GitHub activity markers")
    before, rest = readme.split(START_MARKER)
    _, after = rest.split(END_MARKER)
    version = hashlib.sha256(svg.encode()).hexdigest()[:16]
    card = (f"\n[![{username}'s GitHub activity](./assets/github-activity.svg?v={version})]"
            f"(https://github.com/{username})\n")
    return before + START_MARKER + card + END_MARKER + after


def main():
    username = os.getenv("ACTIVITY_USERNAME", "khanhvinhnguyen")
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", username):
        raise ValueError("Invalid GitHub username")
    start = date.fromisoformat(os.getenv("ACTIVITY_START_DATE", "2017-08-21"))
    now = datetime.now(ZoneInfo(os.getenv("ACTIVITY_TIMEZONE", "Asia/Ho_Chi_Minh")))
    if start > now.date():
        raise ValueError("Activity start date cannot be in the future")
    days = fetch_days(username, start, now.date())
    stats = calculate_stats(days, now.date())
    svg = render_svg(username, days, stats, start, now)
    readme_path = ROOT / "README.md"
    readme = prepare_readme(readme_path.read_text(), username, svg)
    report = {
        "username": username, "updated_at": now.isoformat(),
        "timezone": str(now.tzinfo), "source": f"https://github.com/users/{username}/contributions",
        "coverage": {"from": str(start), "to": str(now.date())},
        "stats": stats,
        "days": {str(day): count for day, count in days.items()},
    }
    outputs = {
        ROOT / "assets/github-activity.svg": svg,
        ROOT / "assets/github-activity.json": json.dumps(report, default=str, indent=2) + "\n",
        readme_path: readme,
    }
    # Fetching, parsing, completeness checks and rendering finish before any write.
    # The workflow publishes all three files together in a single Git commit.
    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
    print(json.dumps({"updated_at": now.isoformat(), **stats}, default=str))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Activity refresh failed: {error}", file=sys.stderr)
        sys.exit(1)
