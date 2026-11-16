from datetime import date, timedelta


def iter_working_days(start: date, end: date, holidays: set[date]) -> list[date]:
    """
    Return all working days from `start` to `end` inclusive,
    excluding Saturdays, Sundays, and dates in `holidays`.
    """
    if end < start:
        return []

    working_days: list[date] = []
    current = start
    while current <= end:
        # weekday(): Monday=0 ... Friday=4, Saturday=5, Sunday=6
        if current.weekday() < 5 and current not in holidays:
            working_days.append(current)
        current += timedelta(days=1)
    return working_days


def count_working_days(start: date, end: date, holidays: set[date]) -> int:
    """Count working days from `start` to `end` inclusive (pure function, no DB access)."""
    return len(iter_working_days(start, end, holidays))