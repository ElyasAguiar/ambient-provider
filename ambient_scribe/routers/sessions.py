# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Sessions router for managing sessions and their transcriptions."""
import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ambient_scribe.database import get_db
from ambient_scribe.middleware.auth import get_current_active_user
from ambient_scribe.models import database as db_models
from ambient_scribe.models.database.users_model import User
from ambient_scribe.repositories import SessionRepository, TranscriptRepository
from ambient_scribe.services.storage import S3StorageManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def get_storage_manager(request: Request) -> S3StorageManager:
    """Get storage manager from app state."""
    return request.app.state.storage_manager


class TranscriptionSegmentResponse(BaseModel):
    """Transcription segment response."""

    start: float = Field(..., description="Start time in seconds")
    end: float = Field(..., description="End time in seconds")
    text: str = Field(..., description="Transcribed text")
    speaker_tag: Optional[int] = Field(None, description="Speaker identifier")
    confidence: Optional[float] = Field(None, description="Confidence score 0-1")


class TranscriptionResponse(BaseModel):
    """Transcription response."""

    id: str
    session_id: str
    filename: str
    audio_url: str
    language: str
    duration: Optional[float]
    segments: List[TranscriptionSegmentResponse]
    speaker_roles: Optional[dict]
    status: str
    error_message: Optional[str]
    created_at: str
    updated_at: str


class TranscriptionCreate(BaseModel):
    """Transcription creation request."""

    filename: str
    audio_key: str
    language: str = "en-US"


class TranscriptionUpdate(BaseModel):
    """Transcription update request."""

    segments: Optional[List[TranscriptionSegmentResponse]] = None
    speaker_roles: Optional[dict] = None
    status: Optional[str] = None
    duration: Optional[float] = None


async def verify_session_access(
    session_id: UUID,
    current_user: User,
    db: AsyncSession,
) -> db_models.Session:
    """Verify user has access to session."""
    session_repo = SessionRepository(db)
    session = await session_repo.get_by_id(session_id)

    if not session or session.workspace.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    return session


@router.get("/{session_id}/transcriptions", response_model=List[TranscriptionResponse])
async def list_transcriptions(
    session_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    storage: S3StorageManager = Depends(get_storage_manager),
):
    """List all transcriptions for a session."""
    session = await verify_session_access(session_id, current_user, db)

    transcript_repo = TranscriptRepository(db)
    transcripts = await transcript_repo.get_by_session(session.id)

    return [
        TranscriptionResponse(
            id=str(transcript.id),
            session_id=str(transcript.session_id),
            filename=transcript.filename,
            audio_url=storage.generate_presigned_url(transcript.audio_key, expiration=3600),
            language=transcript.language,
            duration=transcript.duration,
            segments=[
                TranscriptionSegmentResponse(
                    start=seg.get("start", 0),
                    end=seg.get("end", 0),
                    text=seg.get("text", ""),
                    speaker_tag=seg.get("speaker_tag"),
                    confidence=seg.get("confidence"),
                )
                for seg in transcript.segments
            ],
            speaker_roles=transcript.speaker_roles,
            status=transcript.status,
            error_message=transcript.error_message,
            created_at=transcript.created_at.isoformat(),
            updated_at=transcript.updated_at.isoformat(),
        )
        for transcript in transcripts
    ]


