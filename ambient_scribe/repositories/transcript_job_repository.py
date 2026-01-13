# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Repository for TranscriptJob operations."""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ambient_scribe.models import database as db_models


class TranscriptJobRepository:
    """Repository for TranscriptJob CRUD operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        transcript_id: UUID,
        job_id: str,
        engine: str = "asr",
        engine_params: Optional[dict] = None,
        max_retries: int = 3,
    ) -> db_models.TranscriptJob:
        """
        Create a new transcript job record.

        Args:
            transcript_id: Associated transcript ID
            job_id: Unique Redis job ID
            engine: Transcription engine ('asr' or 'whisperx')
            engine_params: Engine-specific parameters
            max_retries: Maximum retry attempts

        Returns:
            Created TranscriptJob instance
        """
        job = db_models.TranscriptJob(
            transcript_id=transcript_id,
            job_id=job_id,
            engine=engine,
            engine_params=engine_params or {},
            max_retries=max_retries,
            attempts=0,
        )
        self.db.add(job)
        await self.db.flush()
        await self.db.refresh(job)
        return job

    async def get_by_id(self, job_db_id: UUID) -> Optional[db_models.TranscriptJob]:
        """
        Get transcript job by database ID.

        Args:
            job_db_id: TranscriptJob UUID

        Returns:
            TranscriptJob instance or None
        """
        result = await self.db.execute(
            select(db_models.TranscriptJob)
            .options(selectinload(db_models.TranscriptJob.transcript))
            .where(db_models.TranscriptJob.id == job_db_id)
        )
        return result.scalar_one_or_none()

    async def get_by_job_id(self, job_id: str) -> Optional[db_models.TranscriptJob]:
        """
        Get transcript job by Redis job ID.

        Args:
            job_id: Redis job ID string

        Returns:
            TranscriptJob instance or None
        """
        result = await self.db.execute(
            select(db_models.TranscriptJob)
            .options(selectinload(db_models.TranscriptJob.transcript))
            .where(db_models.TranscriptJob.job_id == job_id)
        )
        return result.scalar_one_or_none()

    async def get_by_transcript_id(self, transcript_id: UUID) -> Optional[db_models.TranscriptJob]:
        """
        Get transcript job by transcript ID.

        Args:
            transcript_id: Transcript UUID

        Returns:
            TranscriptJob instance or None
        """
        result = await self.db.execute(
            select(db_models.TranscriptJob).where(
                db_models.TranscriptJob.transcript_id == transcript_id
            )
        )
        return result.scalar_one_or_none()

    async def update_worker_info(
        self, job_id: str, worker_id: str, started_at: Optional[datetime] = None
    ) -> Optional[db_models.TranscriptJob]:
        """
        Update worker information when job starts processing.

        Args:
            job_id: Redis job ID
            worker_id: Worker identifier
            started_at: Job start timestamp (defaults to now)

        Returns:
            Updated TranscriptJob instance or None
        """
        job = await self.get_by_job_id(job_id)
        if job:
            job.worker_id = worker_id
            job.started_at = started_at or datetime.utcnow()
            await self.db.flush()
            await self.db.refresh(job)
        return job

    async def increment_attempts(self, job_id: str) -> Optional[db_models.TranscriptJob]:
        """
        Increment job attempt counter.

        Args:
            job_id: Redis job ID

        Returns:
            Updated TranscriptJob instance or None
        """
        job = await self.get_by_job_id(job_id)
        if job:
            job.attempts += 1
            await self.db.flush()
            await self.db.refresh(job)
        return job

    async def mark_completed(
        self, job_id: str, completed_at: Optional[datetime] = None
    ) -> Optional[db_models.TranscriptJob]:
        """
        Mark job as completed.

        Args:
            job_id: Redis job ID
            completed_at: Completion timestamp (defaults to now)

        Returns:
            Updated TranscriptJob instance or None
        """
        job = await self.get_by_job_id(job_id)
        if job:
            job.completed_at = completed_at or datetime.utcnow()
            await self.db.flush()
            await self.db.refresh(job)
        return job

    async def mark_failed(
        self,
        job_id: str,
        error_details: dict,
        completed_at: Optional[datetime] = None,
    ) -> Optional[db_models.TranscriptJob]:
        """
        Mark job as failed with error details.

        Args:
            job_id: Redis job ID
            error_details: Error information dictionary
            completed_at: Failure timestamp (defaults to now)

        Returns:
            Updated TranscriptJob instance or None
        """
        job = await self.get_by_job_id(job_id)
        if job:
            job.completed_at = completed_at or datetime.utcnow()
            job.error_details = error_details
            await self.db.flush()
            await self.db.refresh(job)
        return job

    async def get_retryable_jobs(self) -> List[db_models.TranscriptJob]:
        """
        Get jobs that can be retried (attempts < max_retries and not completed).

        Returns:
            List of TranscriptJob instances eligible for retry
        """
        result = await self.db.execute(
            select(db_models.TranscriptJob)
            .where(
                db_models.TranscriptJob.attempts < db_models.TranscriptJob.max_retries,
                db_models.TranscriptJob.completed_at.is_(None),
            )
            .order_by(db_models.TranscriptJob.created_at)
        )
        return list(result.scalars().all())

    async def get_old_completed_jobs(self, older_than: datetime) -> List[db_models.TranscriptJob]:
        """
        Get completed jobs older than specified datetime (for cleanup).

        Args:
            older_than: Datetime threshold

        Returns:
            List of old completed TranscriptJob instances
        """
        result = await self.db.execute(
            select(db_models.TranscriptJob)
            .where(
                db_models.TranscriptJob.completed_at.isnot(None),
                db_models.TranscriptJob.completed_at < older_than,
            )
            .order_by(db_models.TranscriptJob.completed_at)
        )
        return list(result.scalars().all())

    async def delete(self, job_id: str) -> bool:
        """
        Delete transcript job by Redis job ID.

        Args:
            job_id: Redis job ID

        Returns:
            True if deleted, False if not found
        """
        job = await self.get_by_job_id(job_id)
        if job:
            await self.db.delete(job)
            await self.db.flush()
            return True
        return False
