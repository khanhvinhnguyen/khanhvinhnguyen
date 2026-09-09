"""Merko renderers matching the original profile widgets.

Streak SVG: adapted from DenverCoder1/github-readme-streak-stats.
Graph layout/styles: adapted from Ashutosh00710/github-readme-activity-graph.
Graph interpolation/scaling: adapted from Chartist 0.11.4.
See third_party/ for the upstream sources and MIT license notices.
"""

from datetime import timedelta
from html import escape
from math import ceil, floor, log10, isqrt
from pathlib import Path
from string import Template

HERE = Path(__file__).resolve().parent


def format_date(value, today):
    """The original README's PHP date_format=j/n[/Y]."""
    return f"{value.day}/{value.month}" + (f"/{value.year}" if value.year != today.year else "")


def date_span(start, end, today):
    start, end = start or today, end or today
    first, last = format_date(start, today), format_date(end, today)
    return first if first == last else f"{first} - {last}"


def render_streak(username, days, stats, start, now):
    first_contribution = next((day for day, count in sorted(days.items()) if count), start)
    template = Template((HERE / "templates/streak.svg").read_text(encoding="utf-8"))
    values = {
        "title": f"{username}'s GitHub Streak",
        "description": (
            f"Current streak: {stats['current']} days; longest streak: {stats['longest']} days; "
            f"total contributions: {stats['total']}. Updated {now.isoformat()} from GitHub's "
            "public contribution calendar. Refreshed every six hours."
        ),
        "total": f"{stats['total']:,}",
        "current": f"{stats['current']:,}",
        "longest": f"{stats['longest']:,}",
        "total_range": f"{format_date(first_contribution, now.date())} - Present",
        "current_range": date_span(stats["current_start"], stats["current_end"], now.date()),
        "longest_range": date_span(stats["longest_start"] or start, stats["longest_end"] or start, now.date()),
    }
    return template.substitute({key: escape(value) for key, value in values.items()})


def chart_scale(maximum):
    """Chartist's integer AutoScaleAxis for a 270px plot and 20px minimum spacing."""
    high = max(1, maximum)
    step = 10 ** floor(log10(high))
    upper = ceil(high / step) * step
    factor = next((n for n in range(2, isqrt(upper) + 1) if upper % n == 0), upper)
    project = lambda value: 270 * value / upper
    if project(1) >= 20:
        step = 1
    elif factor < step and project(factor) >= 20:
        step = factor
    elif project(step) < 20:
        while project(step) <= 20:
            step *= 2
    else:
        while project(step / 2) >= 20 and step % 2 == 0:
            step //= 2
    upper = ceil(high / step) * step
    return upper, step


def number(value):
    # Chartist SVG paths use three fractional digits by default.
    return f"{value:.3f}".rstrip("0").rstrip(".") if value else "0"


def smooth_path(points):
    """Chartist's default monotone cubic interpolation, without DOM dependencies."""
    if not points:
        return ""
    path = [f"M{number(points[0][0])},{number(points[0][1])}"]
    if len(points) < 3:
        return "".join(path + [f"L{number(x)},{number(y)}" for x, y in points[1:]])
    widths = [b[0] - a[0] for a, b in zip(points, points[1:])]
    slopes = [(b[1] - a[1]) / width for a, b, width in zip(points, points[1:], widths)]
    tangents = [slopes[0]]
    for i in range(1, len(points) - 1):
        previous, following = slopes[i - 1], slopes[i]
        if not previous or not following or (previous > 0) != (following > 0):
            tangents.append(0)
        else:
            before, after = widths[i - 1], widths[i]
            tangents.append(3 * (before + after) / (
                (2 * after + before) / previous + (after + 2 * before) / following
            ))
    tangents.append(slopes[-1])
    for i, (a, b) in enumerate(zip(points, points[1:])):
        third = widths[i] / 3
        values = (a[0] + third, a[1] + tangents[i] * third,
                  b[0] - third, b[1] - tangents[i + 1] * third, b[0], b[1])
        path.append("C" + ",".join(number(value) for value in values))
    return "".join(path)


