# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ARQ worker for processing transcription jobs."""
import logging
import os
import socket
import tempfile
import traceback
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import UUID

from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ambient_scribe.deps import Settings
from ambient_scribe.repositories.transcript_job_repository import TranscriptJobRepository
from ambient_scribe.repositories.transcript_repository import TranscriptRepository
from ambient_scribe.services.redis_client import RedisJobManager, RedisPublisher
from ambient_scribe.services.transcription_service import (
    TranscriptionEngine,
    TranscriptionService,
)
from ambient_scribe.utils.storage import S3StorageManager

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

# Storage manager (MinIO)
storage_manager = S3StorageManager(
    bucket_name=settings.minio_bucket_name,
    endpoint_url=f"http://{settings.minio_endpoint}",
    access_key=settings.minio_access_key,
    secret_key=settings.minio_secret_key,
    use_ssl=settings.minio_use_ssl,
)


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

    # Initialize Redis managers
    job_manager = RedisJobManager(redis_client, default_ttl=settings.redis_job_ttl)
    publisher = RedisPublisher(redis_client)

    # Initialize transcription service
    transcription_service = TranscriptionService(settings)

    # Create database session
    async with async_session_factory() as db:
        transcript_repo = TranscriptRepository(db)
        job_repo = TranscriptJobRepository(db)

        try:
            # Validate engine
            try:
                engine_enum = TranscriptionEngine(engine)
            except ValueError:
                raise ValueError(f"Invalid transcription engine: {engine}")

            # Update job status to processing
            await job_manager.update_job_status(job_id, "processing", progress=0)
            await publisher.publish_status_update(
                job_id, "processing", progress=0, message=f"Starting {engine.upper()} transcription"
            )

            # Update worker info in database
            await job_repo.update_worker_info(job_id, worker_id)
            await job_repo.increment_attempts(job_id)
            await db.commit()

            # Download audio from MinIO to temporary file
            await publisher.publish_progress(job_id, 10, "Downloading audio file")
            audio_data = await storage_manager.read_file(audio_key)

            # Save to temporary file
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=Path(filename).suffix
            ) as temp_file:
                temp_file.write(audio_data)
                temp_audio_path = Path(temp_file.name)

            try:
                # Process transcription using appropriate engine
                await publisher.publish_progress(job_id, 20, f"Transcribing with {engine.upper()}")

                transcript_result = await transcription_service.transcribe(
                    audio_path=temp_audio_path,
                    transcript_id=transcript_id,
                    filename=filename,
                    engine=engine_enum,
                    language=language,
                    context_id=UUID(context_id) if context_id else None,
                    db=db,
                    **(engine_params or {}),
                )

                await publisher.publish_progress(job_id, 80, "Saving results")

                logger.info(
                    f"[{worker_id}] {engine.upper()} transcription completed: "
                    f"{len(transcript_result.segments)} segments"
                )

                # Convert Pydantic models to dicts for JSON storage
                segments_dict = [
                    seg.model_dump() if hasattr(seg, "model_dump") else seg.dict()
                    for seg in transcript_result.segments
                ]

                # Update transcript in database
                await transcript_repo.update_segments(
                    UUID(transcript_id),
                    segments=segments_dict,
                    duration=transcript_result.duration,
                    speaker_roles=transcript_result.speaker_roles,
                )

                # Mark job as completed in database
                await job_repo.mark_completed(job_id)
                await db.commit()

                # Update Redis status
                result_data = {
                    "transcript_id": transcript_id,
                    "segments_count": len(transcript_result.segments),
                    "duration": transcript_result.duration,
                }

                await job_manager.update_job_status(
                    job_id, "completed", progress=100, result=result_data
                )
                await job_manager.set_job_result(job_id, result_data)
                await publisher.publish_completed(job_id, result=result_data)

                return {
                    "status": "completed",
                    "job_id": job_id,
                    "transcript_id": transcript_id,
                }

            finally:
                # Clean up temporary file
                if temp_audio_path.exists():
                    temp_audio_path.unlink()

        except Exception as e:
            error_message = str(e)
            error_trace = traceback.format_exc()

            logger.error(
                f"[{worker_id}] Job {job_id} failed with {engine.upper()}: {error_message}",
                exc_info=True,
            )

            # Update transcript status to failed
            await transcript_repo.update_status(
                UUID(transcript_id),
                status="failed",
                error_message=error_message,
            )

            # Update job in database
            error_details = {
                "error": error_message,
                "traceback": error_trace,
                "worker_id": worker_id,
                "engine": engine,
            }
            await job_repo.mark_failed(job_id, error_details)
            await db.commit()

            # Update Redis status
            await job_manager.update_job_status(
                job_id, "failed", error=error_message, error_details=error_details
            )
            await publisher.publish_failed(job_id, error_message, error_details)

            # Re-raise to allow ARQ retry mechanism
            raise


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
