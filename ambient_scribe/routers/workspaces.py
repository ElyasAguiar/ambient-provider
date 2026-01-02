# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Workspaces router for organizing sessions."""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ambient_scribe.database import get_db
from ambient_scribe.middleware.auth import get_current_active_user
from ambient_scribe.models.database.users_model import User
from ambient_scribe.repositories import SessionRepository, WorkspaceRepository

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


class WorkspaceCreate(BaseModel):
    """Workspace creation request."""

    name: str
    description: Optional[str] = None


class WorkspaceUpdate(BaseModel):
    """Workspace update request."""

    name: Optional[str] = None
    description: Optional[str] = None


class WorkspaceResponse(BaseModel):
    """Workspace response."""

    id: str
    name: str
    description: Optional[str]
    is_default: bool
    owner_id: str
    sessions_count: int = 0
    created_at: str
    updated_at: str


class SessionCreate(BaseModel):
    """Session creation request."""

    name: str
    context_id: Optional[str] = None
    session_metadata: Optional[dict] = None


class SessionResponse(BaseModel):
    """Session response."""

    id: str
    workspace_id: str
    context_id: Optional[str]
    name: str
    status: str
    session_metadata: Optional[dict]
    created_at: str
    updated_at: str


@router.post("/", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    workspace_data: WorkspaceCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new workspace."""
    workspace_repo = WorkspaceRepository(db)

    workspace = await workspace_repo.create(
        name=workspace_data.name,
        owner_id=current_user.id,
        description=workspace_data.description,
    )

    await db.commit()

    return WorkspaceResponse(
        id=str(workspace.id),
        name=workspace.name,
        description=workspace.description,
        is_default=workspace.is_default,
        owner_id=str(workspace.owner_id),
        created_at=workspace.created_at.isoformat(),
        updated_at=workspace.updated_at.isoformat(),
    )


@router.get("/", response_model=List[WorkspaceResponse])
async def list_workspaces(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """List all workspaces for the current user."""
    workspace_repo = WorkspaceRepository(db)
    session_repo = SessionRepository(db)

    workspaces = await workspace_repo.list_by_owner(current_user.id)

    result = []
    for workspace in workspaces:
        sessions = await session_repo.list_by_workspace(workspace.id)
        result.append(
            WorkspaceResponse(
                id=str(workspace.id),
                name=workspace.name,
                description=workspace.description,
                is_default=workspace.is_default,
                owner_id=str(workspace.owner_id),
                sessions_count=len(sessions),
                created_at=workspace.created_at.isoformat(),
                updated_at=workspace.updated_at.isoformat(),
            )
        )

    return result


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific workspace."""
    workspace_repo = WorkspaceRepository(db)
    workspace = await workspace_repo.get_by_id(workspace_id)

    if not workspace or workspace.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )

    session_repo = SessionRepository(db)
    sessions = await session_repo.list_by_workspace(workspace.id)

    return WorkspaceResponse(
        id=str(workspace.id),
        name=workspace.name,
        description=workspace.description,
        is_default=workspace.is_default,
        owner_id=str(workspace.owner_id),
        sessions_count=len(sessions),
        created_at=workspace.created_at.isoformat(),
        updated_at=workspace.updated_at.isoformat(),
    )


@router.get("/{workspace_id}/sessions", response_model=List[SessionResponse])
async def list_workspace_sessions(
    workspace_id: UUID,
    status_filter: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """List all sessions in a workspace."""
    workspace_repo = WorkspaceRepository(db)
    workspace = await workspace_repo.get_by_id(workspace_id)

    if not workspace or workspace.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )

    session_repo = SessionRepository(db)
    sessions = await session_repo.list_by_workspace(workspace_id, status_filter)

    return [
        SessionResponse(
            id=str(session.id),
            workspace_id=str(session.workspace_id),
            context_id=str(session.context_id) if session.context_id else None,
            name=session.name,
            status=session.status,
            session_metadata=session.session_metadata,
            created_at=session.created_at.isoformat(),
            updated_at=session.updated_at.isoformat(),
        )
        for session in sessions
    ]


@router.post(
    "/{workspace_id}/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    workspace_id: UUID,
    session_data: SessionCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new session in a workspace."""
    workspace_repo = WorkspaceRepository(db)
    workspace = await workspace_repo.get_by_id(workspace_id)

    if not workspace or workspace.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )

    session_repo = SessionRepository(db)
    context_uuid = UUID(session_data.context_id) if session_data.context_id else None

    session = await session_repo.create(
        workspace_id=workspace_id,
        name=session_data.name,
        context_id=context_uuid,
        session_metadata=session_data.session_metadata,
    )

    await db.commit()

    return SessionResponse(
        id=str(session.id),
        workspace_id=str(session.workspace_id),
        context_id=str(session.context_id) if session.context_id else None,
        name=session.name,
        status=session.status,
        session_metadata=session.session_metadata,
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
    )
