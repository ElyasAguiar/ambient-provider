# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Public API for Pydantic schemas."""
from ambient_scribe.models.api.common_schema import ErrorResponse, HealthResponse
from ambient_scribe.models.api.notes_schema import (
    Citation,
    NoteRequest,
    NoteResponse,
    SuggestionResponse,
    TraceEvent,
)
from ambient_scribe.models.api.templates_schema import TemplateInfo, TemplateRequest
from ambient_scribe.models.api.transcripts_schema import Transcript, TranscriptSegment

__all__ = [
    # Transcripts
    "TranscriptSegment",
    "Transcript",
    # Notes
    "NoteRequest",
    "Citation",
    "TraceEvent",
    "NoteResponse",
    "SuggestionResponse",
    # Templates
    "TemplateInfo",
    "TemplateRequest",
    # Common
    "ErrorResponse",
    "HealthResponse",
]