@router.post(
    "/{session_id}/transcriptions",
    response_model=TranscriptionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_transcription(
    session_id: UUID,
    transcription_data: TranscriptionCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    storage: S3StorageManager = Depends(get_storage_manager),
):
    """Create a new transcription for a session."""
    session = await verify_session_access(session_id, current_user, db)
    logger.info(f"Creating transcription for session {session.id}")

    transcript_repo = TranscriptRepository(db)
    transcript = await transcript_repo.create(
        filename=transcription_data.filename,
        audio_key=transcription_data.audio_key,
        language=transcription_data.language,
        session_id=session.id,
    )

    await db.commit()
    await db.refresh(transcript)

    return TranscriptionResponse(
        id=str(transcript.id),
        session_id=str(transcript.session_id),
        filename=transcript.filename,
        audio_url=storage.generate_presigned_url(transcript.audio_key, expiration=3600),
        language=transcript.language,
        duration=transcript.duration,
        segments=[],
        speaker_roles=transcript.speaker_roles,
        status=transcript.status,
        error_message=transcript.error_message,
        created_at=transcript.created_at.isoformat(),
        updated_at=transcript.updated_at.isoformat(),
    )


@router.get(
    "/{session_id}/transcriptions/{transcription_id}",
    response_model=TranscriptionResponse,
)
async def get_transcription(
    session_id: UUID,
    transcription_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    storage: S3StorageManager = Depends(get_storage_manager),
):
    """Get a specific transcription."""
    session = await verify_session_access(session_id, current_user, db)

    transcript_repo = TranscriptRepository(db)
    transcript = await transcript_repo.get_by_id(transcription_id)

    if not transcript or transcript.session_id != session.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transcription not found",
        )

    return TranscriptionResponse(
        id=str(transcript.id),
        session_id=str(transcript.session_id),
        filename=transcript.filename,
        audio_url=storage.generate_presigned_url(transcript.audio_key, expiration=3600),
        language=transcript.language,
        duration=transcript.duration,
        segments=[
            TranscriptionSegmentResponse(
                start=seg.get("start", 0),
                end=seg.get("end", 0),
                text=seg.get("text", ""),
                speaker_tag=seg.get("speaker_tag"),
                confidence=seg.get("confidence"),
            )
            for seg in transcript.segments
        ],
        speaker_roles=transcript.speaker_roles,
        status=transcript.status,
        error_message=transcript.error_message,
        created_at=transcript.created_at.isoformat(),
        updated_at=transcript.updated_at.isoformat(),
    )


@router.patch(
    "/{session_id}/transcriptions/{transcription_id}",
    response_model=TranscriptionResponse,
)
async def update_transcription(
    session_id: UUID,
    transcription_id: UUID,
    transcription_data: TranscriptionUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    storage: S3StorageManager = Depends(get_storage_manager),
):
    """Update a transcription."""
    session = await verify_session_access(session_id, current_user, db)

    transcript_repo = TranscriptRepository(db)
    transcript = await transcript_repo.get_by_id(transcription_id)

    if not transcript or transcript.session_id != session.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transcription not found",
        )

    # Update fields if provided
    if transcription_data.segments is not None:
        transcript.segments = [
            {
                "start": seg.start,
                "end": seg.end,
                "text": seg.text,
                "speaker_tag": seg.speaker_tag,
                "confidence": seg.confidence,
            }
            for seg in transcription_data.segments
        ]

    if transcription_data.speaker_roles is not None:
        transcript.speaker_roles = transcription_data.speaker_roles

    if transcription_data.status is not None:
        transcript.status = transcription_data.status

    if transcription_data.duration is not None:
        transcript.duration = transcription_data.duration

    await db.commit()
    await db.refresh(transcript)

    return TranscriptionResponse(
        id=str(transcript.id),
        session_id=str(transcript.session_id),
        filename=transcript.filename,
        audio_url=storage.generate_presigned_url(transcript.audio_key, expiration=3600),
        language=transcript.language,
        duration=transcript.duration,
        segments=[
            TranscriptionSegmentResponse(
                start=seg.get("start", 0),
                end=seg.get("end", 0),
                text=seg.get("text", ""),
                speaker_tag=seg.get("speaker_tag"),
                confidence=seg.get("confidence"),
            )
            for seg in transcript.segments
        ],
        speaker_roles=transcript.speaker_roles,
        status=transcript.status,
        error_message=transcript.error_message,
        created_at=transcript.created_at.isoformat(),
        updated_at=transcript.updated_at.isoformat(),
    )
