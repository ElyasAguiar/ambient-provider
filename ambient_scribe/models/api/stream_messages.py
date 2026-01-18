# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""FastStream message schemas for Redis Streams."""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TranscriptionJobMessage(BaseModel):
    """Message schema for transcription job requests."""

    job_id: str = Field(..., description="Unique job identifier")
    transcript_id: str = Field(..., description="Database transcript ID")
    audio_key: str = Field(..., description="MinIO object key for audio file")
    filename: str = Field(..., description="Original filename")
    engine: str = Field(..., description="Transcription engine: 'asr' or 'whisperx'")
    language: str = Field(..., description="Language code (e.g., 'en-US', 'en')")
    context_id: Optional[str] = Field(None, description="Optional context ID for word boosting")
    engine_params: Dict[str, Any] = Field(
        default_factory=dict, description="Engine-specific parameters"
    )
    retry_count: int = Field(default=0, description="Number of retry attempts")

    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "550e8400-e29b-41d4-a716-446655440000",
                "transcript_id": "660e8400-e29b-41d4-a716-446655440001",
                "audio_key": "transcriptions/2024/01/audio.wav",
                "filename": "recording.wav",
                "engine": "whisperx",
                "language": "en",
                "context_id": None,
                "engine_params": {
                    "model": "large-v3",
                    "enable_diarization": True,
                    "min_speakers": 2,
                    "max_speakers": 2,
                },
                "retry_count": 0,
            }
        }


class TranscriptionSegment(BaseModel):
    """Single transcription segment with timing and speaker info."""

    start: float = Field(..., description="Start time in seconds")
    end: float = Field(..., description="End time in seconds")
    text: str = Field(..., description="Transcribed text")
    speaker_tag: Optional[int] = Field(None, description="Speaker identifier (0, 1, 2, ...)")
    confidence: Optional[float] = Field(None, description="Confidence score (0-1)")


class TranscriptionResultMessage(BaseModel):
    """Message schema for transcription results."""

    job_id: str = Field(..., description="Job identifier matching the request")
    transcript_id: str = Field(..., description="Database transcript ID")
    status: str = Field(..., description="Result status: 'completed' or 'failed'")
    segments: List[Dict[str, Any]] = Field(
        default_factory=list, description="List of transcription segments"
    )
    duration: Optional[float] = Field(None, description="Total audio duration in seconds")
    language: Optional[str] = Field(None, description="Detected or specified language")
    speaker_roles: Optional[Dict[int, str]] = Field(
        None, description="Mapping of speaker_tag to role (patient/provider)"
    )
    error: Optional[str] = Field(None, description="Error message if status is 'failed'")
    retry_count: int = Field(default=0, description="Number of retry attempts made")

    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "550e8400-e29b-41d4-a716-446655440000",
                "transcript_id": "660e8400-e29b-41d4-a716-446655440001",
                "status": "completed",
                "segments": [
                    {
                        "start": 0.0,
                        "end": 2.5,
                        "text": "Hello, how are you feeling today?",
                        "speaker_tag": 0,
                        "confidence": 0.95,
                    },
                    {
                        "start": 2.8,
                        "end": 5.0,
                        "text": "I've been having some chest pain.",
                        "speaker_tag": 1,
                        "confidence": 0.92,
                    },
                ],
                "duration": 5.0,
                "language": "en",
                "speaker_roles": {0: "provider", 1: "patient"},
                "error": None,
                "retry_count": 0,
            }
        }
