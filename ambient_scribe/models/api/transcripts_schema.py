# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pydantic schemas for transcript domain."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TranscriptSegment(BaseModel):
    """Individual transcript segment with timing and speaker info."""

    start: float = Field(..., description="Start time in seconds")
    end: float = Field(..., description="End time in seconds")
    text: str = Field(..., description="Transcribed text")
    speaker_tag: Optional[int] = Field(None, description="Speaker identifier")
    confidence: Optional[float] = Field(None, description="Confidence score 0-1")


class Transcript(BaseModel):
    """Complete transcript with metadata."""

    id: str = Field(..., description="Unique transcript identifier")
    segments: List[TranscriptSegment] = Field(..., description="List of transcript segments")
    language: str = Field(default="en-US", description="Language code")
    duration: Optional[float] = Field(None, description="Total duration in seconds")
    created_at: datetime = Field(default_factory=datetime.now)
    filename: Optional[str] = Field(None, description="Original filename")
    audio_url: Optional[str] = Field(None, description="URL to access the audio file")
    speaker_roles: Optional[Dict[int, str]] = Field(
        None, description="Mapping of speaker_tag to role (patient/provider)"
    )
    status: str = Field(default="processing", description="Transcript status")
    error_message: Optional[str] = Field(None, description="Error message if failed")
