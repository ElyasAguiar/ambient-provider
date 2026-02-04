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


class TranscriptionWord(BaseModel):
    """Single transcription word with timing and speaker info."""

    text: str = Field(..., description="Transcribed word")
    start: float = Field(..., description="Start time in milliseconds")
    end: float = Field(..., description="End time in milliseconds")
    confidence: Optional[float] = Field(None, description="Confidence score (0-1)")
    speaker: Optional[str] = Field(None, description="Speaker identifier (A, B, C, ...)")


class TranscriptionResultMessage(BaseModel):
    """Message schema for transcription results."""

    job_id: str = Field(..., description="Job identifier matching the request")
    transcript_id: str = Field(..., description="Database transcript ID")
    status: str = Field(..., description="Result status: 'completed' or 'failed'")
    text: str = Field(default="", description="Complete transcription text")
    words: List[Dict[str, Any]] = Field(
        default_factory=list, description="List of transcription words"
    )
    duration: Optional[float] = Field(None, description="Total audio duration in seconds")
    language: Optional[str] = Field(None, description="Detected or specified language")
    speaker_roles: Optional[Dict[str, str]] = Field(
        None, description="Mapping of speaker to role (patient/provider)"
    )
    error: Optional[str] = Field(None, description="Error message if status is 'failed'")
    retry_count: int = Field(default=0, description="Number of retry attempts made")

    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "550e8400-e29b-41d4-a716-446655440000",
                "transcript_id": "660e8400-e29b-41d4-a716-446655440001",
                "status": "completed",
                "text": "Bom dia Jesus...",
                "words": [
                    {
                        "text": "Bom",
                        "start": 31,
                        "end": 612,
                        "confidence": 0.935,
                        "speaker": "A",
                    },
                    {
                        "text": "dia",
                        "start": 615,
                        "end": 890,
                        "confidence": 0.92,
                        "speaker": "A",
                    },
                ],
                "duration": 307,
                "language": "pt",
                "speaker_roles": {"A": "provider", "B": "patient"},
                "error": None,
                "retry_count": 0,
            }
        }