def render_graph(username, days, stats, start, now, display_name=None):
    # Same defaults as the old URL: width=1200, height=420, days=31,
    # theme=merko, hide_border=true, area=false, grid=true, radius=0.
    end = now.date()
    if days.get(end, 0) == 0:
        end -= timedelta(days=1)
    dates = [end - timedelta(days=30 - i) for i in range(31)]
    counts = [days.get(day, 0) for day in dates]
    upper, step = chart_scale(max(counts))
    points = [(90 + i * 1060 / 30, 350 - count * 270 / upper) for i, count in enumerate(counts)]
    title = escape(f"{display_name or username}'s Contribution Graph")
    licenses = "\n".join((HERE / "third_party" / name).read_text(encoding="utf-8")
                         for name in ("activity-graph-LICENSE.txt", "chartist-LICENSE.txt"))
    parts = [f'''<svg width="1200" height="420" viewBox="0 0 1200 420" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="title description">
<!--
{licenses}-->
<title id="title">{title}</title>
<desc id="description">Daily contributions, {dates[0]} through {dates[-1]}. Updated {escape(now.isoformat())} from GitHub's public contribution calendar.</desc>
<rect x="0" y="0" width="1200" height="420" rx="0" fill="#0a0f0b"/>
<style>
svg {{ font: 600 18px 'Segoe UI', Ubuntu, Sans-Serif; user-select: none; }}
.header {{ font: 600 20px 'Segoe UI', Ubuntu, Sans-Serif; fill: #f6f8fa; }}
.ct-label {{ fill: #f6f8fa; color: #f6f8fa; font-size: 12px; line-height: 1; }}
.ct-grid {{ stroke: #f6f8fa; stroke-width: 1px; stroke-opacity: 0.3; stroke-dasharray: 2px; }}
.ct-point {{ stroke-width: 10px; stroke-linecap: round; stroke: #f6f8fa; animation: blink 1s ease-in-out both; }}
.ct-line {{ fill: none; stroke-width: 4px; stroke-dasharray: 5000; stroke-dashoffset: 0; stroke: #abd200; animation: dash 5s ease-in-out both; }}
@keyframes blink {{ from {{ opacity: 0; transform: translateX(-20px); }} to {{ opacity: 1; transform: translateX(0); }} }}
@keyframes dash {{ from {{ stroke-dashoffset: 5000; }} to {{ stroke-dashoffset: 0; }} }}
@media (prefers-reduced-motion: reduce) {{ * {{ animation: none !important; }} }}
</style>
<text x="600" y="39" text-anchor="middle" class="header">{title}</text>
<g class="ct-grids">''']
    for x, _ in points:
        parts.append(f'<line x1="{number(x)}" y1="350" x2="{number(x)}" y2="80" class="ct-grid ct-horizontal"/>')
    for value in range(0, upper + 1, step):
        y = 350 - value * 270 / upper
        parts.append(f'<line x1="90" y1="{number(y)}" x2="1150" y2="{number(y)}" class="ct-grid ct-vertical"/>')
    parts.append('</g><g class="ct-labels">')
    for (x, _), day in zip(points, dates):
        parts.append(f'<text x="{number(x - 4.5)}" y="370" class="ct-label ct-horizontal ct-end">{day.day}</text>')
    for value in range(0, upper + 1, step):
        y = 354.5 - value * 270 / upper
        parts.append(f'<text x="80" y="{number(y)}" text-anchor="end" class="ct-label ct-vertical ct-start">{value}</text>')
    parts.append('</g><g class="ct-series ct-series-a">')
    parts.append(f'<path d="{smooth_path(points)}" class="ct-line"/>')
    for (x, y), day, count in zip(points, dates, counts):
        parts.append(f'<line x1="{number(x)}" y1="{number(y)}" x2="{number(x + 0.01)}" y2="{number(y)}" class="ct-point"><title>{day}: {count} contributions</title></line>')
    parts.append('''</g>
<text x="620" y="400" dominant-baseline="text-after-edge" text-anchor="middle" class="ct-axis-title ct-label">Days</text>
<text x="20" y="215" transform="rotate(-90, 20, 215)" dominant-baseline="hanging" text-anchor="middle" class="ct-axis-title ct-label">Contributions</text>
</svg>
''')
    return "\n".join(parts)
