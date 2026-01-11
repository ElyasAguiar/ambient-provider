# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Repository for Transcript operations."""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ambient_scribe.models import database as db_models


class TranscriptRepository:
    """Repository for Transcript CRUD operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        filename: str,
        audio_key: str,
        language: str = "en-US",
        session_id: Optional[UUID] = None,
    ) -> db_models.Transcript:
        """
        Create a new transcript record.

        Args:
            filename: Original audio filename
            audio_key: S3 object key (permanent path) to audio file
            language: Audio language
            session_id: Optional associated session ID

        Returns:
            Created Transcript instance
        """
        transcript = db_models.Transcript(
            session_id=session_id,
            filename=filename,
            audio_key=audio_key,
            language=language,
            status="processing",
            segments=[],
        )
        self.db.add(transcript)
        await self.db.flush()
        await self.db.refresh(transcript)
        return transcript

    async def get_by_id(self, transcript_id: UUID) -> Optional[db_models.Transcript]:
        """
        Get transcript by ID.

        Args:
            transcript_id: Transcript UUID

        Returns:
            Transcript instance or None
        """
        result = await self.db.execute(
            select(db_models.Transcript)
            .options(selectinload(db_models.Transcript.job))
            .where(db_models.Transcript.id == transcript_id)
        )
        return result.scalar_one_or_none()

    async def get_by_session(self, session_id: UUID) -> List[db_models.Transcript]:
        """
        Get all completed transcripts for a session.

        Args:
            session_id: Session UUID

        Returns:
            List of completed Transcript instances
        """
        result = await self.db.execute(
            select(db_models.Transcript)
            .where(
                db_models.Transcript.session_id == session_id,
                db_models.Transcript.status == "completed",
            )
            .order_by(db_models.Transcript.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_status(
        self,
        transcript_id: UUID,
        status: str,
        error_message: Optional[str] = None,
    ) -> Optional[db_models.Transcript]:
        """
        Update transcript status.

        Args:
            transcript_id: Transcript UUID
            status: New status (processing, completed, failed)
            error_message: Optional error message for failed status

        Returns:
            Updated Transcript instance or None
        """
        transcript = await self.get_by_id(transcript_id)
        if transcript:
            transcript.status = status
            if error_message:
                transcript.error_message = error_message
            await self.db.flush()
            await self.db.refresh(transcript)
        return transcript

    async def update_segments(
        self,
        transcript_id: UUID,
        segments: List[dict],
        duration: Optional[float] = None,
        speaker_roles: Optional[dict] = None,
    ) -> Optional[db_models.Transcript]:
        """
        Update transcript segments and metadata.

        Args:
            transcript_id: Transcript UUID
            segments: List of transcript segments
            duration: Optional audio duration
            speaker_roles: Optional speaker role mapping

        Returns:
            Updated Transcript instance or None
        """
        transcript = await self.get_by_id(transcript_id)
        if transcript:
            transcript.segments = segments
            if duration is not None:
                transcript.duration = duration
            if speaker_roles is not None:
                transcript.speaker_roles = speaker_roles
            transcript.status = "completed"
            await self.db.flush()
            await self.db.refresh(transcript)
        return transcript

    async def delete(self, transcript_id: UUID) -> bool:
        """
        Delete transcript by ID.

        Args:
            transcript_id: Transcript UUID

        Returns:
            True if deleted, False if not found
        """
        transcript = await self.get_by_id(transcript_id)
        if transcript:
            await self.db.delete(transcript)
            await self.db.flush()
            return True
        return False

    async def list_all(self, limit: int = 100, offset: int = 0) -> List[db_models.Transcript]:
        """
        List all completed transcripts with pagination.

        Args:
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of completed Transcript instances
        """
        result = await self.db.execute(
            select(db_models.Transcript)
            .where(db_models.Transcript.status == "completed")
            .order_by(db_models.Transcript.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
