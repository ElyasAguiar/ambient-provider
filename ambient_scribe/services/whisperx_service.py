# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""WhisperX ASR service client."""
import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import aiohttp

from ambient_scribe.deps import get_settings
from ambient_scribe.models import Transcript, TranscriptSegment

logger = logging.getLogger(__name__)

# In-memory job storage for demo (replace with Redis in production)
_whisperx_jobs: Dict[str, Dict[str, Any]] = {}


class WhisperXClient:
    """Client for communicating with WhisperX ASR service."""

    def __init__(self, base_url: str, timeout: int = 300):
        """Initialize WhisperX client."""
        self.base_url = base_url.rstrip("/")
        self.timeout = aiohttp.ClientTimeout(total=timeout)

    async def health_check(self) -> Dict[str, Any]:
        """Check WhisperX service health."""
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(f"{self.base_url}/health") as response:
                    if response.status == 200:
                        return await response.json()
                    return {"status": "error", "message": f"HTTP {response.status}"}
        except Exception as e:
            logger.error(f"WhisperX health check failed: {e}")
            return {"status": "error", "message": str(e)}

    async def transcribe_audio(
        self,
        audio_file_path: Path,
        model: str = "base",
        language: Optional[str] = None,
        enable_diarization: bool = True,
        min_speakers: Optional[int] = None,
        max_speakers: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Transcribe audio file using WhisperX service.

        Args:
            audio_file_path: Path to audio file
            model: WhisperX model name (tiny, base, small, medium, large-v2, large-v3)
            language: Optional language code (e.g., 'en', 'es')
            enable_diarization: Enable speaker diarization
            min_speakers: Minimum number of speakers
            max_speakers: Maximum number of speakers

        Returns:
            WhisperX transcription response
        """
        try:
            # Read file content first
            with open(audio_file_path, "rb") as f:
                file_content = f.read()

            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                # Prepare form data
                data = aiohttp.FormData()

                # Add audio file content
                data.add_field(
                    "audio_file",
                    file_content,
                    filename=audio_file_path.name,
                    content_type="audio/mpeg",
                )

                # Add parameters (matching WhisperX service /asr endpoint)
                data.add_field("model", model)
                data.add_field("task", "transcribe")
                data.add_field("word_timestamps", "true")
                data.add_field("output_format", "json")

                if language:
                    data.add_field("language", language)

                # Diarization parameters (as query params in URL or form data)
                if enable_diarization:
                    data.add_field("diarize", "true")
                    if min_speakers is not None:
                        data.add_field("min_speakers", str(min_speakers))
                    if max_speakers is not None:
                        data.add_field("max_speakers", str(max_speakers))

                # Make request to WhisperX
                async with session.post(
                    f"{self.base_url}/asr",
                    data=data,
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"WhisperX API error: {error_text}")

                    return await response.json()

        except Exception as e:
            logger.error(f"WhisperX transcription failed: {e}")
            raise


def normalize_whisperx_response(whisperx_data: Dict[str, Any]) -> Transcript:
    """
    Normalize WhisperX response to match Ambient-Provider Transcript format.

    Args:
        whisperx_data: Raw response from WhisperX API

    Returns:
        Normalized Transcript object
    """
    segments: List[TranscriptSegment] = []

    # WhisperX returns segments with speaker labels
    for segment in whisperx_data.get("segments", []):
        segments.append(
            TranscriptSegment(
                start=segment.get("start", 0.0),
                end=segment.get("end", 0.0),
                text=segment.get("text", "").strip(),
                speaker_tag=_parse_speaker_tag(segment.get("speaker")),
                confidence=segment.get("confidence"),
            )
        )

    # Build full transcript text
    full_text = " ".join(seg.text for seg in segments)

    # Create transcript
    transcript = Transcript(
        id=str(uuid4()),
        segments=segments,
        language=whisperx_data.get("language", "en"),
        duration=segments[-1].end if segments else 0.0,
        filename=None,  # Will be set by caller
    )

    return transcript


def _parse_speaker_tag(speaker: Optional[str]) -> Optional[int]:
    """
    Parse WhisperX speaker label to integer tag.

    WhisperX uses 'SPEAKER_00', 'SPEAKER_01', etc.
    Convert to 0, 1, 2, ...
    """
    if not speaker:
        return None

    try:
        # Extract number from 'SPEAKER_XX'
        if speaker.startswith("SPEAKER_"):
            return int(speaker.split("_")[1])
        return None
    except (IndexError, ValueError):
        return None


async def submit_whisperx_job(
    audio_file_path: Path,
    model: str = "base",
    language: Optional[str] = None,
    enable_diarization: bool = True,
    min_speakers: Optional[int] = None,
    max_speakers: Optional[int] = None,
) -> str:
    """
    Submit a WhisperX transcription job (async processing).

    Args:
        audio_file_path: Path to audio file
        model: WhisperX model name
        language: Optional language code
        enable_diarization: Enable speaker diarization
        min_speakers: Minimum number of speakers
        max_speakers: Maximum number of speakers

    Returns:
        Job ID for polling
    """
    settings = get_settings()
    job_id = str(uuid4())

    # Store job metadata
    _whisperx_jobs[job_id] = {
        "status": "processing",
        "progress": 0,
        "result": None,
        "error": None,
    }

    # Start processing in background
    asyncio.create_task(
        _process_whisperx_job(
            job_id,
            audio_file_path,
            model,
            language,
            enable_diarization,
            min_speakers,
            max_speakers,
        )
    )

    return job_id


async def _process_whisperx_job(
    job_id: str,
    audio_file_path: Path,
    model: str,
    language: Optional[str],
    enable_diarization: bool,
    min_speakers: Optional[int],
    max_speakers: Optional[int],
):
    """Background task to process WhisperX transcription."""
    try:
        settings = get_settings()
        client = WhisperXClient(
            settings.whisperx_service_url,
            timeout=settings.whisperx_timeout,
        )

        # Update progress
        _whisperx_jobs[job_id]["progress"] = 10

        # Transcribe
        logger.info(f"Starting WhisperX transcription for job {job_id}")
        whisperx_data = await client.transcribe_audio(
            audio_file_path,
            model=model,
            language=language,
            enable_diarization=enable_diarization,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
        )

        # Update progress
        _whisperx_jobs[job_id]["progress"] = 90

        # Normalize response
        transcript = normalize_whisperx_response(whisperx_data)
        transcript.filename = audio_file_path.name

        # Mark as completed
        _whisperx_jobs[job_id]["status"] = "completed"
        _whisperx_jobs[job_id]["progress"] = 100
        _whisperx_jobs[job_id]["result"] = transcript

        logger.info(f"WhisperX transcription completed for job {job_id}")

    except Exception as e:
        logger.error(f"WhisperX job {job_id} failed: {e}")
        _whisperx_jobs[job_id]["status"] = "failed"
        _whisperx_jobs[job_id]["error"] = str(e)


def get_whisperx_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    """
    Get status of a WhisperX job.

    Returns:
        Job status dict or None if job not found
    """
    return _whisperx_jobs.get(job_id)


def get_whisperx_job_result(job_id: str) -> Optional[Transcript]:
    """
    Get result of a completed WhisperX job.

    Returns:
        Transcript or None if not ready/found
    """
    job = _whisperx_jobs.get(job_id)
    if job and job["status"] == "completed":
        return job["result"]
    return None


def get_available_models() -> List[str]:
    """Get list of available WhisperX models from settings."""
    settings = get_settings()
    models = settings.whisperx_available_models.split(",")
    return [m.strip() for m in models if m.strip()]
