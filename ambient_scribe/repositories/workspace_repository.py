# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Repository for Workspace operations."""
from typing import List, Optional
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ambient_scribe.models import database as db_models


class WorkspaceRepository:
    """Repository for Workspace operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        name: str,
        owner_id: UUID,
        description: Optional[str] = None,
        is_default: bool = False,
    ) -> db_models.Workspace:
        """Create a new workspace."""
        workspace = db_models.Workspace(
            name=name,
            owner_id=owner_id,
            description=description,
            is_default=is_default,
        )
        self.db.add(workspace)
        await self.db.flush()
        return workspace

    async def get_by_id(self, workspace_id: UUID) -> Optional[db_models.Workspace]:
        """Get workspace by ID."""
        result = await self.db.execute(
            select(db_models.Workspace)
            .options(selectinload(db_models.Workspace.sessions))
            .where(db_models.Workspace.id == workspace_id)
        )
        return result.scalar_one_or_none()

    async def list_by_owner(self, owner_id: UUID) -> List[db_models.Workspace]:
        """List all workspaces for a user."""
        result = await self.db.execute(
            select(db_models.Workspace)
            .where(db_models.Workspace.owner_id == owner_id)
            .order_by(desc(db_models.Workspace.updated_at))
        )
        return list(result.scalars().all())

    async def delete(self, workspace_id: UUID) -> bool:
        """Delete a workspace."""
        workspace = await self.get_by_id(workspace_id)
        if workspace:
            await self.db.delete(workspace)
            return True
        return False
