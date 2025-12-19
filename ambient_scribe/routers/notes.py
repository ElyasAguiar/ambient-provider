# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Notes generation router."""
import asyncio
import json
from datetime import datetime
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ambient_scribe.deps import get_settings
from ambient_scribe.models import (
    ErrorResponse,
    NoteRequest,
    NoteResponse,
    SuggestionResponse,
)
from ambient_scribe.routers.transcribe import _transcripts
from ambient_scribe.services.llm import generate_note_service
from ambient_scribe.services.suggestions import get_autocomplete_suggestions

router = APIRouter()

# In-memory storage for demo
_notes = {}


@router.get("/debug/transcripts")
async def debug_transcripts():
    """Debug endpoint to see all available transcripts."""
    return {
        "total_transcripts": len(_transcripts),
        "transcript_ids": list(_transcripts.keys()),
        "transcripts": {
            tid: {"filename": t.filename, "segments": len(t.segments)}
            for tid, t in _transcripts.items()
        },
    }


@router.post("/stream")
async def stream_note_endpoint(note_request: NoteRequest):
    """Stream note generation with real-time traces and speaker-aware formatting."""

    print(
        f"POST /stream - Received request: transcript_id={note_request.transcript_id}, template={note_request.template_name}"
    )
    print(f"Available transcripts: {list(_transcripts.keys())}")
    print(f"Total transcripts in memory: {len(_transcripts)}")

    if note_request.transcript_id not in _transcripts:
        print(f"Transcript {note_request.transcript_id} not found in _transcripts")
        print("This suggests either:")
        print("1. Transcription is still in progress")
        print("2. Transcription failed")
        print("3. Server was restarted (in-memory storage lost)")
        raise HTTPException(
            status_code=404,
            detail="Transcript not found. Please ensure transcription completed successfully.",
        )

    async def note_generation_handler():
        transcript = _transcripts[note_request.transcript_id]
        settings = get_settings()

        print(f"Starting note generation for transcript {note_request.transcript_id}")

        try:
            # Initial event with transcript info
            start_event = {
                "type": "start",
                "message": "Starting note generation",
                "metadata": {
                    "transcript_id": note_request.transcript_id,
                    "template": note_request.template_name,
                    "num_segments": len(transcript.segments),
                },
            }
            yield f"data: {json.dumps(start_event)}\n\n"

            # Track for final note storage
            final_note_markdown = None
            start_time = datetime.now()

            # Stream the note generation process
            async for event in generate_note_service(
                transcript=transcript,
                request=note_request,
                settings=settings,
                stream=True,
            ):
                # Capture the final note content when complete
                if event.get("type") == "complete":
                    final_note_markdown = event.get("note_markdown")
                    print(
                        f"Captured final note markdown, length: {len(final_note_markdown) if final_note_markdown else 0}"
                    )

                yield f"data: {json.dumps(event)}\n\n"

            # Store the completed note
            if final_note_markdown:
                note_id = f"{note_request.transcript_id}_{note_request.template_name}"
                template_display = note_request.template_name.replace("_", " ").title()
                transcript_filename = transcript.filename or "Audio Recording"
                generation_time = (datetime.now() - start_time).total_seconds()

                print(f"Saving note with ID: {note_id}")
                print(f"Note content length: {len(final_note_markdown)}")

                note_response = NoteResponse(
                    id=note_id,
                    note_markdown=final_note_markdown,
                    trace_events=[],  # Traces are sent via stream
                    citations=[],  # Citations not used in UI
                    template_used=note_request.template_name,
                    generation_time=generation_time,
                    created_at=datetime.now(),
                    transcript_id=note_request.transcript_id,
                    title=f"{template_display} - {transcript_filename}",
                )

                _notes[note_id] = note_response
                print(f"Note saved successfully. Total notes in storage: {len(_notes)}")
                print(f"Stored note IDs: {list(_notes.keys())}")
            else:
                print("WARNING: final_note_markdown is None or empty - note not saved!")

        except Exception as e:
            print(f"Error in note generation stream: {e}")
            error_event = {
                "type": "error",
                "message": str(e),
                "timestamp": datetime.now().isoformat(),
                "metadata": {
                    "error_type": type(e).__name__,
                    "transcript_id": note_request.transcript_id,
                },
            }
            yield f"data: {json.dumps(error_event)}\n\n"

        finally:
            # End event
            end_event = {
                "type": "end",
                "message": "Note generation complete",
                "timestamp": datetime.now().isoformat(),
            }
            yield f"data: {json.dumps(end_event)}\n\n"

    return StreamingResponse(
        note_generation_handler(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        },
    )


# Provide a GET variant for SSE via query params, matching client call pattern
@router.get("/stream")
async def stream_note_endpoint_get(
    transcript_id: str,
    template_name: str,
    include_traces: bool = True,
    system_instructions: str | None = None,
    custom_sections: List[str] | None = None,
):
    note_request = NoteRequest(
        transcript_id=transcript_id,
        template_name=template_name,
        include_traces=include_traces,
        system_instructions=system_instructions,
        custom_sections=custom_sections,
    )
    return await stream_note_endpoint(note_request)


@router.get("/suggest", response_model=SuggestionResponse)
async def get_suggestions(
    prefix: str,
    transcript_id: str = None,
    context: str = None,
    settings=Depends(get_settings),
) -> SuggestionResponse:
    """Get autocomplete suggestions for the given prefix."""

    transcript = None
    if transcript_id and transcript_id in _transcripts:
        transcript = _transcripts[transcript_id]

    try:
        suggestions = await get_autocomplete_suggestions(
            prefix=prefix, transcript=transcript, context=context, settings=settings
        )

        return SuggestionResponse(suggestions=suggestions, context=context)

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get suggestions: {str(e)}"
        )


@router.get("/{note_id}", response_model=NoteResponse)
async def get_note(note_id: str) -> NoteResponse:
    """Get a generated note by ID."""
    if note_id not in _notes:
        raise HTTPException(status_code=404, detail="Note not found")

    return _notes[note_id]


@router.get("/debug")
async def debug_notes():
    """Debug endpoint to check notes storage."""
    return {
        "total_notes": len(_notes),
        "note_ids": list(_notes.keys()),
        "notes_summary": [
            {
                "id": note.id,
                "transcript_id": note.transcript_id,
                "template": note.template_used,
                "title": note.title,
                "content_length": len(note.note_markdown),
            }
            for note in _notes.values()
        ],
    }


@router.get("/", response_model=List[NoteResponse])
async def list_notes() -> List[NoteResponse]:
    """List all generated notes."""
    print(f"API: Listing notes. Current storage has {len(_notes)} notes")
    print(f"API: Note IDs in storage: {list(_notes.keys())}")
    notes_list = list(_notes.values())
    print(f"API: Returning {len(notes_list)} notes to client")
    return notes_list


@router.delete("/{note_id}")
async def delete_note(note_id: str):
    """Delete a note by ID."""
    if note_id not in _notes:
        raise HTTPException(status_code=404, detail="Note not found")

    deleted_note = _notes.pop(note_id)
    print(f"API: Deleted note {note_id}. {len(_notes)} notes remaining")

    return {
        "message": f"Note {note_id} deleted successfully",
        "deleted_note_title": deleted_note.title,
    }
