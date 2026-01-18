# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""FastStream consumer for processing transcription results."""
import logging
from datetime import datetime
from typing import Dict
from uuid import UUID

from faststream import Logger
from faststream.redis.annotations import ContextRepo, Redis
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from ambient_scribe.deps import get_settings
from ambient_scribe.models.api.stream_messages import TranscriptionResultMessage
from ambient_scribe.repositories.transcript_job_repository import TranscriptJobRepository
from ambient_scribe.repositories.transcript_repository import TranscriptRepository
from ambient_scribe.services.redis import RedisJobManager, RedisPublisher, get_redis_client
from ambient_scribe.stream_broker import broker

logger = logging.getLogger("ambient_scribe.consumers.result")

# Get settings
settings = get_settings()

# Create async database session factory
engine = create_async_engine(
    settings.database_url,
    echo=settings.database_echo,
    pool_pre_ping=True,
)
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@broker.subscriber(stream=settings.transcription_results_stream)
async def process_transcription_result(
    msg: Dict,
    logger: Logger,
):
    """
    Process transcription result messages from workers.

    This consumer:
    1. Validates the result message
    2. Updates Transcript with segments and metadata
    3. Marks TranscriptJob as completed
    4. Updates Redis job status
    5. Publishes SSE event for real-time notifications

    Args:
        msg: Result message dictionary from worker
        logger: FastStream logger
    """
    try:
        # Parse message
        result = TranscriptionResultMessage(**msg)
        logger.info(f"Processing result for job {result.job_id}, status: {result.status}")

        # Create database session
        async with async_session_maker() as db:
            transcript_repo = TranscriptRepository(db)
            job_repo = TranscriptJobRepository(db)

            # Get transcript and job
            transcript_id = UUID(result.transcript_id)
            transcript = await transcript_repo.get_by_id(transcript_id)

            if not transcript:
                logger.error(f"Transcript not found: {result.transcript_id}")
                return

            job = await job_repo.get_by_job_id(result.job_id)
            if not job:
                logger.error(f"Job not found: {result.job_id}")
                return

            # Process based on status
            if result.status == "completed":
                # Update transcript with results
                await transcript_repo.update_segments(
                    transcript_id=transcript_id,
                    segments=result.segments,
                    duration=result.duration,
                    speaker_roles=result.speaker_roles,
                )
                logger.info(
                    f"Updated transcript {transcript_id} with {len(result.segments)} segments"
                )

                # Mark job as completed
                await job_repo.mark_completed(
                    job_id=result.job_id,
                    completed_at=datetime.utcnow(),
                )
                logger.info(f"Marked job {result.job_id} as completed")

            elif result.status == "failed":
                # Update transcript status to failed
                await transcript_repo.update_status(
                    transcript_id=transcript_id,
                    status="failed",
                    error_message=result.error,
                )
                logger.error(f"Transcript {transcript_id} failed: {result.error}")

                # Mark job as failed
                await job_repo.mark_failed(
                    job_id=result.job_id,
                    error_details={"error": result.error, "retry_count": result.retry_count},
                    completed_at=datetime.utcnow(),
                )
                logger.info(f"Marked job {result.job_id} as failed")

            # Commit database changes
            await db.commit()

        # Update Redis job status
        redis_client = await get_redis_client(settings.redis_url)
        job_manager = RedisJobManager(redis_client, default_ttl=settings.redis_job_ttl)

        await job_manager.update_job_status(
            result.job_id,
            status=result.status,
            progress=100 if result.status == "completed" else 0,
        )

        if result.status == "completed":
            await job_manager.set_job_result(
                result.job_id,
                {
                    "transcript_id": result.transcript_id,
                    "segments": result.segments,
                    "duration": result.duration,
                    "language": result.language,
                },
            )

        # Publish SSE event for real-time updates
        publisher = RedisPublisher(redis_client)
        await publisher.publish_status_update(
            result.job_id,
            result.status,
            transcript_id=result.transcript_id,
            error=result.error,
        )

        await redis_client.close()
        logger.info(f"Successfully processed result for job {result.job_id}")

    except Exception as e:
        logger.error(f"Error processing result: {e}", exc_info=True)
        raise  # Re-raise to trigger FastStream retry mechanism
