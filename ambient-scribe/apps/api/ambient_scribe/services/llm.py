# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Large Language Model service for note generation."""
import logging
from datetime import datetime
from typing import Any, AsyncGenerator, Dict

from ambient_scribe.deps import Settings, get_templates_dir
from ambient_scribe.models import NoteRequest, NoteResponse, TraceEvent, Transcript
from ambient_scribe.services.guardrails import (
    apply_input_guardrails,
    apply_output_guardrails,
    validate_privacy_compliance,
)
from ambient_scribe.services.templates import get_template_info, render_template
from ambient_scribe.utils.timecodes import format_timecode
from nemoguardrails import LLMRails, RailsConfig
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


async def generate_note_service(
    transcript: Transcript,
    request: NoteRequest,
    settings: Settings,
    stream: bool = True,  # Always stream
):
    """Build a medical note from a transcript using LLM reasoning with enhanced speaker tracking."""

    start_time = datetime.now()
    trace_events = []

    try:
        # Validate settings
        if not settings.nvidia_api_key:
            raise ValueError("NVIDIA API key not configured")
        if not settings.openai_base_url:
            raise ValueError("OpenAI base URL not configured")
        if not settings.llm_model:
            raise ValueError("LLM model not configured")

        # Initialize OpenAI client
        client = AsyncOpenAI(
            api_key=settings.nvidia_api_key, base_url=settings.openai_base_url
        )

        # Prepare transcript text with speaker roles
        transcript_text = format_transcript_with_speakers(transcript)

        # Apply input guardrails to protect patient information
        if settings.enable_guardrails:
            try:
                filtered_transcript = await apply_input_guardrails(
                    transcript_text, settings
                )
                if filtered_transcript != transcript_text:
                    trace_events.append(
                        TraceEvent(
                            event_type="guardrails_applied",
                            message="Input guardrails applied: sensitive information masked",
                            metadata={
                                "original_length": len(transcript_text),
                                "filtered_length": len(filtered_transcript),
                            },
                        )
                    )
                    transcript_text = filtered_transcript
                else:
                    trace_events.append(
                        TraceEvent(
                            event_type="guardrails_passed",
                            message="Input guardrails applied: no sensitive information detected",
                            metadata={"text_length": len(transcript_text)},
                        )
                    )
            except Exception as e:
                logger.warning(f"Input guardrails failed: {str(e)}")
                trace_events.append(
                    TraceEvent(
                        event_type="guardrails_error",
                        message=f"Input guardrails failed: {str(e)}",
                        metadata={"error": str(e)},
                    )
                )

        # Add trace event for transcript processing
        trace_events.append(
            TraceEvent(
                event_type="transcript_processed",
                message="Processed transcript with speaker identification",
                metadata={"num_segments": len(transcript.segments)},
            )
        )

        # Always use streaming for note generation
        async for event in stream_note_service(
            client, transcript_text, request, settings, trace_events
        ):
            yield event

    except Exception as e:
        trace_events.append(
            TraceEvent(event_type="error", message=f"Note generation failed: {str(e)}")
        )
        raise


