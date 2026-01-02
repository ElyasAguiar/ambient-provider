# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Repository for Session operations."""
from typing import List, Optional
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ambient_scribe.models import database as db_models


class SessionRepository:
    """Repository for Session operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        workspace_id: UUID,
        name: str,
        context_id: Optional[UUID] = None,
        status: str = "active",
        session_metadata: Optional[dict] = None,
    ) -> db_models.Session:
        """Create a new session."""
        session = db_models.Session(
            workspace_id=workspace_id,
            context_id=context_id,
            name=name,
            status=status,
            session_metadata=session_metadata or {},
        )
        self.db.add(session)
        await self.db.flush()
        return session

    async def get_by_id(self, session_id: UUID) -> Optional[db_models.Session]:
        """Get session by ID."""
        result = await self.db.execute(
            select(db_models.Session)
            .options(
                selectinload(db_models.Session.transcripts),
                selectinload(db_models.Session.context),
            )
            .where(db_models.Session.id == session_id)
        )
        return result.scalar_one_or_none()

    async def list_by_workspace(
        self, workspace_id: UUID, status: Optional[str] = None
    ) -> List[db_models.Session]:
        """List all sessions in a workspace."""
        query = select(db_models.Session).where(db_models.Session.workspace_id == workspace_id)

        if status:
            query = query.where(db_models.Session.status == status)

        query = query.order_by(desc(db_models.Session.updated_at))
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_status(self, session_id: UUID, status: str) -> Optional[db_models.Session]:
        """Update session status."""
        session = await self.get_by_id(session_id)
        if session:
            session.status = status
            await self.db.flush()
        return session

    async def delete(self, session_id: UUID) -> bool:
        """Delete a session."""
        session = await self.get_by_id(session_id)
        if session:
            await self.db.delete(session)
            return True
        return False
