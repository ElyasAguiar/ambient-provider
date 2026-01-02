# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Repository for Note operations."""
from typing import List, Optional
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ambient_scribe.models import database as db_models


class NoteRepository:
    """Repository for Note operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        transcript_id: UUID,
        template_id: Optional[UUID],
        title: str,
        content: str,
        markdown_content: str,
        citations: Optional[List] = None,
        trace_events: Optional[List] = None,
        status: str = "generating",
    ) -> db_models.Note:
        """Create a new note."""
        note = db_models.Note(
            transcript_id=transcript_id,
            template_id=template_id,
            title=title,
            content=content,
            markdown_content=markdown_content,
            citations=citations or [],
            trace_events=trace_events or [],
            status=status,
        )
        self.db.add(note)
        await self.db.flush()
        return note

    async def get_by_id(self, note_id: UUID) -> Optional[db_models.Note]:
        """Get note by ID."""
        result = await self.db.execute(
            select(db_models.Note)
            .options(
                selectinload(db_models.Note.transcript),
                selectinload(db_models.Note.template),
            )
            .where(db_models.Note.id == note_id)
        )
        return result.scalar_one_or_none()

    async def list_by_transcript(self, transcript_id: UUID) -> List[db_models.Note]:
        """List all notes for a transcript."""
        result = await self.db.execute(
            select(db_models.Note)
            .where(db_models.Note.transcript_id == transcript_id)
            .order_by(desc(db_models.Note.created_at))
        )
        return list(result.scalars().all())

    async def update_status(
        self,
        note_id: UUID,
        status: str,
        content: Optional[str] = None,
        markdown_content: Optional[str] = None,
    ) -> Optional[db_models.Note]:
        """Update note status and content."""
        note = await self.get_by_id(note_id)
        if note:
            note.status = status
            if content is not None:
                note.content = content
            if markdown_content is not None:
                note.markdown_content = markdown_content
            await self.db.flush()
        return note

    async def delete(self, note_id: UUID) -> bool:
        """Delete a note."""
        note = await self.get_by_id(note_id)
        if note:
            await self.db.delete(note)
            return True
        return False
