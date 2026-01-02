# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unified transcription service supporting multiple ASR engines."""
import logging
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ambient_scribe.deps import Settings
from ambient_scribe.models import Transcript
from ambient_scribe.services.asr import transcribe_audio_file as asr_transcribe
from ambient_scribe.services.whisperx_service import (
    WhisperXClient,
    normalize_whisperx_response,
)

logger = logging.getLogger(__name__)


class TranscriptionEngine(str, Enum):
    """Supported transcription engines."""

    ASR = "asr"
    WHISPERX = "whisperx"


class TranscriptionService:
    """
    Unified service for audio transcription supporting multiple engines.

    This service abstracts the differences between NVIDIA Riva ASR and WhisperX,
    providing a consistent interface for transcription operations.
    """

    def __init__(self, settings: Settings):
        """
        Initialize transcription service.

        Args:
            settings: Application settings
        """
        self.settings = settings
        self._whisperx_client: Optional[WhisperXClient] = None

    @property
    def whisperx_client(self) -> WhisperXClient:
        """Lazy initialization of WhisperX client."""
        if self._whisperx_client is None:
            self._whisperx_client = WhisperXClient(
                base_url=self.settings.whisperx_service_url,
                timeout=self.settings.whisperx_timeout,
            )
        return self._whisperx_client

    async def transcribe(
        self,
        audio_path: Path,
        transcript_id: str,
        filename: str,
        engine: TranscriptionEngine,
        language: str = "en-US",
        context_id: Optional[UUID] = None,
        db: Optional[AsyncSession] = None,
        **engine_params,
    ) -> Transcript:
        """
        Transcribe audio file using specified engine.

        Args:
            audio_path: Path to audio file
            transcript_id: Unique transcript identifier
            filename: Original filename
            engine: Transcription engine to use
            language: Language code (e.g., 'en-US', 'pt-BR')
            context_id: Optional context for domain-specific processing
            db: Database session for context loading
            **engine_params: Engine-specific parameters

        Returns:
            Transcript object with segments

        Raises:
            ValueError: If engine is not supported or validation fails
            Exception: If transcription fails
        """
        logger.info(
            f"Starting transcription: engine={engine}, file={filename}, language={language}"
        )

        if engine == TranscriptionEngine.ASR:
            return await self.transcribe_with_asr(
                audio_path=audio_path,
                transcript_id=transcript_id,
                filename=filename,
                language=language,
                context_id=context_id,
                db=db,
            )
        elif engine == TranscriptionEngine.WHISPERX:
            return await self.transcribe_with_whisperx(
                audio_path=audio_path,
                transcript_id=transcript_id,
                filename=filename,
                language=language,
                context_id=context_id,
                **engine_params,
            )
        else:
            raise ValueError(f"Unsupported transcription engine: {engine}")

    async def transcribe_with_asr(
        self,
        audio_path: Path,
        transcript_id: str,
        filename: str,
        language: str,
        context_id: Optional[UUID] = None,
        db: Optional[AsyncSession] = None,
    ) -> Transcript:
        """
        Transcribe audio using NVIDIA Riva ASR.

        Args:
            audio_path: Path to audio file
            transcript_id: Unique transcript identifier
            filename: Original filename
            language: Language code (e.g., 'en-US')
            context_id: Optional context for word boosting
            db: Database session for context loading

        Returns:
            Transcript object

        Raises:
            Exception: If ASR transcription fails
        """
        logger.info(f"Transcribing with NVIDIA Riva ASR: {filename}")

        try:
            transcript = await asr_transcribe(
                file_path=audio_path,
                transcript_id=transcript_id,
                filename=filename,
                settings=self.settings,
                context_id=context_id,
                db=db,
            )

            logger.info(
                f"ASR transcription completed: {len(transcript.segments)} segments, "
                f"duration={transcript.duration:.2f}s"
            )

            return transcript

        except Exception as e:
            logger.error(f"ASR transcription failed for {filename}: {e}", exc_info=True)
            raise Exception(f"NVIDIA Riva ASR transcription failed: {str(e)}")

    async def transcribe_with_whisperx(
        self,
        audio_path: Path,
        transcript_id: str,
        filename: str,
        language: str,
        context_id: Optional[UUID] = None,
        model: str = "base",
        enable_diarization: bool = True,
        min_speakers: Optional[int] = None,
        max_speakers: Optional[int] = None,
    ) -> Transcript:
        """
        Transcribe audio using WhisperX.

        Args:
            audio_path: Path to audio file
            transcript_id: Unique transcript identifier
            filename: Original filename
            language: Language code (2-letter, e.g., 'en', 'pt')
            context_id: Optional context (not used by WhisperX currently)
            model: WhisperX model (tiny, base, small, medium, large-v2, large-v3)
            enable_diarization: Enable speaker diarization
            min_speakers: Minimum number of speakers
            max_speakers: Maximum number of speakers

        Returns:
            Transcript object

        Raises:
            Exception: If WhisperX transcription fails
        """
        logger.info(
            f"Transcribing with WhisperX: {filename}, model={model}, "
            f"diarization={enable_diarization}"
        )

        try:
            # Convert language code to 2-letter format for WhisperX
            # e.g., 'en-US' -> 'en', 'pt-BR' -> 'pt'
            whisperx_language = language.split("-")[0] if "-" in language else language

            # Call WhisperX service
            whisperx_response = await self.whisperx_client.transcribe_audio(
                audio_file_path=audio_path,
                model=model,
                language=whisperx_language,
                enable_diarization=enable_diarization,
                min_speakers=min_speakers,
                max_speakers=max_speakers,
            )

            # Normalize response to Transcript format
            transcript = normalize_whisperx_response(whisperx_response)
            transcript.id = transcript_id
            transcript.filename = filename

            logger.info(
                f"WhisperX transcription completed: {len(transcript.segments)} segments, "
                f"duration={transcript.duration:.2f}s"
            )

            return transcript

        except Exception as e:
            logger.error(f"WhisperX transcription failed for {filename}: {e}", exc_info=True)
            raise Exception(f"WhisperX transcription failed: {str(e)}")

    async def validate_asr_availability(self) -> Dict[str, Any]:
        """
        Check if NVIDIA Riva ASR service is available.

        Returns:
            Dictionary with status and details
        """
        try:
            # For ASR, we assume it's available if configured
            # Could add actual health check here if Riva provides one
            return {
                "engine": "asr",
                "available": True,
                "uri": self.settings.riva_uri,
                "model": self.settings.riva_model,
                "language": self.settings.riva_language,
            }
        except Exception as e:
            logger.error(f"ASR availability check failed: {e}")
            return {
                "engine": "asr",
                "available": False,
                "error": str(e),
            }

    async def validate_whisperx_availability(self) -> Dict[str, Any]:
        """
        Check if WhisperX service is available.

        Returns:
            Dictionary with status and details
        """
        try:
            health = await self.whisperx_client.health_check()

            return {
                "engine": "whisperx",
                "available": health.get("status") != "error",
                "url": self.settings.whisperx_service_url,
                "available_models": self.get_whisperx_models(),
                "health": health,
            }
        except Exception as e:
            logger.error(f"WhisperX availability check failed: {e}")
            return {
                "engine": "whisperx",
                "available": False,
                "error": str(e),
            }

    def get_whisperx_models(self) -> list[str]:
        """
        Get list of available WhisperX models.

        Returns:
            List of model names
        """
        models = self.settings.whisperx_available_models.split(",")
        return [m.strip() for m in models if m.strip()]

    def validate_whisperx_model(self, model: str) -> bool:
        """
        Validate if WhisperX model is available.

        Args:
            model: Model name to validate

        Returns:
            True if model is available
        """
        available_models = self.get_whisperx_models()
        return model in available_models

    def get_default_engine(self) -> TranscriptionEngine:
        """
        Get default transcription engine from settings.

        Returns:
            Default engine
        """
        default = getattr(self.settings, "default_transcription_engine", "asr").lower()

        try:
            return TranscriptionEngine(default)
        except ValueError:
            logger.warning(f"Invalid default engine '{default}', falling back to ASR")
            return TranscriptionEngine.ASR
