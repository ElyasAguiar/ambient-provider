# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Repository pattern implementations for database access."""
from typing import List, Optional
from uuid import UUID

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ambient_scribe import db_models


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
