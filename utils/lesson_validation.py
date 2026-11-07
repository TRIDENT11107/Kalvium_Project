from __future__ import annotations


MAX_DURATION_MINUTES = 45


def validate_time_plan(lesson: dict, *, max_minutes=MAX_DURATION_MINUTES) -> None:
    plan = lesson.get("time_plan")
    if not isinstance(plan, list) or not plan:
        raise ValueError("Lesson must include a non-empty time_plan.")
    total = 0
    for item in plan:
        try:
            minutes = int(item.get("minutes", 0))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("Every time_plan entry must have a positive integer duration.") from exc
        if minutes <= 0:
            raise ValueError("Every allocated lesson duration must be positive.")
        total += minutes
    if total > max_minutes:
        raise ValueError(f"Lesson duration cannot exceed {max_minutes} minutes (got {total}).")
    if total != int(lesson.get("duration_minutes", total)):
        raise ValueError("Lesson duration_minutes must equal the time_plan total.")
    for collection in ("modules", "activities"):
        for item in lesson.get(collection, []) or []:
            if "minutes" in item:
                try:
                    minutes = int(item["minutes"])
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"{collection} durations must be positive integers.") from exc
                if minutes <= 0:
                    raise ValueError(f"{collection} durations must be positive.")


def validate_lesson_duration(lesson: dict) -> None:
    validate_time_plan(lesson)
