# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Domain/Context management service for ScribeHub."""
import logging
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ambient_scribe.models import database as db_models
from ambient_scribe.repositories import ContextRepository

logger = logging.getLogger(__name__)


class DomainManager:
    """
    Manages domains/contexts for transcription and note generation.

    A domain/context represents a specific use case (medical, aviation, legal, etc.)
    with its own terminology, templates, and configuration.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.context_repo = ContextRepository(db)

    async def get_context(self, context_id: UUID) -> Optional[db_models.Context]:
        """
        Get a context by ID.

        Args:
            context_id: UUID of the context

        Returns:
            Context object or None if not found
        """
        return await self.context_repo.get_by_id(context_id)

    async def list_contexts(
        self, owner_id: UUID, include_system: bool = True
    ) -> List[db_models.Context]:
        """
        List all contexts available to a user.

        Args:
            owner_id: UUID of the user
            include_system: Include system-provided contexts

        Returns:
            List of Context objects
        """
        user_contexts = await self.context_repo.list_by_owner(owner_id)

        if include_system:
            system_contexts = await self.context_repo.list_system()
            return system_contexts + user_contexts

        return user_contexts

    async def list_public_contexts(
        self, limit: int = 50, offset: int = 0, sort_by: str = "recent"
    ) -> List[db_models.Context]:
        """
        List publicly shared contexts.

        Args:
            limit: Maximum number of contexts to return
            offset: Offset for pagination
            sort_by: Sort order ('recent' or 'rating')

        Returns:
            List of public Context objects
        """
        return await self.context_repo.list_public(limit=limit, offset=offset, sort_by=sort_by)

    async def create_context(
        self,
        name: str,
        description: str,
        owner_id: UUID,
        language: str = "pt-BR",
        speaker_labels: Optional[Dict[str, str]] = None,
        word_boosting_config: Optional[Dict] = None,
        is_public: bool = False,
        icon: Optional[str] = None,
    ) -> db_models.Context:
        """
        Create a new context.

        Args:
            name: Context name
            description: Context description
            owner_id: UUID of the owner
            language: Language code (default: pt-BR)
            speaker_labels: Speaker label mappings (e.g., {"speaker_0": "Doctor"})
            word_boosting_config: Word boosting configuration
            is_public: Whether the context is publicly shareable
            icon: Icon identifier (optional)

        Returns:
            Created Context object
        """
        return await self.context_repo.create(
            name=name,
            description=description,
            owner_id=owner_id,
            language=language,
            speaker_labels=speaker_labels or {},
            word_boosting_config=word_boosting_config or {},
            is_public=is_public,
            is_system=False,
            icon=icon,
        )

    async def update_context(self, context_id: UUID, **kwargs) -> Optional[db_models.Context]:
        """
        Update a context.

        Args:
            context_id: UUID of the context
            **kwargs: Fields to update

        Returns:
            Updated Context object or None if not found
        """
        return await self.context_repo.update(context_id, **kwargs)

    async def delete_context(self, context_id: UUID) -> bool:
        """
        Delete a context.

        Args:
            context_id: UUID of the context

        Returns:
            True if deleted, False if not found
        """
        return await self.context_repo.delete(context_id)

    async def clone_public_context(
        self, context_id: UUID, new_owner_id: UUID, new_name: Optional[str] = None
    ) -> Optional[db_models.Context]:
        """
        Clone a public context to a user's private workspace.

        Args:
            context_id: UUID of the public context to clone
            new_owner_id: UUID of the new owner
            new_name: Optional new name (defaults to original name + " (Copy)")

        Returns:
            Cloned Context object or None if original not found
        """
        original = await self.context_repo.get_by_id(context_id)

        if not original or not original.is_public:
            return None

        cloned_name = new_name or f"{original.name} (Copy)"

        return await self.context_repo.create(
            name=cloned_name,
            description=original.description,
            owner_id=new_owner_id,
            language=original.language,
            speaker_labels=original.speaker_labels.copy(),
            word_boosting_config=original.word_boosting_config.copy(),
            is_public=False,
            is_system=False,
            icon=original.icon,
        )

    async def load_word_boosting_terms(self, context_id: UUID) -> Tuple[List[str], List[float]]:
        """
        Load word boosting terms and scores for a context.

        Args:
            context_id: UUID of the context

        Returns:
            Tuple of (terms list, scores list)
        """
        context = await self.context_repo.get_by_id(context_id)

        if not context or not context.word_boosting_config:
            return [], []

        all_terms = []
        all_scores = []

        config = context.word_boosting_config

        # Iterate through categories in the config
        for category, data in config.items():
            if not isinstance(data, dict):
                continue

            terms = data.get("terms", [])
            boost_score = data.get("boost_score", 30.0)

            all_terms.extend(terms)
            all_scores.extend([boost_score] * len(terms))

        logger.info(f"Loaded {len(all_terms)} word boosting terms from context '{context.name}'")

        return all_terms, all_scores

    async def get_speaker_labels(self, context_id: UUID) -> Dict[str, str]:
        """
        Get speaker label mappings for a context.

        Args:
            context_id: UUID of the context

        Returns:
            Dictionary mapping speaker IDs to labels
        """
        context = await self.context_repo.get_by_id(context_id)

        if not context:
            return {}

        return context.speaker_labels or {}

    async def publish_context(self, context_id: UUID, owner_id: UUID) -> bool:
        """
        Publish a context to make it publicly accessible.

        Args:
            context_id: UUID of the context
            owner_id: UUID of the owner (for authorization)

        Returns:
            True if published successfully, False otherwise
        """
        context = await self.context_repo.get_by_id(context_id)

        if not context or context.owner_id != owner_id or context.is_system:
            return False

        # Validate context has required fields
        if not context.word_boosting_config or not context.templates:
            logger.warning(f"Cannot publish context {context_id}: missing required data")
            return False

        await self.context_repo.update(context_id, is_public=True)
        logger.info(f"Published context '{context.name}' (ID: {context_id})")

        return True

    async def unpublish_context(self, context_id: UUID, owner_id: UUID) -> bool:
        """
        Unpublish a context to make it private again.

        Args:
            context_id: UUID of the context
            owner_id: UUID of the owner (for authorization)

        Returns:
            True if unpublished successfully, False otherwise
        """
        context = await self.context_repo.get_by_id(context_id)

        if not context or context.owner_id != owner_id or context.is_system:
            return False

        await self.context_repo.update(context_id, is_public=False)
        logger.info(f"Unpublished context '{context.name}' (ID: {context_id})")

        return True
