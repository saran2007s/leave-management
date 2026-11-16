from datetime import date

from app.services.working_days import count_working_days


def test_full_monday_to_friday():
    assert count_working_days(date(2026, 12, 7), date(2026, 12, 11), set()) == 5


def test_friday_to_monday_excludes_weekend():
    assert count_working_days(date(2026, 12, 11), date(2026, 12, 14), set()) == 2


def test_excludes_public_holiday_and_weekend():
    holidays = {date(2026, 12, 25)}
    # Thu 2026-12-24 to Mon 2026-12-28 -> Thu + Mon = 2 (Fri holiday + Sat/Sun excluded)
    assert count_working_days(date(2026, 12, 24), date(2026, 12, 28), holidays) == 2


def test_weekend_only_returns_zero():
    assert count_working_days(date(2026, 12, 12), date(2026, 12, 13), set()) == 0


def test_single_holiday_returns_zero():
    holidays = {date(2026, 12, 25)}
    assert count_working_days(date(2026, 12, 25), date(2026, 12, 25), holidays) == 0


def test_end_before_start_returns_zero():
    assert count_working_days(date(2026, 12, 10), date(2026, 12, 7), set()) == 0