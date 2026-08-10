"""Pure daily-quiz schedule evaluation. No discord imports, fully testable."""

from datetime import datetime


def evaluate_schedule(
    now: datetime,
    quiz_time: str,
    reveal_time: str,
    last_quiz_date: str,
    quiz_started: bool,
    quiz_finished_today: bool,
) -> str:
    """Decide what the quiz loop should do at *now*.

    Returns one of:
        "reset"  - a new calendar day has started; clear daily flags
        "start"  - it is past the quiz time and no quiz has run today
        "reveal" - it is past the reveal time and a quiz is still open
        "idle"   - nothing to do
    """
    if last_quiz_date != now.date().isoformat():
        return "reset"

    try:
        start_hour, start_minute = (int(part) for part in quiz_time.split(":"))
        reveal_hour, reveal_minute = (int(part) for part in reveal_time.split(":"))
        if not (0 <= start_hour <= 23 and 0 <= start_minute <= 59 and 0 <= reveal_hour <= 23 and 0 <= reveal_minute <= 59):
            return "idle"
    except ValueError:
        return "idle"

    start_time_today = now.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
    reveal_time_today = now.replace(hour=reveal_hour, minute=reveal_minute, second=0, microsecond=0)

    if now >= start_time_today and now < reveal_time_today and not quiz_started and not quiz_finished_today:
        return "start"

    if now >= reveal_time_today and quiz_started:
        return "reveal"

    return "idle"
