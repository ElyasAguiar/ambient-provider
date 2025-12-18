# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""WhisperX transcription router."""
import logging
from pathlib import Path
from typing import Optional

from ambient_scribe.deps import get_settings, get_upload_dir
from ambient_scribe.models import Transcript
from ambient_scribe.services.whisperx_service import (
    get_available_models,
    get_whisperx_job_result,
    get_whisperx_job_status,
    submit_whisperx_job,
)
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)


class WhisperXJobResponse(BaseModel):
    """Response for WhisperX job submission."""

    job_id: str
    status: str


class WhisperXJobStatusResponse(BaseModel):
    """Response for WhisperX job status."""

    job_id: str
    status: str  # processing, completed, failed
    progress: int  # 0-100
    error: Optional[str] = None


@router.get("/models")
async def list_whisperx_models(settings=Depends(get_settings)) -> dict:
    """List available WhisperX models."""
    if not settings.whisperx_enabled:
        raise HTTPException(status_code=503, detail="WhisperX service is disabled")

    models = get_available_models()
    return {
        "models": models,
        "default_model": settings.whisperx_default_model,
    }


@router.post("/transcribe", response_model=WhisperXJobResponse)
async def transcribe_with_whisperx(
    file: UploadFile = File(...),
    model: str = Form("base"),
    language: Optional[str] = Form(None),
    enable_diarization: bool = Form(True),
    min_speakers: Optional[int] = Form(None),
    max_speakers: Optional[int] = Form(None),
    settings=Depends(get_settings),
    upload_dir: Path = Depends(get_upload_dir),
) -> WhisperXJobResponse:
    """
    Submit audio file for WhisperX transcription (async job).

    Args:
        file: Audio file to transcribe
        model: WhisperX model (tiny, base, small, medium, large-v2, large-v3)
        language: Optional language code (e.g., 'en', 'es')
        enable_diarization: Enable speaker diarization
        min_speakers: Minimum number of speakers
        max_speakers: Maximum number of speakers

    Returns:
        Job ID for polling status
    """
    if not settings.whisperx_enabled:
        raise HTTPException(status_code=503, detail="WhisperX service is disabled")

    # Validate file type
    if not file.content_type or not file.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="File must be an audio file")

    # Validate model
    available_models = get_available_models()
    if model not in available_models:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid model. Available models: {', '.join(available_models)}",
        )

    # Check file size
    file_size = getattr(file, "size", None)
    if file_size and file_size > settings.max_file_size:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {settings.max_file_size} bytes",
        )

    try:
        # Save uploaded file
        import uuid

        job_id = str(uuid.uuid4())
        file_path = upload_dir / f"whisperx_{job_id}_{file.filename}"

        logger.info(f"Saving WhisperX upload to: {file_path}")
        content = await file.read()
        with open(file_path, "wb") as buffer:
            buffer.write(content)

        # Submit job
        logger.info(f"Submitting WhisperX job: {job_id}, model={model}")
        job_id = await submit_whisperx_job(
            audio_file_path=file_path,
            model=model,
            language=language,
            enable_diarization=enable_diarization,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
        )

        return WhisperXJobResponse(job_id=job_id, status="processing")

    except Exception as e:
        logger.error(f"WhisperX job submission failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs/{job_id}/status", response_model=WhisperXJobStatusResponse)
async def get_job_status(job_id: str) -> WhisperXJobStatusResponse:
    """
    Get status of a WhisperX transcription job.

    Args:
        job_id: Job ID returned from /transcribe

    Returns:
        Job status and progress
    """
    job = get_whisperx_job_status(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return WhisperXJobStatusResponse(
        job_id=job_id,
        status=job["status"],
        progress=job["progress"],
        error=job.get("error"),
    )


@router.get("/jobs/{job_id}/result", response_model=Transcript)
async def get_job_result(job_id: str) -> Transcript:
    """
    Get result of a completed WhisperX transcription job.

    Args:
        job_id: Job ID returned from /transcribe

    Returns:
        Transcript object with segments and metadata
    """
    # Check job status first
    job = get_whisperx_job_status(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] == "processing":
        raise HTTPException(status_code=202, detail="Job still processing")

    if job["status"] == "failed":
        error_msg = job.get("error", "Unknown error")
        raise HTTPException(status_code=500, detail=f"Job failed: {error_msg}")

    # Get result
    transcript = get_whisperx_job_result(job_id)

    if not transcript:
        raise HTTPException(status_code=404, detail="Result not found")

    return transcript
