# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Context dataclass for transcription job processing."""
from dataclasses import dataclass
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ambient_scribe.repositories.transcript_job_repository import TranscriptJobRepository
from ambient_scribe.repositories.transcript_repository import TranscriptRepository
from ambient_scribe.services.redis import RedisJobManager, RedisPublisher
from ambient_scribe.services.storage import S3StorageManager
from ambient_scribe.services.transcription_service import (
    TranscriptionEngine,
    TranscriptionService,
)


@dataclass
class TranscriptionJobContext:
    """Context for transcription job processing.

    Encapsulates all dependencies and configuration needed for processing
    a transcription job, following dependency injection pattern.
    """

    # Job identifiers
    job_id: str
    transcript_id: UUID
    worker_id: str

    # Audio file info
    audio_key: str
    filename: str

    # Transcription config
    engine: TranscriptionEngine
    language: str
    context_id: Optional[UUID]
    engine_params: Dict[str, Any]

    # Database
    db: AsyncSession

    # Services
    job_manager: RedisJobManager
    publisher: RedisPublisher
    storage_manager: S3StorageManager
    transcription_service: TranscriptionService

    # Repositories
    transcript_repo: TranscriptRepository
    job_repo: TranscriptJobRepository
