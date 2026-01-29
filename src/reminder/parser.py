"""Parser for meeting time formats."""

import re
from datetime import datetime, timedelta
from dataclasses import dataclass


@dataclass
class Meeting:
    """Parsed meeting information."""

    start: datetime
    end: datetime
    original: str


def parse_meeting_time(text: str) -> Meeting | None:
    """
    Parse meeting time from various formats:
    - 'Thu 29/01/2026 10:00 - 11:00' (full format)
    - '11:30' (simple time, assumes today, 1 hour duration)

    Returns Meeting object or None if parsing fails.
    """
    text = text.strip()

    # Try simple time format first: HH:MM
    simple_pattern = r"^(\d{1,2}):(\d{2})$"
    simple_match = re.match(simple_pattern, text)
    if simple_match:
        try:
            hour = int(simple_match.group(1))
            minute = int(simple_match.group(2))
            now = datetime.now()
            start = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

            # If time is in the past today, assume tomorrow
            if start <= now:
                start += timedelta(days=1)

            end = start + timedelta(hours=1)
            return Meeting(start=start, end=end, original=text)
        except ValueError:
            pass

    # Try full format: Day DD/MM/YYYY HH:MM - HH:MM
    full_pattern = r"^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})$"
    full_match = re.match(full_pattern, text, re.IGNORECASE)
    if full_match:
        try:
            day = int(full_match.group(1))
            month = int(full_match.group(2))
            year = int(full_match.group(3))
            start_hour = int(full_match.group(4))
            start_minute = int(full_match.group(5))
            end_hour = int(full_match.group(6))
            end_minute = int(full_match.group(7))

            start = datetime(year, month, day, start_hour, start_minute)
            end = datetime(year, month, day, end_hour, end_minute)

            # Handle overnight meetings (end time is next day)
            if end < start:
                end = end.replace(day=day + 1)

            return Meeting(start=start, end=end, original=text)
        except ValueError:
            pass

    return None
