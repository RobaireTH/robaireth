import unittest
from datetime import date, timedelta
from scripts.update_stats import dates_between, rolling_start, summarize


class StreakTests(unittest.TestCase):
    def history(self, start, end, active):
        return {day: active.get(day, 0) for day in dates_between(start, end)}

    def test_current_streak_can_end_yesterday(self):
        start, today = date(2026, 10, 1), date(2026, 10, 5)
        days = self.history(start, today, {date(2026, 10, 3): 2, date(2026, 10, 4): 4})
        stats = summarize(days, today, start)
        self.assertEqual(stats["current"], {"days": 2, "start": "2026-10-03", "end": "2026-10-04"})
        self.assertEqual(stats["progress"], 1)

    def test_current_streak_breaks_after_a_missing_full_day(self):
        start, today = date(2026, 10, 1), date(2026, 10, 5)
        stats = summarize(self.history(start, today, {date(2026, 10, 3): 2}), today, start)
        self.assertEqual(stats["current"], {"days": 0, "start": None, "end": None})
        self.assertEqual(stats["progress"], 0)

    def test_record_can_be_older_than_the_rolling_window(self):
        start, today = date(2024, 1, 1), date(2026, 10, 30)
        active = {start + timedelta(days=i): 1 for i in range(40)}
        active[today - timedelta(days=1)], active[today] = 2, 3
        stats = summarize(self.history(start, today, active), today, start)
        self.assertEqual(stats["longest"], {"days": 40, "start": "2024-01-01", "end": "2024-02-09"})
        self.assertEqual(stats["window"]["contributions"], 5)
        self.assertEqual(stats["window"]["start"], "2025-10-31")
        self.assertEqual(stats["current"]["days"], 2)
        self.assertAlmostEqual(stats["progress"], 0.05)

    def test_streak_dates_cross_year_boundaries(self):
        start, today = date(2025, 12, 29), date(2026, 1, 2)
        stats = summarize({day: 1 for day in dates_between(start, today)}, today, start)
        self.assertEqual(stats["current"]["days"], 5)
        self.assertEqual(stats["longest"]["start"], "2025-12-29")
        self.assertEqual(stats["longest"]["end"], "2026-01-02")

    def test_incomplete_history_does_not_publish_a_false_record(self):
        with self.assertRaises(ValueError):
            summarize({date(2026, 10, 30): 1}, date(2026, 10, 30), date(2026, 10, 1))

    def test_rolling_window_handles_leap_day(self):
        self.assertEqual(rolling_start(date(2024, 2, 29)), date(2023, 3, 1))
        self.assertEqual(rolling_start(date(2025, 2, 28)), date(2024, 2, 29))

    def test_no_activity_has_no_division_by_zero_or_invented_dates(self):
        day = date(2026, 10, 30)
        stats = summarize({day: 0}, day, day)
        self.assertEqual(stats["longest"], {"days": 0, "start": None, "end": None})
        self.assertEqual(stats["progress"], 0)


if __name__ == "__main__":
    unittest.main()
