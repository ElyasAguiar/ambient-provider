# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Transcription job processor with clear separation of concerns."""

import asyncio
import logging
import tempfile
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from .job_context import TranscriptionJobContext

logger = logging.getLogger(__name__)


class TranscriptionJobProcessor:
    """Handles the processing of transcription jobs with clear separation of concerns.

    This class implements a pipeline pattern where each step is isolated and testable.
    The processor orchestrates the entire transcription workflow from initialization
    to completion or failure handling.
    """

    # Configurable retry parameters for audio download
    AUDIO_DOWNLOAD_MAX_RETRIES = 10
    AUDIO_DOWNLOAD_RETRY_DELAY = 2  # seconds

    def __init__(self, ctx: TranscriptionJobContext):
        """Initialize processor with job context.

        Args:
            ctx: TranscriptionJobContext with all dependencies
        """
        self.ctx = ctx

    async def process(self) -> dict:
        """Main processing pipeline.

        Orchestrates the entire transcription workflow:
        1. Initialize job (update status, worker info)
        2. Download audio from storage
        3. Process transcription with temporary file
        4. Save results to database
        5. Mark job as completed

        Returns:
            Dictionary with result information

        Raises:
            Exception: Any unhandled exception is caught and processed by _handle_failure
        """
        try:
            # Step 1: Initialize job
            await self._initialize_job()

            # Step 2: Download audio
            audio_data = await self._download_audio()

            # Step 3: Process transcription with temp file
            transcript_result = await self._process_with_temp_file(audio_data)

            # Step 4: Save results
            await self._save_results(transcript_result)

            # Step 5: Mark as completed
            return await self._complete_job(transcript_result)

        except Exception as e:
            return await self._handle_failure(e)

    async def _initialize_job(self):
        """Initialize job processing: update status and worker info.

        Updates both Redis (for real-time status) and database (for persistence).
        Commits to database to ensure worker info is saved before processing starts.
        """
        logger.info(
            f"[{self.ctx.worker_id}] Initializing job {self.ctx.job_id} "
            f"with engine={self.ctx.engine.value}"
        )

        # Update job status to processing
        await self.ctx.job_manager.update_job_status(self.ctx.job_id, "processing", progress=0)
        await self.ctx.publisher.publish_status_update(
            self.ctx.job_id,
            "processing",
            progress=0,
            message=f"Starting {self.ctx.engine.value.upper()} transcription",
        )

        # Update worker info in database
        await self.ctx.job_repo.update_worker_info(self.ctx.job_id, self.ctx.worker_id)
        await self.ctx.job_repo.increment_attempts(self.ctx.job_id)
        await self.ctx.db.commit()

    async def _download_audio(self) -> bytes:
        """Download audio file from storage with retry logic for pending uploads.

        Returns:
            Audio file content as bytes

        Raises:
            RuntimeError: If download fails, with original exception as cause
        """
        logger.info(f"[{self.ctx.worker_id}] Downloading audio from key: {self.ctx.audio_key}")

        await self.ctx.publisher.publish_progress(self.ctx.job_id, 10, "Downloading audio file")

        max_retries = self.AUDIO_DOWNLOAD_MAX_RETRIES
        retry_delay = self.AUDIO_DOWNLOAD_RETRY_DELAY

        for attempt in range(max_retries):
            try:
                # Check if file exists
                if await self.ctx.storage_manager.file_exists(self.ctx.audio_key):
                    audio_data = await self.ctx.storage_manager.read_file(self.ctx.audio_key)
                    logger.info(
                        f"[{self.ctx.worker_id}] Downloaded {len(audio_data)} bytes from MinIO"
                    )
                    return audio_data
                else:
                    logger.warning(
                        f"[{self.ctx.worker_id}] Audio file not found yet "
                        f"(attempt {attempt + 1}/{max_retries}), waiting {retry_delay}s..."
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)

            except Exception as e:
                logger.error(f"[{self.ctx.worker_id}] Error downloading audio: {e}")
                if attempt < max_retries - 1:
                    logger.warning(
                        f"[{self.ctx.worker_id}] Retrying download "
                        f"(attempt {attempt + 1}/{max_retries})..."
                    )
                    await asyncio.sleep(retry_delay)
                else:
                    raise RuntimeError(f"Failed to download audio file: {e}") from e

        raise RuntimeError(f"Audio file not available after {max_retries} attempts")

    @asynccontextmanager
    async def _temp_audio_file(self, audio_data: bytes):
        """Context manager for temporary audio file.

        Creates a temporary file with the audio data and ensures cleanup
        even if processing fails. Uses the original file extension to
        maintain compatibility with transcription engines.

        Args:
            audio_data: Audio file content as bytes

        Yields:
            Path: Path to temporary audio file
        """
        temp_path = None
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=Path(self.ctx.filename).suffix
            ) as temp_file:
                temp_file.write(audio_data)
                temp_path = Path(temp_file.name)

            logger.info(f"[{self.ctx.worker_id}] Created temp file: {temp_path}")
            yield temp_path

        finally:
            # Cleanup: ensure temp file is deleted
            if temp_path and temp_path.exists():
                try:
                    temp_path.unlink()
                    logger.debug(f"[{self.ctx.worker_id}] Cleaned up temp file: {temp_path}")
                except Exception as e:
                    logger.warning(
                        f"[{self.ctx.worker_id}] Failed to cleanup temp file {temp_path}: {e}"
                    )

    async def _process_with_temp_file(self, audio_data: bytes):
        """Process transcription using temporary file.

        Uses context manager to ensure temporary file cleanup regardless
        of success or failure.

        Args:
            audio_data: Audio file content as bytes

        Returns:
            TranscriptResult: Result from transcription service
        """
        async with self._temp_audio_file(audio_data) as temp_audio_path:
            await self.ctx.publisher.publish_progress(
                self.ctx.job_id,
                20,
                f"Transcribing with {self.ctx.engine.value.upper()}",
            )

            logger.info(
                f"[{self.ctx.worker_id}] Starting transcription with "
                f"{self.ctx.engine.value.upper()}"
            )

            transcript_result = await self.ctx.transcription_service.transcribe(
                audio_path=temp_audio_path,
                transcript_id=str(self.ctx.transcript_id),
                filename=self.ctx.filename,
                engine=self.ctx.engine,
                language=self.ctx.language,
                context_id=self.ctx.context_id,
                db=self.ctx.db,
                **self.ctx.engine_params,
            )

            logger.info(
                f"[{self.ctx.worker_id}] Transcription completed: "
                f"{len(transcript_result.segments)} segments, "
                f"duration={transcript_result.duration}s"
            )

            return transcript_result

    async def _save_results(self, transcript_result):
        """Save transcription results to database.

        Converts Pydantic models to dictionaries for JSON storage and
        updates the transcript record with segments, duration, and speaker roles.

        Args:
            transcript_result: Result from transcription service
        """
        await self.ctx.publisher.publish_progress(self.ctx.job_id, 80, "Saving results")

        # Convert Pydantic models to dicts for JSON storage
        segments_dict = [
            seg.model_dump() if hasattr(seg, "model_dump") else seg.dict()
            for seg in transcript_result.segments
        ]

        # Update transcript in database
        await self.ctx.transcript_repo.update_segments(
            self.ctx.transcript_id,
            segments=segments_dict,
            duration=transcript_result.duration,
            speaker_roles=transcript_result.speaker_roles,
        )

        logger.info(f"[{self.ctx.worker_id}] Saved {len(segments_dict)} segments to database")

    async def _complete_job(self, transcript_result) -> dict:
        """Mark job as completed and publish results.

        Updates both database and Redis with completion status and results.
        Commits to database before updating Redis to ensure data consistency.

        Args:
            transcript_result: Result from transcription service

        Returns:
            Dictionary with completion information
        """
        # Mark job as completed in database
        await self.ctx.job_repo.mark_completed(self.ctx.job_id)
        await self.ctx.db.commit()

        # Prepare result data
        result_data = {
            "transcript_id": str(self.ctx.transcript_id),
            "segments_count": len(transcript_result.segments),
            "duration": transcript_result.duration,
        }

        # Update Redis status
        await self.ctx.job_manager.update_job_status(
            self.ctx.job_id, "completed", progress=100, result=result_data
        )
        await self.ctx.job_manager.set_job_result(self.ctx.job_id, result_data)
        await self.ctx.publisher.publish_completed(self.ctx.job_id, result=result_data)

        logger.info(f"[{self.ctx.worker_id}] Job {self.ctx.job_id} completed successfully")

        return {
            "status": "completed",
            "job_id": self.ctx.job_id,
            "transcript_id": str(self.ctx.transcript_id),
        }

    async def _handle_failure(self, error: Exception) -> dict:
        """Handle job failure with proper error logging and status updates.

        Updates transcript and job status to failed in both database and Redis.
        Includes error details, traceback, and worker information for debugging.
        Re-raises the exception to allow ARQ's retry mechanism to work.

        Args:
            error: The exception that caused the failure

        Raises:
            Exception: Re-raises the original exception after cleanup
        """
        error_message = str(error)
        error_trace = traceback.format_exc()

        logger.error(
            f"[{self.ctx.worker_id}] Job {self.ctx.job_id} failed: {error_message}",
            exc_info=True,
        )

        try:
            # Update transcript status to failed
            await self.ctx.transcript_repo.update_status(
                self.ctx.transcript_id,
                status="failed",
                error_message=error_message,
            )

            # Update job in database
            error_details = {
                "error": error_message,
                "traceback": error_trace,
                "worker_id": self.ctx.worker_id,
                "engine": self.ctx.engine.value,
            }
            await self.ctx.job_repo.mark_failed(self.ctx.job_id, error_details)
            await self.ctx.db.commit()

            # Update Redis status
            await self.ctx.job_manager.update_job_status(
                self.ctx.job_id, "failed", error=error_message, error_details=error_details
            )
            await self.ctx.publisher.publish_failed(self.ctx.job_id, error_message, error_details)

        except Exception as cleanup_error:
            logger.error(
                f"[{self.ctx.worker_id}] Error during failure cleanup: {cleanup_error}",
                exc_info=True,
            )

        # Re-raise to allow ARQ retry mechanism
        raise
