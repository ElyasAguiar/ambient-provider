# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Transcription router."""
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
from typing import Optional
import uuid
import json
import asyncio
from pathlib import Path

from ambient_scribe.models import Transcript, ErrorResponse
from ambient_scribe.services.asr import transcribe_audio_file, stream_transcribe_audio_file
from ambient_scribe.deps import get_settings, get_upload_dir

router = APIRouter()

# In-memory storage for demo (replace with database in production)
_transcripts = {}

import logging
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/file", response_model=Transcript)
@limiter.limit("5/minute")
async def transcribe_file(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    settings=Depends(get_settings),
    upload_dir: Path = Depends(get_upload_dir)
) -> Transcript:
    """Transcribe an uploaded audio file."""

    logger = logging.getLogger("ambient_scribe.transcribe")
    logger.debug(f"Received file upload: filename={file.filename}, content_type={file.content_type}")

    # Validate file type
    if not file.content_type or not file.content_type.startswith("audio/"):
        logger.warning(f"Rejected file: filename={file.filename}, content_type={file.content_type}")
        raise HTTPException(
            status_code=400,
            detail="File must be an audio file"
        )

    # Check file size
    # Note: UploadFile does not always have .size attribute, so log what we can
    file_size = getattr(file, "size", None)
    logger.debug(f"File size: {file_size}")
    if file_size and file_size > settings.max_file_size:
        logger.warning(f"File too large: {file_size} > {settings.max_file_size}")
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {settings.max_file_size} bytes"
        )

    # Generate unique ID and save file
    transcript_id = str(uuid.uuid4())
    file_path = upload_dir / f"{transcript_id}_{file.filename}"
    logger.info(f"Saving uploaded file to: {file_path}")

    try:
        # Save uploaded file
        content = await file.read()
        logger.debug(f"Read {len(content)} bytes from uploaded file")
        with open(file_path, "wb") as buffer:
            buffer.write(content)
        logger.info(f"File saved successfully: {file_path}")

        # Transcribe audio
        logger.info(f"Starting transcription: file_path={file_path}, transcript_id={transcript_id}")
        transcript = await transcribe_audio_file(
            file_path=file_path,
            transcript_id=transcript_id,
            filename=file.filename,
            settings=settings
        )
        logger.info(f"Transcription completed: transcript_id={transcript_id}")

        # Add audio URL to transcript (via API proxy)
        transcript.audio_url = f"/api/uploads/{transcript_id}_{file.filename}"
        
        # Store transcript
        _transcripts[transcript_id] = transcript
        logger.debug(f"Transcript stored in memory: transcript_id={transcript_id}")

        # Keep the audio file (don't schedule cleanup for now)
        # This allows the audio player to access the file
        logger.debug(f"Audio file preserved for playback: {file_path}")

        return transcript

    except Exception as e:
        logger.error(f"Exception during transcription: {e}", exc_info=True)
        # Cleanup file if transcription failed
        if file_path.exists():
            try:
                file_path.unlink()
                logger.info(f"Cleaned up file after failure: {file_path}")
            except Exception as cleanup_exc:
                logger.error(f"Failed to cleanup file: {file_path}, error: {cleanup_exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Transcription failed: {str(e)}"
        )

