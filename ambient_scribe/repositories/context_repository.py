# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Repository for Context operations."""
from typing import List, Optional
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ambient_scribe.models import database as db_models


class ContextRepository:
    """Repository for Context operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        name: str,
        description: str,
        owner_id: UUID,
        language: str = "pt-BR",
        speaker_labels: Optional[dict] = None,
        word_boosting_config: Optional[dict] = None,
        is_public: bool = False,
        is_system: bool = False,
        icon: Optional[str] = None,
    ) -> db_models.Context:
        """Create a new context."""
        context = db_models.Context(
            name=name,
            description=description,
            owner_id=owner_id,
            language=language,
            speaker_labels=speaker_labels or {},
            word_boosting_config=word_boosting_config or {},
            is_public=is_public,
            is_system=is_system,
            icon=icon,
        )
        self.db.add(context)
        await self.db.flush()
        return context

    async def get_by_id(self, context_id: UUID) -> Optional[db_models.Context]:
        """Get context by ID."""
        result = await self.db.execute(
            select(db_models.Context)
            .options(
                selectinload(db_models.Context.templates),
                selectinload(db_models.Context.ratings),
            )
            .where(db_models.Context.id == context_id)
        )
        return result.scalar_one_or_none()

    async def list_by_owner(self, owner_id: UUID) -> List[db_models.Context]:
        """List all contexts owned by a user."""
        result = await self.db.execute(
            select(db_models.Context)
            .where(db_models.Context.owner_id == owner_id)
            .order_by(desc(db_models.Context.updated_at))
        )
        return list(result.scalars().all())

    async def list_public(
        self, limit: int = 50, offset: int = 0, sort_by: str = "recent"
    ) -> List[db_models.Context]:
        """List public contexts."""
        query = select(db_models.Context).where(db_models.Context.is_public == True)

        if sort_by == "rating":
            # Join with ratings and sort by average rating
            query = (
                query.outerjoin(db_models.ContextRating)
                .group_by(db_models.Context.id)
                .order_by(desc(func.avg(db_models.ContextRating.rating)))
            )
        else:  # recent
            query = query.order_by(desc(db_models.Context.created_at))

        query = query.limit(limit).offset(offset)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def list_system(self) -> List[db_models.Context]:
        """List system contexts."""
        result = await self.db.execute(
            select(db_models.Context)
            .where(db_models.Context.is_system == True)
            .order_by(db_models.Context.name)
        )
        return list(result.scalars().all())

    async def update(
        self,
        context_id: UUID,
        **kwargs,
    ) -> Optional[db_models.Context]:
        """Update a context."""
        context = await self.get_by_id(context_id)
        if context:
            for key, value in kwargs.items():
                if hasattr(context, key):
                    setattr(context, key, value)
            await self.db.flush()
        return context

    async def delete(self, context_id: UUID) -> bool:
        """Delete a context."""
        context = await self.get_by_id(context_id)
        if context:
            await self.db.delete(context)
            return True
        return False
