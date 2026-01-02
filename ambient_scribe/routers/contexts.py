# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Contexts router for managing transcription domains."""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ambient_scribe.database import get_db
from ambient_scribe.middleware.auth import get_current_active_user
from ambient_scribe.models.database.users_model import User
from ambient_scribe.repositories import ContextRatingRepository, TemplateRepository
from ambient_scribe.services.domain_manager import DomainManager

router = APIRouter(prefix="/api/contexts", tags=["contexts"])


class ContextCreate(BaseModel):
    """Context creation request."""

    name: str
    description: str
    language: str = "pt-BR"
    speaker_labels: dict = {}
    word_boosting_config: dict = {}
    is_public: bool = False
    icon: Optional[str] = None


class ContextUpdate(BaseModel):
    """Context update request."""

    name: Optional[str] = None
    description: Optional[str] = None
    language: Optional[str] = None
    speaker_labels: Optional[dict] = None
    word_boosting_config: Optional[dict] = None
    icon: Optional[str] = None


class ContextResponse(BaseModel):
    """Context response."""

    id: str
    name: str
    description: str
    language: str
    speaker_labels: dict
    word_boosting_config: dict
    is_public: bool
    is_system: bool
    icon: Optional[str]
    owner_id: str
    created_at: str
    updated_at: str
    templates_count: int = 0
    average_rating: Optional[float] = None
    ratings_count: int = 0


class RatingCreate(BaseModel):
    """Rating creation request."""

    rating: int  # 1-5
    comment: Optional[str] = None


@router.post("/", response_model=ContextResponse, status_code=status.HTTP_201_CREATED)
async def create_context(
    context_data: ContextCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new context."""
    domain_manager = DomainManager(db)

    context = await domain_manager.create_context(
        name=context_data.name,
        description=context_data.description,
        owner_id=current_user.id,
        language=context_data.language,
        speaker_labels=context_data.speaker_labels,
        word_boosting_config=context_data.word_boosting_config,
        is_public=context_data.is_public,
        icon=context_data.icon,
    )

    await db.commit()

    return ContextResponse(
        id=str(context.id),
        name=context.name,
        description=context.description,
        language=context.language,
        speaker_labels=context.speaker_labels,
        word_boosting_config=context.word_boosting_config,
        is_public=context.is_public,
        is_system=context.is_system,
        icon=context.icon,
        owner_id=str(context.owner_id),
        created_at=context.created_at.isoformat(),
        updated_at=context.updated_at.isoformat(),
        templates_count=len(context.templates) if context.templates else 0,
    )


@router.get("/", response_model=List[ContextResponse])
async def list_contexts(
    include_system: bool = True,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """List all contexts available to the current user."""
    domain_manager = DomainManager(db)
    contexts = await domain_manager.list_contexts(
        owner_id=current_user.id, include_system=include_system
    )

    # Get template counts and ratings
    template_repo = TemplateRepository(db)
    rating_repo = ContextRatingRepository(db)

    result = []
    for context in contexts:
        templates = await template_repo.list_by_context(context.id)
        avg_rating = await rating_repo.get_average_rating(context.id)
        rating_count = await rating_repo.get_rating_count(context.id)

        result.append(
            ContextResponse(
                id=str(context.id),
                name=context.name,
                description=context.description,
                language=context.language,
                speaker_labels=context.speaker_labels,
                word_boosting_config=context.word_boosting_config,
                is_public=context.is_public,
                is_system=context.is_system,
                icon=context.icon,
                owner_id=str(context.owner_id),
                created_at=context.created_at.isoformat(),
                updated_at=context.updated_at.isoformat(),
                templates_count=len(templates),
                average_rating=float(avg_rating) if avg_rating else None,
                ratings_count=rating_count,
            )
        )

    return result


@router.get("/public", response_model=List[ContextResponse])
async def list_public_contexts(
    limit: int = 50,
    offset: int = 0,
    sort_by: str = "recent",
    db: AsyncSession = Depends(get_db),
):
    """List publicly shared contexts."""
    domain_manager = DomainManager(db)
    contexts = await domain_manager.list_public_contexts(
        limit=limit, offset=offset, sort_by=sort_by
    )

    # Get template counts and ratings
    template_repo = TemplateRepository(db)
    rating_repo = ContextRatingRepository(db)

    result = []
    for context in contexts:
        templates = await template_repo.list_by_context(context.id)
        avg_rating = await rating_repo.get_average_rating(context.id)
        rating_count = await rating_repo.get_rating_count(context.id)

        result.append(
            ContextResponse(
                id=str(context.id),
                name=context.name,
                description=context.description,
                language=context.language,
                speaker_labels=context.speaker_labels,
                word_boosting_config=context.word_boosting_config,
                is_public=context.is_public,
                is_system=context.is_system,
                icon=context.icon,
                owner_id=str(context.owner_id),
                created_at=context.created_at.isoformat(),
                updated_at=context.updated_at.isoformat(),
                templates_count=len(templates),
                average_rating=float(avg_rating) if avg_rating else None,
                ratings_count=rating_count,
            )
        )

    return result


@router.get("/{context_id}", response_model=ContextResponse)
async def get_context(
    context_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific context by ID."""
    domain_manager = DomainManager(db)
    context = await domain_manager.get_context(context_id)

    if not context:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Context not found",
        )

    # Check authorization (only owner or if public/system)
    if context.owner_id != current_user.id and not context.is_public and not context.is_system:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this context",
        )

    # Get template count and ratings
    template_repo = TemplateRepository(db)
    rating_repo = ContextRatingRepository(db)

    templates = await template_repo.list_by_context(context.id)
    avg_rating = await rating_repo.get_average_rating(context.id)
    rating_count = await rating_repo.get_rating_count(context.id)

    return ContextResponse(
        id=str(context.id),
        name=context.name,
        description=context.description,
        language=context.language,
        speaker_labels=context.speaker_labels,
        word_boosting_config=context.word_boosting_config,
        is_public=context.is_public,
        is_system=context.is_system,
        icon=context.icon,
        owner_id=str(context.owner_id),
        created_at=context.created_at.isoformat(),
        updated_at=context.updated_at.isoformat(),
        templates_count=len(templates),
        average_rating=float(avg_rating) if avg_rating else None,
        ratings_count=rating_count,
    )