async def stream_note_service(
    client: AsyncOpenAI,
    transcript_text: str,
    request: NoteRequest,
    settings: Settings,
    trace_events: list,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Stream note generation with real-time traces."""

    # Send initial trace
    yield {
        "type": "trace",
        "event": "started",
        "message": "Starting note generation...",
        "timestamp": datetime.now().isoformat(),
    }

    try:
        # Generate content with streaming
        note_content = {}

        # Determine sections from selected template
        sections: list[str] = []
        try:
            templates_dir = get_templates_dir()
            info = get_template_info(request.template_name, templates_dir)
            if info and info.sections:
                sections = [
                    s for s in info.sections if isinstance(s, str) and s.strip()
                ]
        except Exception:
            sections = []

        # Only fallback to SOAP defaults if we couldn't derive sections
        if not sections:
            logger.warning(
                f"Could not determine sections for template '{request.template_name}', using SOAP defaults"
            )
            sections = ["subjective", "objective", "assessment", "plan"]

        for section in sections:
            yield {
                "type": "trace",
                "event": "processing_section",
                "message": f"Processing {section.replace('_', ' ').title()} section...",
                "timestamp": datetime.now().isoformat(),
            }

            # Stream the section generation with real-time traces
            section_content = ""
            async for trace_event in generate_section_service(
                client, transcript_text, section, settings
            ):
                # Yield the streaming trace event
                yield {
                    "type": "trace",
                    "event": trace_event["event"],
                    "message": trace_event["message"],
                    "timestamp": trace_event["timestamp"],
                    "metadata": trace_event.get("metadata", {}),
                }

                # Capture the final section content
                if trace_event["event"] == "llm_reasoning_complete":
                    section_content = trace_event["metadata"].get("section_content", "")

            note_content[section] = section_content

            yield {
                "type": "section_complete",
                "section": section,
                "content": section_content,
                "timestamp": datetime.now().isoformat(),
            }

        # Render final note
        yield {
            "type": "trace",
            "event": "rendering",
            "message": "Rendering final note...",
            "timestamp": datetime.now().isoformat(),
        }

        rendered_note = render_template(
            request.template_name,
            **note_content,
            custom_sections=request.custom_sections,
        )

        # Apply output guardrails to final note
        if settings.enable_guardrails:
            yield {
                "type": "trace",
                "event": "guardrails_output",
                "message": "Applying output guardrails...",
                "timestamp": datetime.now().isoformat(),
            }

            try:
                filtered_note = await apply_output_guardrails(rendered_note, settings)

                # Validate privacy compliance
                validation_result = await validate_privacy_compliance(
                    filtered_note, settings
                )

                yield {
                    "type": "trace",
                    "event": "privacy_validation",
                    "message": validation_result["message"],
                    "timestamp": datetime.now().isoformat(),
                    "metadata": validation_result,
                }

                if filtered_note != rendered_note:
                    yield {
                        "type": "trace",
                        "event": "output_guardrails_applied",
                        "message": "Output guardrails applied: sensitive information masked",
                        "timestamp": datetime.now().isoformat(),
                        "metadata": {
                            "original_length": len(rendered_note),
                            "filtered_length": len(filtered_note),
                            "is_compliant": validation_result["is_compliant"],
                        },
                    }

                rendered_note = filtered_note

            except Exception as e:
                logger.warning(f"Output guardrails failed: {str(e)}")
                yield {
                    "type": "trace",
                    "event": "guardrails_error",
                    "message": f"Output guardrails failed: {str(e)}",
                    "timestamp": datetime.now().isoformat(),
                    "metadata": {"error": str(e)},
                }

        yield {
            "type": "complete",
            "note_markdown": rendered_note,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        yield {
            "type": "error",
            "message": str(e),
            "timestamp": datetime.now().isoformat(),
        }


async def generate_section_service(
    client: AsyncOpenAI, transcript_text: str, section: str, settings: Settings
) -> AsyncGenerator[Dict[str, Any], None]:
    """Generate content for a specific note section with streaming traces."""

    # Initialize NeMo Guardrails if enabled
    rails = None
    if settings.enable_guardrails and settings.guardrails_config_path:
        try:
            config = RailsConfig.from_path(settings.guardrails_config_path)
            rails = LLMRails(config)
        except Exception as e:
            logger.warning(f"Failed to initialize NeMo Guardrails: {str(e)}")

    section_prompts = {
        # Core SOAP sections
        "subjective": "Identify only the key subjective information (chief complaint, relevant symptoms, pertinent history). Exclude filler or repetition. Be concise. Do not include any other information.",
        "objective": "Extract objective findings (vitals, physical exam, observed data). Include only clear, factual observations. Avoid interpretation or speculation.",
        "assessment": "Summarize the clinical impression in 1–2 concise sentences. Highlight the main problem(s) and likely diagnosis. Avoid long differential lists unless essential.",
        "plan": "Outline a brief treatment and follow-up plan. Keep to essentials, no verbose explanation.",
        # Chief complaint and history sections
        "chief_complaint": "Extract the main reason for the visit in 1-2 sentences. Focus on what the patient states as their primary concern.",
        "history_present_illness": "Summarize the patient's description of their current problem, including onset, duration, and characteristics. Be concise.",
        "interval_history": "Extract what has happened since the last visit. Include changes in symptoms, treatments tried, or new concerns. Be brief.",
        "current_symptoms": "List current symptoms mentioned by the patient. Use bullet points if multiple symptoms. Be concise.",
        # Review and history sections
        "review_of_systems": "Extract any systematic review mentioned. If not performed, state 'Not performed'. Keep brief.",
        "past_medical_history": "Extract significant past medical conditions mentioned. If none discussed, state 'Not discussed'.",
        "medications": "List current medications mentioned. If none discussed, state 'Not discussed'.",
        "allergies": "Extract any allergies mentioned. If none stated, use 'NKDA' or 'Not discussed'.",
        "social_history": "Extract relevant social history (smoking, alcohol, occupation, etc.) if mentioned. Be brief.",
        # Physical examination sections
        "examination_findings": "Extract physical examination findings, vital signs, and objective observations. If no examination documented, state 'No examination findings documented'.",
        "objective": "Extract objective findings (vitals, physical exam, observed data). Include only clear, factual observations. Avoid interpretation or speculation.",
        # Care planning sections
        "follow_up": "Extract follow-up instructions or next appointment plans. Be specific but concise.",
        "medication_changes": "Identify any medication changes, additions, or discontinuations discussed. If none, state 'No changes discussed'.",
        "patient_education": "Extract any education or instructions given to the patient. If none provided, state 'None documented'.",
        "additional_notes": "Extract any other relevant information not covered in other sections. Keep brief.",
    }

    base_prompt = section_prompts.get(
        section, f"Extract {section} information from this transcript:"
    )
    system_message = settings.system_prompt

    # Enhanced prompt that encourages reasoning
    enhanced_prompt = f"""
    {system_message}
    
    For each section, you will be given a transcript of a patient's visit. You will need to extract the information for the section from the transcript.
    
    Please generate a reasoning trace with clear makrdonw and the final output of section contexts hould be a simple text paragraph description. 
    
    THE FINAL SECTION OUTPUT SHOULD BE A SIMPLE TEXT PARAGRAPH DESCRIPTION. DO NOT INCLUDE BULLET POINTS. TRY TO KEEP IT TO 2-3 SENTENCES.
    
    {base_prompt}

Please provide your reasoning process step by step, then give the final section content.

PLEASE FOLLOW THE FORMAT BELOW EXACTLY AS IT IS IMPORTANT FOR OUTPUT PARSING.

Format your response as:
REASONING:
[Your step-by-step analysis of the transcript for this section]

SECTION CONTENT:
[The final content for the {section} section in paragraph form]

Transcript:
{transcript_text}"""

    # Log the prompt being sent
    yield {
        "event": "llm_prompt_sent",
        "message": f"Sending prompt to LLM for {section} section",
        "timestamp": datetime.now().isoformat(),
        "metadata": {
            "section": section,
            "system_prompt": system_message,
            "user_prompt": (
                enhanced_prompt[:500] + "..."
                if len(enhanced_prompt) > 500
                else enhanced_prompt
            ),
            "model": settings.llm_model,
            "max_tokens": 1024,
            "temperature": 0.1,
        },
    }

    try:
        # Use NeMo Guardrails if enabled and initialized
        if rails is not None:
            messages = [{"role": "user", "content": enhanced_prompt}]
            stream = rails.stream_async(messages=messages)
        else:
            # Default OpenAI streaming
            stream = await client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": enhanced_prompt},
                ],
                max_tokens=1024,
                temperature=0.1,
                stream=True,
            )

        full_response = ""
        reasoning_buffer = ""
        content_buffer = ""
        in_reasoning = False
        in_content = False

        # Stream the LLM response chunk by chunk
        async for chunk in stream:
            # Handle different chunk formats for OpenAI vs NeMo Guardrails
            if rails is not None:
                chunk_content = chunk  # NeMo Guardrails returns text directly
                full_response += chunk_content
            else:
                chunk_content = (
                    chunk.choices[0].delta.content
                    if chunk.choices[0].delta.content
                    else ""
                )
                full_response += chunk_content

            # Check for section markers
            if "REASONING:" in full_response and not in_reasoning:
                in_reasoning = True
                yield {
                    "event": "llm_reasoning_start",
                    "message": f"LLM started reasoning for {section} section",
                    "timestamp": datetime.now().isoformat(),
                    "metadata": {"section": section, "partial_reasoning": ""},
                }

            if "SECTION CONTENT:" in full_response and not in_content:
                in_content = True
                in_reasoning = False
                yield {
                    "event": "llm_content_start",
                    "message": f"LLM started generating content for {section} section",
                    "timestamp": datetime.now().isoformat(),
                    "metadata": {
                        "section": section,
                        "reasoning": reasoning_buffer.replace("REASONING:", "")
                        .strip()
                        .replace("**", "")
                        .rstrip("*")
                        .lstrip(":")
                        .strip(),
                        "partial_content": "",
                    },
                }

            # Accumulate reasoning or content
            if in_reasoning and "SECTION CONTENT:" not in full_response:
                reasoning_buffer += chunk_content
                # Stream reasoning updates every few characters
                if len(reasoning_buffer) % 50 == 0:  # Update every 50 chars
                    yield {
                        "event": "llm_reasoning_stream",
                        "message": f"Streaming reasoning for {section} section",
                        "timestamp": datetime.now().isoformat(),
                        "metadata": {
                            "section": section,
                            "partial_reasoning": reasoning_buffer.replace(
                                "REASONING:", ""
                            )
                            .strip()
                            .replace("**", "")
                            .rstrip("*")
                            .lstrip(":")
                            .strip(),
                        },
                    }
            elif in_content:
                content_buffer += chunk_content
                # Stream content updates every few characters
                if len(content_buffer) % 30 == 0:  # Update every 30 chars
                    yield {
                        "event": "llm_content_stream",
                        "message": f"Streaming content for {section} section",
                        "timestamp": datetime.now().isoformat(),
                        "metadata": {
                            "section": section,
                            "partial_content": content_buffer.replace(
                                "SECTION CONTENT:", ""
                            )
                            .strip()
                            .replace("**", "")
                            .rstrip("*")
                            .strip(),
                        },
                    }

        # Parse the final reasoning and content
        reasoning = ""
        section_content = ""

        if "REASONING:" in full_response and "SECTION CONTENT:" in full_response:
            parts = full_response.split("SECTION CONTENT:")
            reasoning_part = parts[0].replace("REASONING:", "").strip()
            section_content = parts[1].strip()
            reasoning = reasoning_part
        else:
            # Fallback if the format isn't followed - try to extract just content without reasoning
            if "SECTION CONTENT:" in full_response:
                section_content = full_response.split("SECTION CONTENT:")[1].strip()
                reasoning = (
                    "LLM provided section content without explicit reasoning format"
                )
            else:
                section_content = full_response.strip()
                reasoning = "LLM did not provide explicit reasoning"

        # Clean up reasoning content to remove formatting artifacts
        if reasoning:
            # Remove markdown artifacts and unwanted formatting
            reasoning = reasoning.strip()
            # Remove standalone asterisks and clean up formatting
            reasoning = (
                reasoning.replace("**\n", "").replace("\n**", "").replace("**", "")
            )
            # Remove excessive newlines and spaces
            reasoning = "\n".join(
                line.strip() for line in reasoning.split("\n") if line.strip()
            )
            # Remove any trailing asterisks or formatting and leading colons
            reasoning = reasoning.rstrip("*").rstrip().lstrip("*").lstrip(":").strip()

        # Clean up section content to remove any unwanted formatting
        if section_content:
            # Remove any leading/trailing markdown formatting artifacts
            section_content = section_content.strip()
            # Remove any standalone asterisks or other formatting artifacts
            section_content = (
                section_content.replace("**\n", "")
                .replace("\n**", "")
                .replace("**", "")
            )

        # Apply output guardrails to section content
        if settings.enable_guardrails and section_content:
            try:
                filtered_content = await apply_output_guardrails(
                    section_content, settings
                )
                if filtered_content != section_content:
                    logger.info(f"Section {section} content filtered for privacy")
                section_content = filtered_content
            except Exception as e:
                logger.warning(
                    f"Section content filtering failed for {section}: {str(e)}"
                )

        # Final completion event
        yield {
            "event": "llm_reasoning_complete",
            "message": f"LLM completed reasoning for {section} section",
            "timestamp": datetime.now().isoformat(),
            "metadata": {
                "section": section,
                "reasoning": reasoning,
                "section_content": section_content,
                "usage": {
                    "prompt_tokens": 0,  # Streaming doesn't provide usage info immediately
                    "completion_tokens": 0,
                    "total_tokens": 0,
                },
            },
        }

    except Exception as e:
        yield {
            "event": "llm_error",
            "message": f"LLM call failed for {section} section: {str(e)}",
            "timestamp": datetime.now().isoformat(),
            "metadata": {
                "section": section,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        }


def format_transcript_with_speakers(transcript: Transcript) -> str:
    """Format transcript for LLM processing with enhanced speaker visualization."""

    formatted_text = []

    # Use stored speaker roles if available, otherwise fall back to keyword matching
    if transcript.speaker_roles:
        speaker_roles = {
            tag: role.title() for tag, role in transcript.speaker_roles.items()
        }
    else:
        speaker_roles = {}  # Track potential roles based on content

        # First pass - try to identify speaker roles
        for segment in transcript.segments:
            text_lower = segment.text.lower()
            if segment.speaker_tag:
                if any(
                    term in text_lower
                    for term in [
                        "my symptoms",
                        "i feel",
                        "i have been",
                        "i am experiencing",
                    ]
                ):
                    speaker_roles[segment.speaker_tag] = "Patient"
                elif any(
                    term in text_lower
                    for term in [
                        "recommend",
                        "prescribe",
                        "diagnosis",
                        "examination",
                        "assessment",
                    ]
                ):
                    speaker_roles[segment.speaker_tag] = "Provider"

    # Format transcript with roles
    for segment in transcript.segments:
        if segment.speaker_tag in speaker_roles:
            speaker = (
                f"{speaker_roles[segment.speaker_tag]} (Speaker {segment.speaker_tag})"
            )
        else:
            speaker = (
                f"Speaker {segment.speaker_tag}" if segment.speaker_tag else "Speaker"
            )

        # Format timestamp as MM:SS with clear formatting
        timestamp = f"**[{format_timecode(segment.start)}]**"

        formatted_text.append(f"{timestamp} {speaker}: {segment.text}")

    return "\n\n".join(formatted_text)  # Add extra newline for better readability