@router.post("/stream", response_model=None)
@limiter.limit("5/minute")
async def stream_transcribe_file(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    settings=Depends(get_settings),
    upload_dir: Path = Depends(get_upload_dir)
):
    """Stream transcribe an uploaded audio file with real-time updates."""

    logger = logging.getLogger("ambient_scribe.transcribe")
    logger.debug(f"Received streaming file upload: filename={file.filename}, content_type={file.content_type}")

    # Validate file type
    if not file.content_type or not file.content_type.startswith("audio/"):
        logger.warning(f"Rejected file: filename={file.filename}, content_type={file.content_type}")
        raise HTTPException(
            status_code=400,
            detail="File must be an audio file"
        )

    # Check file size
    file_size = getattr(file, "size", None)
    logger.debug(f"File size: {file_size}")
    if file_size and file_size > settings.max_file_size:
        logger.warning(f"File too large: {file_size} > {settings.max_file_size}")
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {settings.max_file_size} bytes"
        )

    # Generate unique ID and save file
    transcript_id = str(uuid.uuid4())
    file_path = upload_dir / f"{transcript_id}_{file.filename}"
    logger.info(f"Saving uploaded file to: {file_path}")

    try:
        # Save uploaded file
        content = await file.read()
        logger.debug(f"Read {len(content)} bytes from uploaded file")
        with open(file_path, "wb") as buffer:
            buffer.write(content)
        logger.info(f"File saved successfully: {file_path}")

        # Create streaming generator
        async def stream_transcription():
            try:
                # Send initial status
                yield f"data: {json.dumps({'type': 'status', 'message': 'Starting transcription...', 'transcript_id': transcript_id})}\n\n"
                
                # Stream transcription results
                last_result = None
                async for result in stream_transcribe_audio_file(
                    file_path=file_path,
                    transcript_id=transcript_id,
                    filename=file.filename,
                    settings=settings
                ):
                    yield f"data: {json.dumps(result)}\n\n"
                    last_result = result
                
                # Store final transcript if completed and send audio_url
                if last_result and last_result.get('type') == 'complete' and 'transcript' in last_result:
                    transcript_data = last_result['transcript']
                    transcript_obj = Transcript(**transcript_data)
                    # Add audio URL
                    audio_url = f"/api/uploads/{transcript_id}_{file.filename}"
                    transcript_obj.audio_url = audio_url
                    _transcripts[transcript_id] = transcript_obj
                    
                    # Send audio_url as a separate event for frontend
                    yield f"data: {json.dumps({'type': 'audio_url', 'audio_url': audio_url, 'transcript_id': transcript_id})}\n\n"
                    logger.info(f"Streaming transcription completed: transcript_id={transcript_id}")

            except Exception as e:
                logger.error(f"Streaming transcription error: {e}", exc_info=True)
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

        return StreamingResponse(
            stream_transcription(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Cache-Control"
            }
        )

    except Exception as e:
        logger.error(f"Exception during streaming transcription setup: {e}", exc_info=True)
        # Cleanup file if setup failed
        if file_path.exists():
            try:
                file_path.unlink()
                logger.info(f"Cleaned up file after failure: {file_path}")
            except Exception as cleanup_exc:
                logger.error(f"Failed to cleanup file: {file_path}, error: {cleanup_exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Streaming transcription setup failed: {str(e)}"
        )

@router.get("/stream/{transcript_id}")
async def stream_transcription_status(transcript_id: str):
    """Stream transcription progress for existing transcript (placeholder for progress tracking)."""
    
    async def generate_progress():
        # Check if transcript exists
        if transcript_id in _transcripts:
            transcript_data = _transcripts[transcript_id].dict()
            yield f"data: {json.dumps({'type': 'complete', 'transcript': transcript_data})}\n\n"
        else:
            yield f"data: {json.dumps({'type': 'error', 'error': 'Transcript not found'})}\n\n"
    
    return StreamingResponse(
        generate_progress(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        }
    )

@router.get("/{transcript_id}", response_model=Transcript)
async def get_transcript(transcript_id: str) -> Transcript:
    """Get a transcript by ID."""
    if transcript_id not in _transcripts:
        raise HTTPException(
            status_code=404,
            detail="Transcript not found"
        )
    
    transcript = _transcripts[transcript_id]
    
    # Fix audio URL format if it doesn't have the /api prefix
    if transcript.audio_url and not transcript.audio_url.startswith('/api/uploads/'):
        if transcript.audio_url.startswith('/uploads/'):
            transcript.audio_url = '/api' + transcript.audio_url
            _transcripts[transcript_id] = transcript  # Update in memory
    
    return transcript

@router.get("/", response_model=list[Transcript])
async def list_transcripts() -> list[Transcript]:
    """List all transcripts."""
    transcripts = []
    for transcript_id, transcript in _transcripts.items():
        # Fix audio URL format if it doesn't have the /api prefix
        if transcript.audio_url and not transcript.audio_url.startswith('/api/uploads/'):
            if transcript.audio_url.startswith('/uploads/'):
                transcript.audio_url = '/api' + transcript.audio_url
                _transcripts[transcript_id] = transcript  # Update in memory
        transcripts.append(transcript)
    
    return transcripts

async def cleanup_file(file_path: Path):
    """Background task to cleanup uploaded files."""
    try:
        if file_path.exists():
            file_path.unlink()
    except Exception:
        pass  # Ignore cleanup errors
