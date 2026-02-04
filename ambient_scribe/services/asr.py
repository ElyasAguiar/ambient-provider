# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Automatic Speech Recognition service using NVIDIA Riva."""
import io
import os

# Configure numba/librosa caching before importing librosa to avoid Docker issues
# Don't disable JIT entirely as it breaks librosa, just fix the caching
os.environ["NUMBA_CACHE_DIR"] = "/tmp/numba_cache"  # Set writable cache directory
os.environ["NUMBA_DISABLE_CACHING"] = "1"  # Disable caching to avoid permission issues

# Ensure cache directory exists and is writable
import pathlib

pathlib.Path("/tmp/numba_cache").mkdir(parents=True, exist_ok=True)

import asyncio
import json
import logging
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import UUID

import librosa
import riva.client
import riva.client.proto.riva_asr_pb2 as rasr
import soundfile as sf
from sqlalchemy.ext.asyncio import AsyncSession

from ambient_scribe.deps import Settings
from ambient_scribe.models.api.transcripts_schema import Transcript, TranscriptWord
from ambient_scribe.services.domain_manager import DomainManager

logger = logging.getLogger(__name__)


def serialize_for_json(data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert datetime objects to ISO format strings for JSON serialization."""
    serialized = {}
    for key, value in data.items():
        if isinstance(value, datetime):
            serialized[key] = value.isoformat()
        else:
            serialized[key] = value
    return serialized


async def detect_speaker_roles(transcript: Transcript, settings: Settings) -> dict:
    """Simple LLM call to detect which speaker ID is patient vs provider."""
    try:
        from openai import AsyncOpenAI

        # Prepare sample text from first few words (grouped by speaker)
        sample_speakers = {}
        for word in transcript.words[:100]:  # First 100 words
            if word.speaker:
                if word.speaker not in sample_speakers:
                    sample_speakers[word.speaker] = []
                sample_speakers[word.speaker].append(word.text)

        if not sample_speakers:
            return {}

        sample_segments = []
        for speaker, words in sample_speakers.items():
            sample_segments.append(f"Speaker {speaker}: {' '.join(words[:20])}")

        sample_text = "\n".join(sample_segments)

        prompt = f"""Analyze this medical conversation and determine which speaker is the patient and which is the provider/doctor. The speaker that is not the patient is most likely the doctor, so be generous.

{sample_text}

Return only a JSON object: {{"patient": "speaker_id", "provider": "speaker_id"}} where speaker_id is A, B, C, etc."""

        client = AsyncOpenAI(api_key=settings.nvidia_api_key, base_url=settings.openai_base_url)
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a medical transcript analyzer. Return only JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=50,
        )

        result_text = response.choices[0].message.content.strip()
        print(f"DEBUG: Speaker role detection result: {result_text}")
        result_json = json.loads(result_text)

        # Convert to our format: {speaker_id: "patient"/"provider"}
        speaker_roles = {}
        if "patient" in result_json:
            speaker_roles[str(result_json["patient"])] = "patient"
        if "provider" in result_json:
            speaker_roles[str(result_json["provider"])] = "provider"

        return speaker_roles

    except Exception as e:
        print(f"Warning: Speaker role detection failed: {e}")
        return {}


async def transcribe_audio_file(
    file_path: Path,
    transcript_id: str,
    filename: str,
    settings: Settings,
    context_id: Optional[UUID] = None,
    db: Optional[AsyncSession] = None,
) -> Transcript:
    """
    Transcribe an audio file using NVIDIA Riva ASR.

    Args:
        file_path: Path to the audio file
        transcript_id: Unique identifier for this transcript
        filename: Original filename
        settings: Application settings
        context_id: Optional context ID for domain-specific word boosting
        db: Optional database session for loading context configuration

    Returns:
        Transcript object with segments and speaker information
    """

    try:
        # Convert audio to WAV format if needed
        audio_data = convert_to_wav(file_path)

        # Set up Riva client
        if settings.self_hosted:
            print(f"Using self-hosted Riva URI: {settings.riva_uri}")
            auth = riva.client.Auth(uri=settings.riva_uri)
        else:
            print(f"Using NVIDIA Riva URI: {settings.riva_uri}")
            auth = riva.client.Auth(
                uri=settings.riva_uri,
                use_ssl=True,
                metadata_args=[
                    ["function-id", settings.riva_function_id],
                    ["authorization", f"Bearer {settings.nvidia_api_key}"],
                ],
            )

        # Create ASR service with timeout options
        asr_service = riva.client.ASRService(auth)

        # Configure recognition
        config = riva.client.RecognitionConfig(
            language_code=settings.riva_language,
            max_alternatives=1,
            enable_automatic_punctuation=True,
            enable_word_time_offsets=True,
            model=settings.riva_model,
        )

        # Set audio encoding parameters
        enc_enum = rasr.RecognitionConfig.DESCRIPTOR.fields_by_name["encoding"].enum_type
        config.encoding = enc_enum.values_by_name["LINEAR_PCM"].number
        config.sample_rate_hertz = 16000
        config.audio_channel_count = 1

        # Always enable speaker diarization to ensure UI can separate speakers
        riva.client.add_speaker_diarization_to_config(
            config, True, 2
        )  # 2 is just a hint, it is possible riva gives more

        # Load context-specific word boosting if context_id is provided
        if context_id and db:
            try:
                domain_manager = DomainManager(db)
                terms, scores = await domain_manager.load_word_boosting_terms(context_id)

                if terms and scores:
                    config.boosted_lm_words[:] = terms
                    config.boosted_lm_scores[:] = scores
                    logger.info(
                        f"Applied word boosting for context {context_id}: {len(terms)} terms loaded"
                    )
                else:
                    logger.info(f"No word boosting terms found for context {context_id}")
            except Exception as e:
                logger.warning(f"Failed to load word boosting for context {context_id}: {e}")
        else:
            logger.info("No context specified, using default ASR configuration")

        # Get audio bytes
        audio_data.seek(0)
        audio_bytes = audio_data.read()

        if len(audio_bytes) == 0:
            raise ValueError("Empty audio buffer")

        # Perform transcription
        response = asr_service.offline_recognize(audio_bytes, config)

        # Convert response to our format
        words = process_riva_response_to_words(response)

        # Build complete text
        text = " ".join(word.text for word in words)

        # Calculate total duration (convert from ms to seconds)
        duration = words[-1].end / 1000.0 if words else 0.0

        # Create transcript
        transcript = Transcript(
            id=transcript_id,
            words=words,
            text=text,
            language=settings.riva_language,
            duration=duration,
            filename=filename,
            created_at=datetime.now(),
        )

        # Detect speaker roles
        transcript.speaker_roles = await detect_speaker_roles(transcript, settings)

        print(f"DEBUG: Transcript speaker roles: {transcript.speaker_roles}")

        return transcript

    except Exception as e:
        raise Exception(f"ASR transcription failed: {str(e)}")


async def stream_transcribe_audio_file(
    file_path: Path,
    transcript_id: str,
    filename: str,
    settings: Settings,
    context_id: Optional[UUID] = None,
    db: Optional[AsyncSession] = None,
) -> AsyncGenerator[dict, None]:
    """
    Stream transcribe an audio file using NVIDIA Riva ASR with real-time updates.

    Args:
        file_path: Path to the audio file
        transcript_id: Unique identifier for this transcript
        filename: Original filename
        settings: Application settings
        context_id: Optional context ID for domain-specific word boosting
        db: Optional database session for loading context configuration

    Yields:
        Dictionary with streaming updates
    """

    try:
        # Check if streaming is enabled
        if not settings.enable_streaming:
            # Fall back to regular transcription
            print(f"Streaming is disabled, falling back to regular transcription")
            transcript = await transcribe_audio_file(
                file_path, transcript_id, filename, settings, context_id, db
            )
            transcript_dict = serialize_for_json(transcript.dict())

            yield {"type": "final", "transcript": transcript_dict}
            return

        # Set up Riva client
        if settings.self_hosted:
            print(f"Using self-hosted Riva URI for streaming: {settings.riva_uri}")
            auth = riva.client.Auth(uri=settings.riva_uri)
        else:
            print(f"Using NVIDIA Riva URI for streaming: {settings.riva_uri}")
            auth = riva.client.Auth(
                uri=settings.riva_uri,
                use_ssl=True,
                metadata_args=[
                    ["function-id", settings.riva_function_id],
                    ["authorization", f"Bearer {settings.nvidia_api_key}"],
                ],
            )
        asr_service = riva.client.ASRService(auth)

        # Handle audio format - convert MP3 to WAV if needed
        audio_file_to_use = str(file_path)
        temp_wav_file = None

        if str(file_path).endswith(".mp3"):
            print(f"Converting MP3 to WAV for streaming: {file_path}")
            y, sr = librosa.load(str(file_path), sr=16000, mono=True)
            wav_file = str(file_path).replace(".mp3", "_temp.wav")
            sf.write(wav_file, y, sr)
            audio_file_to_use = wav_file
            temp_wav_file = wav_file
            print(f"Temporary WAV file created: {wav_file}")

        # Configure streaming recognition
        config = riva.client.StreamingRecognitionConfig(
            config=riva.client.RecognitionConfig(
                language_code=settings.riva_language,
                max_alternatives=1,
                enable_automatic_punctuation=True,
                enable_word_time_offsets=True,
                sample_rate_hertz=16000,
                audio_channel_count=1,
                model=settings.riva_model,
            ),
            interim_results=True,
        )

        # Enable speaker diarization
        riva.client.add_speaker_diarization_to_config(config, True, 2)

        # Load context-specific word boosting if context_id is provided
        if context_id and db:
            try:
                domain_manager = DomainManager(db)
                terms, scores = await domain_manager.load_word_boosting_terms(context_id)

                if terms and scores:
                    config.config.boosted_lm_words[:] = terms
                    config.config.boosted_lm_scores[:] = scores
                    logger.info(
                        f"Applied word boosting for streaming with context {context_id}: {len(terms)} terms"
                    )
            except Exception as e:
                logger.warning(
                    f"Failed to load word boosting for streaming context {context_id}: {e}"
                )

        print(f"Starting streaming transcription of: {audio_file_to_use}")

        # Process streaming results
        current_speaker = None
        accumulated_text = ""
        processed_finals = set()
        words = []

        try:
            with riva.client.AudioChunkFileIterator(
                audio_file_to_use, settings.streaming_chunk_size
            ) as audio_chunk_iterator:

                for response in asr_service.streaming_response_generator(
                    audio_chunks=audio_chunk_iterator,
                    streaming_config=config,
                ):
                    if not response.results:
                        continue

                    for result in response.results:
                        if not result.alternatives:
                            continue

                        alternative = result.alternatives[0]
                        transcript = alternative.transcript.strip()

                        if not transcript:
                            continue

                        # Get speaker info
                        speaker = "Speaker"
                        speaker_tag = 0
                        if hasattr(alternative, "words") and alternative.words:
                            speaker_tags = []
                            for word in alternative.words:
                                if hasattr(word, "speaker_tag"):
                                    speaker_tags.append(word.speaker_tag)

                            if speaker_tags:
                                speaker_tag = Counter(speaker_tags).most_common(1)[0][0]
                                speaker = f"Speaker {chr(65 + speaker_tag)}"

                        if result.is_final:
                            # Create a unique key for this final result
                            result_key = f"{speaker}:{transcript}"

                            # Skip if we've already processed this exact final result
                            if result_key in processed_finals:
                                continue

                            processed_finals.add(result_key)

                            # Process individual words
                            if hasattr(alternative, "words") and alternative.words:
                                for word_obj in alternative.words:
                                    word_text = getattr(word_obj, "word", "").strip()
                                    if not word_text:
                                        continue

                                    # Get speaker
                                    word_speaker_tag = getattr(word_obj, "speaker_tag", speaker_tag)
                                    word_speaker = (
                                        chr(65 + word_speaker_tag)
                                        if word_speaker_tag is not None
                                        else "A"
                                    )

                                    # Get timestamps in milliseconds
                                    start_ms = (
                                        extract_time(word_obj.start_time) * 1000.0
                                        if hasattr(word_obj, "start_time")
                                        else 0.0
                                    )
                                    end_ms = (
                                        extract_time(word_obj.end_time) * 1000.0
                                        if hasattr(word_obj, "end_time")
                                        else 0.0
                                    )
                                    confidence = getattr(word_obj, "confidence", None)

                                    word = TranscriptWord(
                                        text=word_text,
                                        start=start_ms,
                                        end=end_ms,
                                        confidence=confidence,
                                        speaker=word_speaker,
                                    )
                                    words.append(word)

                            # Yield final segment update
                            yield {
                                "type": "final_segment",
                                "text": transcript,
                                "speaker": speaker,
                            }

                        else:
                            # Yield partial result
                            yield {
                                "type": "partial",
                                "text": transcript,
                                "speaker": speaker,
                            }

                        # Small delay to prevent overwhelming the client
                        await asyncio.sleep(0.01)

        finally:
            # Clean up temporary WAV file if we created one
            if temp_wav_file and Path(temp_wav_file).exists():
                Path(temp_wav_file).unlink()
                print(f"Cleaned up temporary file: {temp_wav_file}")

        # Build complete text
        text = " ".join(word.text for word in words)

        # Create final transcript object
        duration = words[-1].end / 1000.0 if words else 0.0

        transcript_obj = Transcript(
            id=transcript_id,
            words=words,
            text=text,
            language=settings.riva_language,
            duration=duration,
            filename=filename,
            created_at=datetime.now(),
        )

        # Detect speaker roles
        # transcript_obj.speaker_roles = await detect_speaker_roles(transcript_obj, settings)

        # Yield complete transcript
        transcript_dict = serialize_for_json(transcript_obj.dict())

        yield {"type": "complete", "transcript": transcript_dict}

        print("Streaming transcription completed.")

    except Exception as e:
        yield {"type": "error", "error": f"Streaming transcription failed: {str(e)}"}
        raise Exception(f"Streaming ASR transcription failed: {str(e)}")


def extract_time(time_obj) -> float:
    """Extract time from Riva time object."""
    try:
        if hasattr(time_obj, "seconds") and hasattr(time_obj, "nanos"):
            seconds = getattr(time_obj, "seconds", None)
            nanos = getattr(time_obj, "nanos", None)
            if seconds is not None and nanos is not None:
                return max(0.0, seconds + nanos / 1e9)

        if isinstance(time_obj, (int, float)):
            return max(0.0, float(time_obj))

        if hasattr(time_obj, "total_seconds"):
            return max(0.0, time_obj.total_seconds())

    except Exception:
        pass

    return 0.0


def convert_to_wav(file_path: Path) -> io.BytesIO:
    """Convert audio file to WAV format suitable for Riva."""

    try:
        # Load audio with librosa (supports many formats)
        y, sr = librosa.load(str(file_path), sr=None)

        # Resample to 16kHz if needed
        if sr != 16000:
            y = librosa.resample(y, orig_sr=sr, target_sr=16000)
            sr = 16000

        # Convert to mono if stereo
        if len(y.shape) > 1:
            y = librosa.to_mono(y)

        # Write to buffer
        wav_buffer = io.BytesIO()
        sf.write(wav_buffer, y, sr, format="wav")
        wav_buffer.seek(0)

        return wav_buffer

    except Exception as e:
        raise Exception(f"Audio conversion failed: {str(e)}")


def process_riva_response_to_words(response) -> List[TranscriptWord]:
    """Process Riva ASR response into transcript words."""

    print(f"DEBUG: Riva response: {response}")

    words = []

    # Convert speaker_tag (int) to speaker (A, B, C...)
    def speaker_tag_to_letter(tag: Optional[int]) -> str:
        if tag is None or tag < 0:
            return "A"
        return chr(65 + tag)  # 0->A, 1->B, 2->C, etc.

    try:
        for result in response.results:
            words_list = getattr(result.alternatives[0], "words", []) or []
            last_known_speaker = None

            for word in words_list:
                # Extract word text
                word_text = getattr(word, "word", "").strip()
                if not word_text:
                    continue

                # Get speaker tag
                if hasattr(word, "speaker_tag") and word.speaker_tag is not None:
                    speaker_tag = word.speaker_tag
                    last_known_speaker = speaker_tag
                else:
                    speaker_tag = last_known_speaker if last_known_speaker is not None else 0

                speaker = speaker_tag_to_letter(speaker_tag)

                # Get confidence
                confidence = getattr(word, "confidence", None)

                # Get timestamps and convert to milliseconds
                def safe_time_ms(get_time_attr):
                    try:
                        t = get_time_attr()

                        # Try different ways to extract time
                        if hasattr(t, "seconds") and hasattr(t, "nanos"):
                            seconds = getattr(t, "seconds", None)
                            nanos = getattr(t, "nanos", None)
                            if seconds is not None and nanos is not None:
                                time_val = seconds + nanos / 1e9
                                # Convert seconds to milliseconds
                                return max(0.0, time_val * 1000.0)

                        # Try if it's already a numeric value (assume seconds)
                        if isinstance(t, (int, float)):
                            time_val = float(t)
                            # Convert seconds to milliseconds
                            return max(0.0, time_val * 1000.0)

                        # Try if it has a total_seconds method
                        if hasattr(t, "total_seconds"):
                            time_val = t.total_seconds()
                            return max(0.0, time_val * 1000.0)

                    except Exception as e:
                        print(f"DEBUG: Exception in safe_time_ms: {e}")

                    return 0.0

                start_ms = safe_time_ms(lambda: word.start_time)
                end_ms = safe_time_ms(lambda: word.end_time)

                # Ensure end >= start
                if end_ms < start_ms:
                    end_ms = start_ms

                words.append(
                    TranscriptWord(
                        text=word_text,
                        start=start_ms,
                        end=end_ms,
                        confidence=confidence,
                        speaker=speaker,
                    )
                )

    except Exception as e:
        print(f"DEBUG: Exception processing words: {e}")
        pass

    # If we still have no words, try to extract from full transcript text
    if not words:
        full_text = " ".join(
            [
                getattr(result.alternatives[0], "transcript", "")
                for result in getattr(response, "results", [])
            ]
        ).strip()

        if full_text:
            # Split into words and create basic word entries
            word_texts = full_text.split()
            for i, word_text in enumerate(word_texts):
                words.append(
                    TranscriptWord(
                        text=word_text,
                        start=0.0,
                        end=0.0,
                        confidence=1.0,
                        speaker="A",
                    )
                )

    # Post-process to add estimated timestamps if all are 0
    if words and all(w.start == 0.0 and w.end == 0.0 for w in words):
        words = add_estimated_word_timestamps(words)

    return words


def add_estimated_word_timestamps(words: List[TranscriptWord]) -> List[TranscriptWord]:
    """Add estimated timestamps to words that have 0.0 timestamps."""
    if not words:
        return words

    # Estimate based on average speaking rate: ~150 words per minute = 2.5 words/sec = 400ms per word
    avg_word_duration_ms = 400.0
    current_time_ms = 0.0

    result = []
    for word in words:
        if word.start == 0.0 and word.end == 0.0:
            # Estimate duration based on word length (longer words take more time)
            estimated_duration = avg_word_duration_ms * (1 + len(word.text) / 10.0)
            result.append(
                TranscriptWord(
                    text=word.text,
                    start=current_time_ms,
                    end=current_time_ms + estimated_duration,
                    confidence=word.confidence,
                    speaker=word.speaker,
                )
            )
            current_time_ms += estimated_duration
        else:
            result.append(word)
            current_time_ms = max(current_time_ms, word.end)

    return result


def fix_inconsistent_timestamps(
    segments: List[TranscriptSegment],
) -> List[TranscriptSegment]:
    """Fix timestamps that are inconsistent or out of sequence."""

    if len(segments) < 2:
        return segments

    print("DEBUG: Checking for inconsistent timestamps")

    # Look for patterns that suggest wrong units or inconsistent timing
    issues_found = []

    for i in range(1, len(segments)):
        prev_segment = segments[i - 1]
        curr_segment = segments[i]

        # Check for time going backwards (should always increase)
        if curr_segment.start < prev_segment.start:
            issues_found.append(
                f"Time goes backwards: {prev_segment.start:.1f}s -> {curr_segment.start:.1f}s"
            )

        # Check for unreasonably large jumps (> 30 minutes between segments)
        time_gap = curr_segment.start - prev_segment.start
        if time_gap > 1800:  # 30 minutes
            issues_found.append(f"Large time gap: {time_gap:.1f}s between segments {i-1} and {i}")

        # Check for segments that are very long (> 5 minutes)
        duration = curr_segment.end - curr_segment.start
        if duration > 300:  # 5 minutes
            issues_found.append(f"Very long segment: {duration:.1f}s for segment {i}")

    if issues_found:
        print(f"DEBUG: Found {len(issues_found)} timestamp issues:")
        for issue in issues_found:
            print(f"  - {issue}")

        # If we have major issues, regenerate all timestamps based on text length
        print("DEBUG: Regenerating all timestamps based on text length")
        return regenerate_timestamps_from_text(segments)

    return segments


def regenerate_timestamps_from_text(
    segments: List[TranscriptSegment],
) -> List[TranscriptSegment]:
    """Regenerate timestamps based on text length and speaking rate."""

    print("DEBUG: Regenerating timestamps from text analysis")

    # Average speaking rate: ~150 words per minute = 2.5 words per second
    words_per_second = 2.5

    current_time = 0.0
    new_segments = []

    for i, segment in enumerate(segments):
        word_count = len(segment.text.split())
        duration = max(1.0, word_count / words_per_second)  # Minimum 1 second per segment

        new_segment = TranscriptSegment(
            start=current_time,
            end=current_time + duration,
            text=segment.text,
            speaker_tag=segment.speaker_tag,
            confidence=segment.confidence,
        )

        new_segments.append(new_segment)
        current_time += duration + 0.5  # Add 0.5 second pause between segments

        print(f"DEBUG: Regenerated segment {i}: {new_segment.start:.1f}s - {new_segment.end:.1f}s")

    return new_segments


def add_estimated_timestamps(
    segments: List[TranscriptSegment],
) -> List[TranscriptSegment]:
    """Add estimated timestamps to segments that have 0 timestamps."""

    if not segments:
        return segments

    # Check if all segments have 0 timestamps
    all_zero = all(seg.start == 0.0 and seg.end == 0.0 for seg in segments)

    if all_zero:
        print("DEBUG: All timestamps are 0, adding estimated timestamps")

        # Estimate based on text length and average speaking rate
        # Average speaking rate: ~150 words per minute = 2.5 words per second
        words_per_second = 2.5

        current_time = 0.0
        for i, segment in enumerate(segments):
            word_count = len(segment.text.split())
            duration = max(1.0, word_count / words_per_second)  # Minimum 1 second per segment

            segments[i] = TranscriptSegment(
                start=current_time,
                end=current_time + duration,
                text=segment.text,
                speaker_tag=segment.speaker_tag,
                confidence=segment.confidence,
            )

            current_time += duration + 0.5  # Add 0.5 second pause between segments
            print(
                f"DEBUG: Estimated segment {i}: {segments[i].start:.1f}s - {segments[i].end:.1f}s"
            )

    return segments


# Mock transcription function for testing without Riva
async def mock_transcribe_audio_file(
    file_path: Path, transcript_id: str, filename: str, settings: Settings
) -> Transcript:
    """Mock transcription for testing purposes."""

    # Simulate processing time
    import asyncio

    await asyncio.sleep(2)

    # Create mock transcript segments
    segments = [
        TranscriptSegment(
            start=0.0,
            end=15.0,
            text="Good morning, how are you feeling today?",
            speaker_tag=1,  # Doctor
            confidence=0.95,
        ),
        TranscriptSegment(
            start=15.5,
            end=32.0,
            text="I've been having some chest pain and shortness of breath for the past few days.",
            speaker_tag=2,  # Patient
            confidence=0.92,
        ),
        TranscriptSegment(
            start=33.0,
            end=48.0,
            text="Can you describe the chest pain? Is it sharp, dull, or crushing?",
            speaker_tag=1,  # Doctor
            confidence=0.97,
        ),
        TranscriptSegment(
            start=49.0,
            end=65.0,
            text="It's more of a dull ache, and it gets worse when I walk up stairs.",
            speaker_tag=2,  # Patient
            confidence=0.94,
        ),
    ]

    # Create transcript
    transcript = Transcript(
        id=transcript_id,
        segments=segments,
        language="en-US",
        duration=65.0,
        filename=filename,
        created_at=datetime.now(),
    )

    # Detect speaker roles
    transcript.speaker_roles = await detect_speaker_roles(transcript, settings)

    return transcript
