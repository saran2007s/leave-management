import os
from collections import defaultdict
from datetime import date, timedelta

import httpx

from app.schemas import CalendarEventOut, TeamSummaryOut


def _build_template_summary(
    events: list[CalendarEventOut],
    holidays: set[date],
    start_date: date,
    end_date: date,
    max_off_per_day: int,
) -> str:
    """Deterministic plain-English fallback summary when GEMINI_API_KEY is not configured."""
    if not events:
        return (
            f"No approved or pending leave requests between "
            f"{start_date.isoformat()} and {end_date.isoformat()}. "
            f"Full team capacity is available (cap: {max_off_per_day} off/day)."
        )

    approved_count = sum(1 for e in events if e.status == "approved")
    pending_count = sum(1 for e in events if e.status == "pending")
    people_off = sorted({e.user_name for e in events})

    # Count overlapping working days inside the requested window to spot peak days
    day_counts: dict[date, int] = defaultdict(int)
    current = start_date
    while current <= end_date:
        if current.weekday() < 5 and current not in holidays:
            for ev in events:
                if ev.start_date <= current <= ev.end_date:
                    day_counts[current] += 1
        current += timedelta(days=1)

    peak_days = [
        f"{day.isoformat()} ({count}/{max_off_per_day} off)"
        for day, count in sorted(day_counts.items())
        if count >= max_off_per_day
    ]

    summary = (
        f"From {start_date.isoformat()} to {end_date.isoformat()}, there are "
        f"{len(events)} active leave request(s) ({approved_count} approved, {pending_count} pending) "
        f"involving {len(people_off)} team member(s): {', '.join(people_off)}."
    )
    if peak_days:
        summary += f" Team capacity limit reached on: {', '.join(peak_days[:5])}."
    else:
        summary += f" All working days remain below the team cap of {max_off_per_day} off/day."

    return summary


def _call_gemini(prompt: str, api_key: str) -> str | None:
    """Call Google Gemini REST API with a short timeout. Returns None on any failure."""
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={api_key}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 180},
    }
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return text.strip()
    except Exception:
        return None


def generate_team_summary(
    events: list[CalendarEventOut],
    holidays: set[date],
    start_date: date,
    end_date: date,
    max_off_per_day: int,
) -> TeamSummaryOut:
    """
    Generate a concise team availability summary using Gemini if GEMINI_API_KEY is set,
    falling back seamlessly to the deterministic template summary otherwise.
    """
    fallback_text = _build_template_summary(
        events=events,
        holidays=holidays,
        start_date=start_date,
        end_date=end_date,
        max_off_per_day=max_off_per_day,
    )

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return TeamSummaryOut(
            summary=fallback_text,
            source="template",
            start_date=start_date,
            end_date=end_date,
            total_requests=len(events),
        )

    event_lines = [
        f"- {e.user_name}: {e.leave_type_name} ({e.status}), {e.start_date} to {e.end_date} ({e.days_count} working days)"
        for e in events
    ]
    facts = "\n".join(event_lines) if event_lines else "None."
    prompt = (
        "You are an HR operations assistant. Write a clear, concise 2-3 sentence "
        "team availability summary for a manager based strictly on these facts.\n"
        f"Window: {start_date.isoformat()} to {end_date.isoformat()}\n"
        f"Team cap (max off per day): {max_off_per_day}\n"
        f"Leave requests:\n{facts}\n"
        "Mention pending approvals or tight capacity dates if any."
    )

    ai_text = _call_gemini(prompt, api_key)
    if ai_text:
        return TeamSummaryOut(
            summary=ai_text,
            source="gemini",
            start_date=start_date,
            end_date=end_date,
            total_requests=len(events),
        )

    return TeamSummaryOut(
        summary=fallback_text,
        source="template",
        start_date=start_date,
        end_date=end_date,
        total_requests=len(events),
    )