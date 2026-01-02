# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Repository for ContextRating operations."""
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ambient_scribe.models import database as db_models


class ContextRatingRepository:
    """Repository for ContextRating operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_or_update(
        self,
        context_id: UUID,
        user_id: UUID,
        rating: int,
        comment: Optional[str] = None,
    ) -> db_models.ContextRating:
        """Create or update a context rating."""
        # Check if rating already exists
        result = await self.db.execute(
            select(db_models.ContextRating).where(
                and_(
                    db_models.ContextRating.context_id == context_id,
                    db_models.ContextRating.user_id == user_id,
                )
            )
        )
        existing_rating = result.scalar_one_or_none()

        if existing_rating:
            existing_rating.rating = rating
            existing_rating.comment = comment
            await self.db.flush()
            return existing_rating
        else:
            new_rating = db_models.ContextRating(
                context_id=context_id,
                user_id=user_id,
                rating=rating,
                comment=comment,
            )
            self.db.add(new_rating)
            await self.db.flush()
            return new_rating

    async def get_average_rating(self, context_id: UUID) -> Optional[float]:
        """Get average rating for a context."""
        result = await self.db.execute(
            select(func.avg(db_models.ContextRating.rating)).where(
                db_models.ContextRating.context_id == context_id
            )
        )
        return result.scalar_one_or_none()

    async def get_rating_count(self, context_id: UUID) -> int:
        """Get number of ratings for a context."""
        result = await self.db.execute(
            select(func.count(db_models.ContextRating.id)).where(
                db_models.ContextRating.context_id == context_id
            )
        )
        return result.scalar_one() or 0
