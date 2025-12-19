# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Utilities for working with timecodes and transcript timestamps."""
import re
from typing import List, Tuple


def format_timecode(seconds: float) -> str:
    """Format seconds into MM:SS or HH:MM:SS format."""

    if not isinstance(seconds, (int, float)) or seconds < 0:
        return "00:00"

    # Validate and convert if timestamp seems to be in wrong units
    normalized_seconds = seconds

    # More aggressive detection: if > 3600 seconds (1 hour), it's probably wrong for typical conversations
    if seconds > 3600:
        print(f"DEBUG: Large timestamp detected: {seconds}s, attempting conversion")

        # Try different conversion factors
        candidates = [
            (1000, "milliseconds"),
            (1000000, "microseconds"),
            (1000000000, "nanoseconds"),
            (60, "minutes to seconds"),  # Sometimes timestamps are in minutes
        ]

        for factor, name in candidates:
            converted = seconds / factor
            if 0 <= converted <= 3600:  # Reasonable range: 0 to 1 hour
                normalized_seconds = converted
                print(f"DEBUG: Converted from {name}: {normalized_seconds}s")
                break

        # If still unreasonable after all conversions
        if normalized_seconds > 3600:
            print(f"DEBUG: Could not normalize large timestamp: {seconds}s")
            return "??:??"

    # Ensure we have valid integers
    hours = int(normalized_seconds // 3600)
    minutes = int((normalized_seconds % 3600) // 60)
    secs = int(normalized_seconds % 60)

    # Always return MM:SS format, never show hours for typical conversation timestamps
    # Only show hours if the conversation is genuinely longer than 1 hour
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes:02d}:{secs:02d}"


def parse_timecode(timecode: str) -> float:
    """Parse a timecode string back to seconds."""

    try:
        parts = timecode.split(":")

        if len(parts) == 2:  # MM:SS
            minutes, seconds = map(int, parts)
            return minutes * 60 + seconds
        elif len(parts) == 3:  # HH:MM:SS
            hours, minutes, seconds = map(int, parts)
            return hours * 3600 + minutes * 60 + seconds
        else:
            raise ValueError("Invalid timecode format")

    except (ValueError, TypeError):
        return 0.0


def create_hyperlinked_timecode(seconds: float, base_url: str = None) -> str:
    """Create a hyperlinked timecode for transcript navigation."""

    timecode = format_timecode(seconds)

    if base_url:
        return f"[{timecode}]({base_url}#t={seconds})"
    else:
        return f"[#{timecode}](#t={seconds})"


def extract_timecodes_from_text(text: str) -> List[Tuple[str, float]]:
    """Extract timecode references from text."""

    # Look for patterns like [#12:34] or [12:34]
    pattern = r"\[#?(\d{1,2}:\d{2}(?::\d{2})?)\]"
    matches = re.finditer(pattern, text)

    timecodes = []
    for match in matches:
        timecode_str = match.group(1)
        seconds = parse_timecode(timecode_str)
        timecodes.append((timecode_str, seconds))

    return timecodes


def add_timecode_links(text: str, transcript_id: str = None) -> str:
    """Add clickable links to timecodes in text."""

    def replace_timecode(match):
        timecode = match.group(1)
        seconds = parse_timecode(timecode)

        if transcript_id:
            return f'<a href="#transcript" data-time="{seconds}" class="timecode-link">[#{timecode}]</a>'
        else:
            return f'<span class="timecode" data-time="{seconds}">[#{timecode}]</span>'

    # Replace timecode patterns
    pattern = r"\[#?(\d{1,2}:\d{2}(?::\d{2})?)\]"
    return re.sub(pattern, replace_timecode, text)


def segment_timestamp_overlap(
    start1: float, end1: float, start2: float, end2: float, threshold: float = 0.5
) -> bool:
    """Check if two timestamp ranges overlap significantly."""

    # Calculate overlap
    overlap_start = max(start1, start2)
    overlap_end = min(end1, end2)
    overlap_duration = max(0, overlap_end - overlap_start)

    # Calculate total duration covered
    total_duration = max(end1, end2) - min(start1, start2)

    if total_duration == 0:
        return True

    # Check if overlap is significant
    overlap_ratio = overlap_duration / total_duration
    return overlap_ratio >= threshold


def find_transcript_context(
    target_time: float, segments: List, context_window: float = 30.0
) -> List:
    """Find transcript segments around a target time."""

    context_segments = []

    for segment in segments:
        # Check if segment is within context window
        if (
            segment.start <= target_time + context_window
            and segment.end >= target_time - context_window
        ):
            context_segments.append(segment)

    return context_segments
