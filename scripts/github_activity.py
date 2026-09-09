#!/usr/bin/env python3
"""Build a dependency-free profile card from GitHub's public contribution calendar."""

from __future__ import annotations

import hashlib
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

from merko import render_graph as render_svg, render_streak as render_streak_svg

ROOT = Path(__file__).resolve().parents[1]
START_MARKER = "<!-- github-activity:start -->"
END_MARKER = "<!-- github-activity:end -->"
DAY = timedelta(days=1)


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


def prepare_readme(readme: str, username: str, svg: str, streak_svg: str):
    if readme.count(START_MARKER) != 1 or readme.count(END_MARKER) != 1:
        raise ValueError("README must contain exactly one pair of GitHub activity markers")
    before, rest = readme.split(START_MARKER)
    _, after = rest.split(END_MARKER)
    graph_version = hashlib.sha256(svg.encode()).hexdigest()[:16]
    streak_version = hashlib.sha256(streak_svg.encode()).hexdigest()[:16]
    card = (
        f"\n[![GitHub Streak](./assets/github-streak.svg?v={streak_version})]"
        f"(https://github.com/{username})\n\n"
        f"[![{username}'s GitHub Activity Graph](./assets/github-activity.svg?v={graph_version})]"
        f"(https://github.com/{username})\n"
    )
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
    svg = render_svg(username, days, stats, start, now, os.getenv("ACTIVITY_DISPLAY_NAME", username))
    streak_svg = render_streak_svg(username, days, stats, start, now)
    readme_path = ROOT / "README.md"
    readme = prepare_readme(readme_path.read_text(), username, svg, streak_svg)
    report = {
        "username": username, "updated_at": now.isoformat(),
        "timezone": str(now.tzinfo), "source": f"https://github.com/users/{username}/contributions",
        "coverage": {"from": str(start), "to": str(now.date())},
        "stats": stats,
        "days": {str(day): count for day, count in days.items()},
    }
    outputs = {
        ROOT / "assets/github-activity.svg": svg,
        ROOT / "assets/github-streak.svg": streak_svg,
        ROOT / "assets/github-activity.json": json.dumps(report, default=str, indent=2) + "\n",
        readme_path: readme,
    }
    # Fetching, parsing, completeness checks and rendering finish before any write.
    # The workflow publishes all four files together in a single Git commit.
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
