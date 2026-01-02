# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Job-based transcription router with Redis queue."""
import json
import logging
import os
from typing import Optional
from uuid import UUID, uuid4

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from ambient_scribe.database import get_db
from ambient_scribe.deps import Settings, get_settings
from ambient_scribe.repositories.transcript_job_repository import TranscriptJobRepository
from ambient_scribe.repositories.transcript_repository import TranscriptRepository
from ambient_scribe.services.redis import RedisJobManager, RedisSubscriber, get_redis_client
from ambient_scribe.services.storage import S3StorageManager

router = APIRouter(prefix="/api/transcribe/jobs", tags=["transcription-jobs"])
logger = logging.getLogger("ambient_scribe.jobs")
limiter = Limiter(key_func=get_remote_address)

# Storage manager will be initialized on first request
_storage_manager: Optional[S3StorageManager] = None
_redis_pool = None


def get_storage_manager(settings: Settings = Depends(get_settings)) -> S3StorageManager:
    """Get or create storage manager."""
    global _storage_manager
    if _storage_manager is None:
        minio_endpoint = settings.minio_endpoint
        # Add http:// if not present
        if not minio_endpoint.startswith("http"):
            minio_endpoint = f"http://{minio_endpoint}"

        _storage_manager = S3StorageManager(
            bucket_name=settings.minio_bucket_name,
            endpoint_url=minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            use_ssl=settings.minio_use_ssl,
        )
    return _storage_manager


async def get_arq_pool(settings: Settings = Depends(get_settings)):
    """Get or create ARQ Redis pool."""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _redis_pool


@router.post("/transcribe")
@limiter.limit("10/minute")
async def enqueue_transcription_job(
    request: Request,
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    engine: str = Form("asr"),
    context_id: Optional[str] = Form(None),
    language: str = Form("en-US"),
    settings: Settings = Depends(get_settings),
    storage: S3StorageManager = Depends(get_storage_manager),
    db: AsyncSession = Depends(get_db),
):
    """
    Enqueue a transcription job with specified or default engine.

    Args:
        file: Audio file to transcribe
        session_id: Optional session UUID to associate transcript with
        engine: Transcription engine ('asr' or 'whisperx', default: asr)
        context_id: Optional context UUID for domain-specific processing
        language: Audio language (default: en-US)

    Returns:
        Job information with job_id for status polling
    """
    # Validate engine
    if engine not in ["asr", "whisperx"]:
        raise HTTPException(
            status_code=400, detail=f"Invalid engine '{engine}'. Must be 'asr' or 'whisperx'"
        )

    return await _enqueue_job_internal(
        file=file,
        session_id=session_id,
        engine=engine,
        context_id=context_id,
        language=language,
        engine_params={},
        settings=settings,
        storage=storage,
        db=db,
    )


@router.post("/transcribe/asr")
@limiter.limit("10/minute")
async def enqueue_asr_transcription(
    request: Request,
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    context_id: Optional[str] = Form(None),
    language: str = Form("en-US"),
    settings: Settings = Depends(get_settings),
    storage: S3StorageManager = Depends(get_storage_manager),
    db: AsyncSession = Depends(get_db),
):
    """
    Enqueue transcription job using NVIDIA Riva ASR.

    This endpoint uses NVIDIA Riva for high-accuracy speech recognition
    with speaker diarization and optional domain-specific word boosting.

    Args:
        file: Audio file to transcribe
        session_id: Optional session UUID to associate transcript with
        context_id: Optional context UUID for word boosting
        language: Audio language (e.g., 'en-US', 'pt-BR')

    Returns:
        Job information with job_id for status polling
    """
    return await _enqueue_job_internal(
        file=file,
        session_id=session_id,
        engine="asr",
        context_id=context_id,
        language=language,
        engine_params={},
        settings=settings,
        storage=storage,
        db=db,
    )


