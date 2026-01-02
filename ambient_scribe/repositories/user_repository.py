# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Repository for User operations."""
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ambient_scribe.models import database as db_models


class UserRepository:
    """Repository for User operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        email: str,
        username: str,
        hashed_password: str,
        full_name: Optional[str] = None,
    ) -> db_models.User:
        """Create a new user."""
        user = db_models.User(
            email=email,
            username=username,
            hashed_password=hashed_password,
            full_name=full_name,
        )
        self.db.add(user)
        await self.db.flush()
        return user

    async def get_by_id(self, user_id: UUID) -> Optional[db_models.User]:
        """Get user by ID."""
        result = await self.db.execute(select(db_models.User).where(db_models.User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[db_models.User]:
        """Get user by email."""
        result = await self.db.execute(select(db_models.User).where(db_models.User.email == email))
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> Optional[db_models.User]:
        """Get user by username."""
        result = await self.db.execute(
            select(db_models.User).where(db_models.User.username == username)
        )
        return result.scalar_one_or_none()
