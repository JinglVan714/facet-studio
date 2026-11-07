"""Timecode formatting.  Internal unit is always milliseconds."""

from __future__ import annotations


def format_ms(ms: int, *, with_millis: bool = True) -> str:
    if ms < 0:
        raise ValueError("ms must be >= 0")
    seconds, millis = divmod(int(ms), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if with_millis:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def format_range(start_ms: int, end_ms: int, *, with_millis: bool = False) -> str:
    return f"{format_ms(start_ms, with_millis=with_millis)}–{format_ms(end_ms, with_millis=with_millis)}"