@router.post("/transcribe/whisperx")
@limiter.limit("10/minute")
async def enqueue_whisperx_transcription(
    request: Request,
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    model: str = Form("base"),
    language: Optional[str] = Form(None),
    enable_diarization: bool = Form(True),
    min_speakers: Optional[int] = Form(None),
    max_speakers: Optional[int] = Form(None),
    settings: Settings = Depends(get_settings),
    storage: S3StorageManager = Depends(get_storage_manager),
    db: AsyncSession = Depends(get_db),
):
    """
    Enqueue transcription job using WhisperX.

    This endpoint uses WhisperX for multilingual speech recognition
    with advanced speaker diarization capabilities.

    Args:
        file: Audio file to transcribe
        session_id: Optional session UUID to associate transcript with
        model: WhisperX model (tiny, base, small, medium, large-v2, large-v3)
        language: 2-letter language code (e.g., 'en', 'pt') - auto-detect if None
        enable_diarization: Enable speaker diarization
        min_speakers: Minimum number of speakers hint
        max_speakers: Maximum number of speakers hint

    Returns:
        Job information with job_id for status polling
    """
    # Validate model
    from ambient_scribe.services.transcription_service import TranscriptionService

    transcription_service = TranscriptionService(settings)

    if not transcription_service.validate_whisperx_model(model):
        available = transcription_service.get_whisperx_models()
        raise HTTPException(
            status_code=400, detail=f"Invalid model '{model}'. Available: {', '.join(available)}"
        )

    # Prepare engine parameters
    engine_params = {
        "model": model,
        "enable_diarization": enable_diarization,
    }
    if min_speakers is not None:
        engine_params["min_speakers"] = min_speakers
    if max_speakers is not None:
        engine_params["max_speakers"] = max_speakers

    return await _enqueue_job_internal(
        file=file,
        session_id=session_id,
        engine="whisperx",
        context_id=None,  # WhisperX doesn't use context for word boosting
        language=language or "en",
        engine_params=engine_params,
        settings=settings,
        storage=storage,
        db=db,
    )


