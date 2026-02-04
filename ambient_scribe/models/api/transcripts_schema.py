# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pydantic schemas for transcript domain."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TranscriptWord(BaseModel):
    """Individual transcript word with timing and speaker info."""

    text: str = Field(..., description="Transcribed word")
    start: float = Field(..., description="Start time in milliseconds")
    end: float = Field(..., description="End time in milliseconds")
    confidence: Optional[float] = Field(None, description="Confidence score 0-1")
    speaker: Optional[str] = Field(None, description="Speaker identifier (A, B, C, ...)")


class Transcript(BaseModel):
    """Complete transcript with metadata."""

    id: str = Field(..., description="Unique transcript identifier (transcript_id)")
    language: str = Field(default="pt", description="Language code")
    duration: Optional[float] = Field(None, description="Total duration in seconds")
    text: str = Field(default="", description="Complete transcription text")
    words: List[TranscriptWord] = Field(
        default_factory=list, description="List of transcript words"
    )
    created_at: datetime = Field(default_factory=datetime.now)
    filename: Optional[str] = Field(None, description="Original filename")
    audio_url: Optional[str] = Field(None, description="URL to access the audio file")
    speaker_roles: Optional[Dict[str, str]] = Field(
        None, description="Mapping of speaker to role (patient/provider)"
    )
    status: str = Field(default="processing", description="Transcript status")
    error_message: Optional[str] = Field(None, description="Error message if failed")
