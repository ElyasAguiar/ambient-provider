# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pydantic schemas for notes domain."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class NoteRequest(BaseModel):
    """Request to generate a medical note."""

    transcript_id: str = Field(..., description="ID of the transcript to use")
    template_name: str = Field(..., description="Template to use for note generation")
    custom_sections: Optional[List[str]] = Field(None, description="Custom sections to include")
    system_instructions: Optional[str] = Field(
        None, description="Additional instructions for the LLM"
    )
    include_traces: bool = Field(default=True, description="Whether to include reasoning traces")


class Citation(BaseModel):
    """Citation linking note content to transcript."""

    text: str = Field(..., description="Cited text")
    start_time: float = Field(..., description="Start time in transcript")
    end_time: float = Field(..., description="End time in transcript")
    segment_id: Optional[str] = Field(None, description="Reference to transcript segment")


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
    trace_events: List[TraceEvent] = Field(default_factory=list, description="Reasoning traces")
    citations: List[Citation] = Field(default_factory=list, description="Citations to transcript")
    template_used: str = Field(..., description="Template that was used")
    generation_time: float = Field(..., description="Time taken to generate note")
    created_at: datetime = Field(default_factory=datetime.now)
    transcript_id: Optional[str] = Field(None, description="ID of the transcript used")
    title: Optional[str] = Field(None, description="Display title for the note")


class SuggestionResponse(BaseModel):
    """Response for autocomplete suggestions."""

    suggestions: List[str] = Field(..., description="List of suggested completions")
    context: Optional[str] = Field(None, description="Context used for suggestions")
