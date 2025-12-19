# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pydantic models for API requests and responses."""
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
    segments: List[TranscriptSegment] = Field(
        ..., description="List of transcript segments"
    )
    language: str = Field(default="en-US", description="Language code")
    duration: Optional[float] = Field(None, description="Total duration in seconds")
    created_at: datetime = Field(default_factory=datetime.now)
    filename: Optional[str] = Field(None, description="Original filename")
    audio_url: Optional[str] = Field(None, description="URL to access the audio file")
    speaker_roles: Optional[Dict[int, str]] = Field(
        None, description="Mapping of speaker_tag to role (patient/provider)"
    )


class NoteRequest(BaseModel):
    """Request to generate a medical note."""

    transcript_id: str = Field(..., description="ID of the transcript to use")
    template_name: str = Field(..., description="Template to use for note generation")
    custom_sections: Optional[List[str]] = Field(
        None, description="Custom sections to include"
    )
    system_instructions: Optional[str] = Field(
        None, description="Additional instructions for the LLM"
    )
    include_traces: bool = Field(
        default=True, description="Whether to include reasoning traces"
    )


class Citation(BaseModel):
    """Citation linking note content to transcript."""

    text: str = Field(..., description="Cited text")
    start_time: float = Field(..., description="Start time in transcript")
    end_time: float = Field(..., description="End time in transcript")
    segment_id: Optional[str] = Field(
        None, description="Reference to transcript segment"
    )


class TraceEvent(BaseModel):
    """Individual reasoning trace event."""

    timestamp: datetime = Field(default_factory=datetime.now)
    event_type: str = Field(..., description="Type of trace event")
    message: str = Field(..., description="Trace message")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class NoteResponse(BaseModel):
    """Response containing generated note and metadata."""

    id: Optional[str] = Field(None, description="Unique identifier for the note")
    note_markdown: str = Field(..., description="Generated note in markdown format")
    trace_events: List[TraceEvent] = Field(
        default_factory=list, description="Reasoning traces"
    )
    citations: List[Citation] = Field(
        default_factory=list, description="Citations to transcript"
    )
    template_used: str = Field(..., description="Template that was used")
    generation_time: float = Field(..., description="Time taken to generate note")
    created_at: datetime = Field(default_factory=datetime.now)
    transcript_id: Optional[str] = Field(None, description="ID of the transcript used")
    title: Optional[str] = Field(None, description="Display title for the note")


class SuggestionResponse(BaseModel):
    """Response for autocomplete suggestions."""

    suggestions: List[str] = Field(..., description="List of suggested completions")
    context: Optional[str] = Field(None, description="Context used for suggestions")


class TemplateInfo(BaseModel):
    """Template metadata."""

    name: str = Field(..., description="Template name")
    display_name: str = Field(..., description="Human-readable template name")
    description: str = Field(..., description="Template description")
    sections: List[str] = Field(..., description="Available sections")
    is_custom: bool = Field(
        default=False, description="Whether this is a custom template"
    )


class TemplateRequest(BaseModel):
    """Request to create or update a template."""

    name: str = Field(..., description="Template name")
    display_name: str = Field(..., description="Human-readable template name")
    description: str = Field(..., description="Template description")
    template_content: str = Field(..., description="Jinja2 template content")
    sections: List[str] = Field(..., description="Available sections")


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Detailed error information")
    code: Optional[str] = Field(None, description="Error code")


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(..., description="Service status")
    timestamp: datetime = Field(default_factory=datetime.now)
    version: str = Field(..., description="API version")
    services: Dict[str, str] = Field(..., description="Status of dependent services")
