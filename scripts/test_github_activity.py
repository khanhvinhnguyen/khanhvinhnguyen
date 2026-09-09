import unittest
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zoneinfo import ZoneInfo

from github_activity import (
    CalendarParser, calculate_stats, main, prepare_readme, render_svg, render_streak_svg, validate_days,
)


class ActivityTests(unittest.TestCase):
    def test_today_without_a_contribution_preserves_yesterdays_streak(self):
        days = {date(2026, 9, 7): 4, date(2026, 9, 8): 6, date(2026, 9, 9): 0}
        stats = calculate_stats(days, date(2026, 9, 9))
        self.assertEqual(stats["current"], 2)
        self.assertEqual(stats["current_end"], date(2026, 9, 8))

    def test_yesterday_without_a_contribution_breaks_the_streak(self):
        days = {date(2026, 9, 7): 4, date(2026, 9, 8): 0, date(2026, 9, 9): 0}
        self.assertEqual(calculate_stats(days, date(2026, 9, 9))["current"], 0)

    def test_today_starts_a_new_streak_after_a_gap(self):
        days = {date(2026, 9, 7): 4, date(2026, 9, 8): 0, date(2026, 9, 9): 2}
        self.assertEqual(calculate_stats(days, date(2026, 9, 9))["current"], 1)

    def test_streak_crosses_the_year_boundary(self):
        days = {date(2025, 12, 30): 1, date(2025, 12, 31): 3, date(2026, 1, 1): 2}
        stats = calculate_stats(days, date(2026, 1, 1))
        self.assertEqual((stats["current"], stats["longest"], stats["total"]), (3, 3, 6))

    def test_missing_historical_data_is_an_error_not_a_zero(self):
        with self.assertRaisesRegex(ValueError, "Incomplete calendar"):
            validate_days({date(2026, 9, 9): 2}, date(2026, 9, 7), date(2026, 9, 9))

    def test_only_today_may_be_missing_from_the_calendar(self):
        days = validate_days({date(2026, 9, 8): 6}, date(2026, 9, 8), date(2026, 9, 9))
        self.assertEqual(days[date(2026, 9, 9)], 0)
        self.assertEqual(calculate_stats(days, date(2026, 9, 9))["current"], 1)

    def test_leap_day_is_required(self):
        with self.assertRaisesRegex(ValueError, "2024-02-29"):
            validate_days({date(2024, 2, 28): 1, date(2024, 3, 1): 1}, date(2024, 2, 28), date(2024, 3, 1))

    def test_parser_reads_counts_not_intensity_levels(self):
        parser = CalendarParser()
        parser.feed('''<td id="day1" data-date="2026-09-08" data-level="1"></td>
            <tool-tip for="day1">6 contributions on September 8th.</tool-tip>
            <td id="day2" data-date="2026-09-09" data-level="0"></td>
            <tool-tip for="day2">No contributions on September 9th.</tool-tip>''')
        self.assertEqual(parser.counts(), {date(2026, 9, 8): 6, date(2026, 9, 9): 0})

    def test_empty_or_changed_html_fails_instead_of_resetting_stats(self):
        for body in ('<html>Service unavailable</html>', '<td id="x" data-date="2026-09-09"></td>'):
            parser = CalendarParser()
            parser.feed(body)
            with self.assertRaises(ValueError):
                parser.counts()

    def test_fetch_failure_keeps_the_existing_files(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "assets").mkdir()
            (root / "assets/github-activity.svg").write_text("previous-good-card")
            (root / "README.md").write_text("previous-readme")
            with patch("github_activity.ROOT", root), patch("github_activity.fetch_days", side_effect=ValueError("Missing data")):
                with self.assertRaisesRegex(ValueError, "Missing data"):
                    main()
            self.assertEqual((root / "assets/github-activity.svg").read_text(), "previous-good-card")
            self.assertEqual((root / "README.md").read_text(), "previous-readme")

    def test_timezone_rolls_over_at_vietnam_midnight(self):
        now = datetime.fromisoformat("2026-09-08T18:00:00+00:00").astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))
        self.assertEqual(now.date(), date(2026, 9, 9))

    def test_card_is_valid_xml_even_without_contributions(self):
        import xml.etree.ElementTree as ET
        today = date(2026, 9, 9)
        days = {today: 0}
        now = datetime(2026, 9, 9, 10, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
        for renderer in (render_svg, render_streak_svg):
            svg = renderer("someone", days, calculate_stats(days, today), today, now)
            self.assertEqual(ET.fromstring(svg).tag, "{http://www.w3.org/2000/svg}svg")

    def test_graph_retains_31_exact_counts_across_month_boundary(self):
        import xml.etree.ElementTree as ET
        from datetime import timedelta
        today = date(2026, 9, 9)
        days = {today - timedelta(days=i): i + 1 for i in range(31)}
        now = datetime(2026, 9, 9, 10, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
        svg = render_svg("someone", days, calculate_stats(days, today), min(days), now)
        points = ET.fromstring(svg).findall('.//*[@class="ct-point"]')
        self.assertEqual(len(points), 31)
        self.assertEqual(points[0][0].text, "2026-08-10: 31 contributions")
        self.assertEqual(points[-1][0].text, "2026-09-09: 1 contributions")

    def test_graph_omits_empty_today_like_the_original_widget(self):
        import xml.etree.ElementTree as ET
        today = date(2026, 9, 9)
        days = {date(2026, 9, 8): 6, today: 0}
        now = datetime(2026, 9, 9, 10, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
        svg = render_svg("someone", days, calculate_stats(days, today), min(days), now)
        points = ET.fromstring(svg).findall('.//*[@class="ct-point"]')
        self.assertEqual(points[-1][0].text, "2026-09-08: 6 contributions")

    def test_readme_preserves_other_content_and_versions_the_image(self):
        original = "Before\n<!-- github-activity:start -->old<!-- github-activity:end -->\nAfter"
        first = prepare_readme(original, "someone", "first-svg", "first-streak")
        second = prepare_readme(first, "someone", "second-svg", "second-streak")
        self.assertTrue(second.startswith("Before\n"))
        self.assertTrue(second.endswith("\nAfter"))
        self.assertNotEqual(first, second)
        with self.assertRaises(ValueError):
            prepare_readme("No markers", "someone", "svg", "streak")


if __name__ == "__main__":
    unittest.main()
