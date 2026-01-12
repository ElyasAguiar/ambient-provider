# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ARQ worker entry point for processing transcription jobs."""
import logging
import socket
from typing import Any, Dict, Optional
from uuid import UUID

from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ambient_scribe.deps import Settings
from ambient_scribe.repositories.transcript_job_repository import TranscriptJobRepository
from ambient_scribe.repositories.transcript_repository import TranscriptRepository
from ambient_scribe.services.redis import RedisJobManager, RedisPublisher
from ambient_scribe.services.storage import S3StorageManager
from ambient_scribe.services.transcription_service import (
    TranscriptionEngine,
    TranscriptionService,
)

from .job_context import TranscriptionJobContext
from .job_processor import TranscriptionJobProcessor

logger = logging.getLogger(__name__)

# Global settings
settings = Settings()

# Database engine
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Storage manager (MinIO) - lazy initialization
_storage_manager: Optional[S3StorageManager] = None


def get_storage_manager() -> S3StorageManager:
    """Get or create storage manager instance."""
    global _storage_manager
    if _storage_manager is None:
        _storage_manager = S3StorageManager(
            bucket_name=settings.minio_bucket_name,
            endpoint_url=f"http://{settings.minio_endpoint}",
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            use_ssl=settings.minio_use_ssl,
        )
    return _storage_manager


async def process_transcription_job(
    ctx: dict,
    job_id: str,
    transcript_id: str,
    audio_key: str,
    filename: str,
    engine: str = "asr",
    language: str = "en-US",
    context_id: Optional[str] = None,
    engine_params: Optional[Dict[str, Any]] = None,
) -> dict:
    """
    Process a transcription job using specified engine.

    Args:
        ctx: ARQ context dictionary
        job_id: Unique job identifier
        transcript_id: Transcript database ID
        audio_key: MinIO object key for audio file
        filename: Original filename
        engine: Transcription engine ('asr' or 'whisperx')
        language: Audio language
        context_id: Optional context ID for domain-specific processing
        engine_params: Engine-specific parameters

    Returns:
        Dictionary with result information
    """
    worker_id = socket.gethostname()
    redis_client = ctx["redis"]

    logger.info(
        f"[{worker_id}] Processing job {job_id} with engine={engine}, "
        f"transcript_id={transcript_id}"
    )

    # Validate engine upfront
    try:
        engine_enum = TranscriptionEngine(engine)
    except ValueError as e:
        error_msg = f"Invalid transcription engine: {engine}"
        logger.error(f"[{worker_id}] {error_msg}")
        raise ValueError(error_msg) from e

    # Initialize services
    job_manager = RedisJobManager(redis_client, default_ttl=settings.redis_job_ttl)
    publisher = RedisPublisher(redis_client)
    transcription_service = TranscriptionService(settings)
    storage_manager = get_storage_manager()

    # Create database session
    async with async_session_factory() as db:
        # Initialize repositories
        transcript_repo = TranscriptRepository(db)
        job_repo = TranscriptJobRepository(db)

        # Create job context
        job_context = TranscriptionJobContext(
            job_id=job_id,
            transcript_id=UUID(transcript_id),
            audio_key=audio_key,
            filename=filename,
            engine=engine_enum,
            language=language,
            context_id=UUID(context_id) if context_id else None,
            engine_params=engine_params or {},
            worker_id=worker_id,
            db=db,
            job_manager=job_manager,
            publisher=publisher,
            storage_manager=storage_manager,
            transcription_service=transcription_service,
            transcript_repo=transcript_repo,
            job_repo=job_repo,
        )

        # Process job using the processor
        processor = TranscriptionJobProcessor(job_context)
        return await processor.process()


async def startup(ctx: dict):
    """ARQ worker startup hook."""
    print("Worker starting up...")


async def shutdown(ctx: dict):
    """ARQ worker shutdown hook."""
    print("Worker shutting down...")


class WorkerSettings:
    """ARQ worker settings."""

    redis_settings = RedisSettings.from_dsn(settings.redis_url)

    functions = [process_transcription_job]

    on_startup = startup
    on_shutdown = shutdown

    # Job settings
    max_jobs = 10  # Maximum concurrent jobs per worker
    job_timeout = 3600  # 1 hour timeout for transcription jobs
    keep_result = 3600  # Keep result in Redis for 1 hour

    # Retry settings
    max_tries = 3
    retry_jobs = True
