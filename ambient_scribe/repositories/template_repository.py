# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Repository for Template operations."""
from typing import List, Optional
from uuid import UUID

from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ambient_scribe.models import database as db_models


class TemplateRepository:
    """Repository for Template operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        context_id: UUID,
        name: str,
        display_name: str,
        description: str,
        content: str,
        sections: List[str],
        created_by: UUID,
        is_default: bool = False,
        is_public: bool = False,
    ) -> db_models.Template:
        """Create a new template."""
        template = db_models.Template(
            context_id=context_id,
            name=name,
            display_name=display_name,
            description=description,
            content=content,
            sections=sections,
            created_by=created_by,
            is_default=is_default,
            is_public=is_public,
        )
        self.db.add(template)
        await self.db.flush()
        return template

    async def get_by_id(self, template_id: UUID) -> Optional[db_models.Template]:
        """Get template by ID."""
        result = await self.db.execute(
            select(db_models.Template).where(db_models.Template.id == template_id)
        )
        return result.scalar_one_or_none()

    async def list_by_context(self, context_id: UUID) -> List[db_models.Template]:
        """List all templates for a context."""
        result = await self.db.execute(
            select(db_models.Template)
            .where(db_models.Template.context_id == context_id)
            .order_by(desc(db_models.Template.is_default), db_models.Template.name)
        )
        return list(result.scalars().all())

    async def get_default_for_context(self, context_id: UUID) -> Optional[db_models.Template]:
        """Get the default template for a context."""
        result = await self.db.execute(
            select(db_models.Template).where(
                and_(
                    db_models.Template.context_id == context_id,
                    db_models.Template.is_default == True,
                )
            )
        )
        return result.scalar_one_or_none()

    async def delete(self, template_id: UUID) -> bool:
        """Delete a template."""
        template = await self.get_by_id(template_id)
        if template:
            await self.db.delete(template)
            return True
        return False
