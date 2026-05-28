"""
Utility functions: date/time formatting, date ranges.
"""

from datetime import datetime, date, timedelta
from core.models import TZ

def format_datetime(dt: datetime) -> str:
    """2026-05-28 10:00"""
    return dt.astimezone(TZ).strftime("%Y-%m-%d %H:%M")

def format_time(dt: datetime) -> str:
    """10:00"""
    return dt.astimezone(TZ).strftime("%H:%M")

def format_date(dt: datetime) -> str:
    """28.05.2026"""
    return dt.astimezone(TZ).strftime("%d.%m.%Y")

def get_current_date() -> date:
    """Current date in TZ."""
    return datetime.now(TZ).date()

def get_current_datetime() -> datetime:
    """Current datetime in TZ."""
    return datetime.now(TZ)

def get_date_range(interval: str, ref_date: date = None) -> tuple[date, date]:
    """
    Return (start_date, end_date) inclusive.
    interval: 'today', 'tomorrow', 'week', 'next_week'
    """
    if ref_date is None:
        ref_date = get_current_date()
    if interval == 'today':
        return ref_date, ref_date
    elif interval == 'tomorrow':
        tomorrow = ref_date + timedelta(days=1)
        return tomorrow, tomorrow
    elif interval == 'week':
        # Monday to Sunday of the week containing ref_date
        start = ref_date - timedelta(days=ref_date.weekday())
        end = start + timedelta(days=6)
        return start, end
    elif interval == 'next_week':
        start = ref_date + timedelta(days=7 - ref_date.weekday())
        end = start + timedelta(days=6)
        return start, end
    else:
        raise ValueError(f"Unknown interval: {interval}")