async def _enqueue_job_internal(
    file: UploadFile,
    session_id: Optional[str],
    engine: str,
    context_id: Optional[str],
    language: str,
    engine_params: dict,
    settings: Settings,
    storage: S3StorageManager,
    db: AsyncSession,
):
    """
    Internal function to enqueue transcription jobs.
    Shared logic for all transcription endpoints.
    """
    logger.info(f"Received {engine.upper()} transcription request: filename={file.filename}")

    # Validate file type
    if not file.content_type or not file.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="File must be an audio file")

    # Check file size
    file_size = getattr(file, "size", None)
    if file_size and file_size > settings.max_file_size:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {settings.max_file_size} bytes",
        )

    # Validate session_id if provided
    session_uuid = None
    if session_id:
        try:
            session_uuid = UUID(session_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid session_id format")

    # Validate context_id if provided
    context_uuid_str = None
    if context_id:
        try:
            UUID(context_id)  # Validate format
            context_uuid_str = context_id
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid context_id format")

    # Validate filename
    if not file.filename:
        raise HTTPException(status_code=400, detail="File must have a filename")

    try:
        # Read file content
        content = await file.read()
        logger.info(f"Read {len(content)} bytes from uploaded file")

        # Upload to MinIO
        audio_key = await storage.save_file(content, file.filename, subfolder="transcriptions")
        logger.info(f"Uploaded audio to MinIO: {audio_key}")

        # Generate presigned URL for audio access (1 hour expiration)
        audio_url = storage.generate_presigned_url(audio_key, expiration=3600)

        # Create transcript record in database
        transcript_repo = TranscriptRepository(db)
        transcript = await transcript_repo.create(
            filename=file.filename,
            audio_url=audio_url,
            language=language,
            session_id=session_uuid,
        )
        await db.commit()
        logger.info(f"Created transcript record: {transcript.id}")

        # Generate job ID
        job_id = str(uuid4())

        # Create job record in database with engine info
        job_repo = TranscriptJobRepository(db)
        job = await job_repo.create(
            transcript_id=transcript.id,
            job_id=job_id,
            engine=engine,
            engine_params=engine_params,
            max_retries=3,
        )
        await db.commit()
        logger.info(f"Created {engine.upper()} job record: {job_id}")

        # Get Redis client for job manager
        redis_client = await get_redis_client(settings.redis_url)
        job_manager = RedisJobManager(redis_client, default_ttl=settings.redis_job_ttl)

        # Create job in Redis
        await job_manager.create_job(
            job_id,
            {
                "transcript_id": str(transcript.id),
                "filename": file.filename,
                "language": language,
                "engine": engine,
            },
        )

        # Enqueue job to ARQ with engine parameters
        arq_pool = await get_arq_pool(settings)
        await arq_pool.enqueue_job(
            "process_transcription_job",
            job_id=job_id,
            transcript_id=str(transcript.id),
            audio_key=audio_key,
            filename=file.filename,
            engine=engine,
            language=language,
            context_id=context_uuid_str,
            engine_params=engine_params,
        )
        logger.info(f"Enqueued {engine.upper()} job to ARQ: {job_id}")

        await redis_client.close()

        return {
            "job_id": job_id,
            "transcript_id": str(transcript.id),
            "engine": engine,
            "status": "queued",
            "message": f"{engine.upper()} transcription job enqueued successfully",
        }

    except Exception as e:
        logger.error(f"Error enqueuing transcription job: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to enqueue transcription: {str(e)}")


@router.get("/engines")
async def list_available_engines(settings: Settings = Depends(get_settings)):
    """
    List available transcription engines and their capabilities.

    Returns:
        Dictionary of available engines with status and capabilities
    """
    from ambient_scribe.services.transcription_service import TranscriptionService

    transcription_service = TranscriptionService(settings)

    asr_info = await transcription_service.validate_asr_availability()
    whisperx_info = await transcription_service.validate_whisperx_availability()

    return {
        "engines": {
            "asr": asr_info,
            "whisperx": whisperx_info,
        },
        "default_engine": transcription_service.get_default_engine().value,
    }


@router.get("/status/{job_id}")
async def get_job_status(
    job_id: str,
    settings: Settings = Depends(get_settings),
    db: AsyncSession = Depends(get_db),
):
    """
    Get job status from Redis (fast) or database (fallback).

    Args:
        job_id: Job identifier

    Returns:
        Job status information
    """
    try:
        # Try Redis first (fast cache)
        redis_client = await get_redis_client(settings.redis_url)
        job_manager = RedisJobManager(redis_client, default_ttl=settings.redis_job_ttl)

        status_data = await job_manager.get_job_status(job_id)

        if status_data:
            await redis_client.close()
            return status_data

        await redis_client.close()

        # Fallback to database
        job_repo = TranscriptJobRepository(db)
        job = await job_repo.get_by_job_id(job_id)

        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        # Get transcript status
        transcript_repo = TranscriptRepository(db)
        transcript = await transcript_repo.get_by_id(job.transcript_id)

        return {
            "job_id": job_id,
            "status": transcript.status if transcript else "unknown",
            "transcript_id": str(job.transcript_id),
            "attempts": job.attempts,
            "worker_id": job.worker_id,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "error_details": job.error_details,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get job status: {str(e)}")


@router.get("/stream/{job_id}")
async def stream_job_status(
    job_id: str,
    settings: Settings = Depends(get_settings),
):
    """
    Stream job status updates via Server-Sent Events using Redis pub/sub.

    Args:
        job_id: Job identifier

    Returns:
        SSE stream of status updates
    """

    async def event_generator():
        redis_client = None
        try:
            # Connect to Redis
            redis_client = await get_redis_client(settings.redis_url)
            subscriber = RedisSubscriber(redis_client)

            # Send initial status
            yield f"data: {json.dumps({'type': 'connected', 'job_id': job_id})}\n\n"

            # Subscribe to job updates
            async for update in subscriber.subscribe_to_job(job_id):
                yield f"data: {json.dumps(update)}\n\n"

                # Stop after completion or failure
                if update.get("status") in ["completed", "failed"]:
                    break

        except Exception as e:
            logger.error(f"Error streaming job status: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
        finally:
            if redis_client:
                await redis_client.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/result/{job_id}")
async def get_job_result(job_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get completed transcription result.

    Args:
        job_id: Job identifier

    Returns:
        Transcript data
    """
    try:
        # Get job from database
        job_repo = TranscriptJobRepository(db)
        job = await job_repo.get_by_job_id(job_id)

        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        # Get transcript
        transcript_repo = TranscriptRepository(db)
        transcript = await transcript_repo.get_by_id(job.transcript_id)

        if not transcript:
            raise HTTPException(status_code=404, detail="Transcript not found")

        if transcript.status == "processing":
            raise HTTPException(status_code=202, detail="Transcription still in progress")

        if transcript.status == "failed":
            raise HTTPException(
                status_code=500,
                detail=f"Transcription failed: {transcript.error_message}",
            )

        return {
            "job_id": job_id,
            "transcript_id": str(transcript.id),
            "status": transcript.status,
            "filename": transcript.filename,
            "audio_url": transcript.audio_url,
            "language": transcript.language,
            "duration": transcript.duration,
            "segments": transcript.segments,
            "speaker_roles": transcript.speaker_roles,
            "created_at": transcript.created_at.isoformat(),
            "updated_at": transcript.updated_at.isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job result: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get job result: {str(e)}")
