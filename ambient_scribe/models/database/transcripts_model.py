# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Transcript and TranscriptJob SQLAlchemy models."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ambient_scribe.database import Base


class Transcript(Base):
    """Transcript model for audio transcriptions."""

    __tablename__ = "transcripts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    audio_key: Mapped[str] = mapped_column(String(500), nullable=False)
    language: Mapped[str] = mapped_column(String(10), default="en-US", nullable=False)
    duration: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    segments: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    speaker_roles: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("uploading", "processing", "completed", "failed", name="transcript_status"),
        default="processing",
        nullable=False,
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    session: Mapped[Optional["Session"]] = relationship("Session", back_populates="transcripts")
    notes: Mapped[list["Note"]] = relationship(
        "Note", back_populates="transcript", cascade="all, delete-orphan"
    )
    job: Mapped[Optional["TranscriptJob"]] = relationship(
        "TranscriptJob", back_populates="transcript", uselist=False, cascade="all, delete-orphan"
    )


class TranscriptJob(Base):
    """TranscriptJob model for tracking job processing metadata."""

    __tablename__ = "transcript_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transcript_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transcripts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    job_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    engine: Mapped[str] = mapped_column(
        Enum("asr", "whisperx", name="transcription_engine"),
        default="asr",
        nullable=False,
    )
    engine_params: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=dict)
    worker_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    transcript: Mapped["Transcript"] = relationship("Transcript", back_populates="job")