@router.put("/{context_id}", response_model=ContextResponse)
async def update_context(
    context_id: UUID,
    context_data: ContextUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a context."""
    domain_manager = DomainManager(db)
    context = await domain_manager.get_context(context_id)

    if not context:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Context not found",
        )

    # Check authorization
    if context.owner_id != current_user.id or context.is_system:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this context",
        )

    # Update only provided fields
    update_data = context_data.model_dump(exclude_unset=True)
    updated_context = await domain_manager.update_context(context_id, **update_data)

    await db.commit()

    if not updated_context:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Context not found after update",
        )

    return ContextResponse(
        id=str(updated_context.id),
        name=updated_context.name,
        description=updated_context.description,
        language=updated_context.language,
        speaker_labels=updated_context.speaker_labels,
        word_boosting_config=updated_context.word_boosting_config,
        is_public=updated_context.is_public,
        is_system=updated_context.is_system,
        icon=updated_context.icon,
        owner_id=str(updated_context.owner_id),
        created_at=updated_context.created_at.isoformat(),
        updated_at=updated_context.updated_at.isoformat(),
    )


@router.delete("/{context_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_context(
    context_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a context."""
    domain_manager = DomainManager(db)
    context = await domain_manager.get_context(context_id)

    if not context:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Context not found",
        )

    # Check authorization
    if context.owner_id != current_user.id or context.is_system:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this context",
        )

    success = await domain_manager.delete_context(context_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Context not found",
        )

    await db.commit()


@router.post("/{context_id}/publish", status_code=status.HTTP_200_OK)
async def publish_context(
    context_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Publish a context to make it publicly accessible."""
    domain_manager = DomainManager(db)

    success = await domain_manager.publish_context(context_id, current_user.id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot publish this context (not authorized, missing data, or is system context)",
        )

    await db.commit()

    return {"message": "Context published successfully"}


@router.post("/{context_id}/unpublish", status_code=status.HTTP_200_OK)
async def unpublish_context(
    context_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Unpublish a context to make it private again."""
    domain_manager = DomainManager(db)

    success = await domain_manager.unpublish_context(context_id, current_user.id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot unpublish this context (not authorized or is system context)",
        )

    await db.commit()

    return {"message": "Context unpublished successfully"}


@router.post(
    "/{context_id}/clone",
    response_model=ContextResponse,
    status_code=status.HTTP_201_CREATED,
)
async def clone_context(
    context_id: UUID,
    new_name: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Clone a public context to user's private workspace."""
    domain_manager = DomainManager(db)

    cloned_context = await domain_manager.clone_public_context(
        context_id, current_user.id, new_name
    )

    if not cloned_context:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Context not found or not public",
        )

    await db.commit()

    return ContextResponse(
        id=str(cloned_context.id),
        name=cloned_context.name,
        description=cloned_context.description,
        language=cloned_context.language,
        speaker_labels=cloned_context.speaker_labels,
        word_boosting_config=cloned_context.word_boosting_config,
        is_public=cloned_context.is_public,
        is_system=cloned_context.is_system,
        icon=cloned_context.icon,
        owner_id=str(cloned_context.owner_id),
        created_at=cloned_context.created_at.isoformat(),
        updated_at=cloned_context.updated_at.isoformat(),
    )


@router.post("/{context_id}/rate", status_code=status.HTTP_201_CREATED)
async def rate_context(
    context_id: UUID,
    rating_data: RatingCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Rate a public context."""
    if rating_data.rating < 1 or rating_data.rating > 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rating must be between 1 and 5",
        )

    domain_manager = DomainManager(db)
    context = await domain_manager.get_context(context_id)

    if not context or not context.is_public:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Public context not found",
        )

    rating_repo = ContextRatingRepository(db)
    await rating_repo.create_or_update(
        context_id=context_id,
        user_id=current_user.id,
        rating=rating_data.rating,
        comment=rating_data.comment,
    )

    await db.commit()

    return {"message": "Rating submitted successfully"}
