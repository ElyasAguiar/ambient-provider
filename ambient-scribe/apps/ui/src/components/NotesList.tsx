/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState, useEffect, useCallback } from 'react'
import { NoteResponse, Transcript } from '@/lib/schema'
import AmbientScribeAPI from '@/lib/api'
import { FileText, Calendar, Clock, Trash2, Plus, AlertCircle } from 'lucide-react'

interface NotesListProps {
  currentNoteId?: string
  onNoteSelect: (note: NoteResponse, transcript: Transcript) => void
  onNewNote: () => void
  onRefreshReady?: (refreshFn: () => void) => void
  onNoteDeleted?: (deletedNoteId: string) => void
  refreshTrigger?: number
}

interface NoteWithTranscript {
  note: NoteResponse
  transcript: Transcript | null
  isLocked: boolean // Whether this note is still generating
}

export function NotesList({ currentNoteId, onNoteSelect, onNewNote, onRefreshReady, onNoteDeleted, refreshTrigger }: NotesListProps) {
  const [notesWithTranscripts, setNotesWithTranscripts] = useState<NoteWithTranscript[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  const loadNotesAndTranscripts = async () => {
    try {
      setIsLoading(true)
      setError(null)
      
      console.log('NotesList: Starting to load notes and transcripts...')
      
      // Load notes and transcripts in parallel
      const [notes, transcripts] = await Promise.all([
        AmbientScribeAPI.listNotes(),
        AmbientScribeAPI.listTranscripts()
      ])

      console.log('NotesList: Loaded notes from API:', notes)
      console.log('NotesList: Notes count:', notes.length)
      console.log('NotesList: Loaded transcripts from API:', transcripts)
      console.log('NotesList: Transcripts count:', transcripts.length)

      // Create a map of transcript ID to transcript for quick lookup
      const transcriptMap = new Map(transcripts.map(t => [t.id, t]))

      // Combine notes with their transcripts
      const combined: NoteWithTranscript[] = notes.map(note => {
        const transcript = note.transcript_id ? transcriptMap.get(note.transcript_id) || null : null
        return {
          note: {
            ...note,
            id: note.id || `${note.transcript_id}_${note.template_used}`,
            title: note.title || generateNoteTitle(note, transcript)
          },
          transcript,
          isLocked: false // Will be updated based on generation state
        }
      })

      // Sort by creation date (newest first)
      combined.sort((a, b) => new Date(b.note.created_at).getTime() - new Date(a.note.created_at).getTime())

      console.log('NotesList: Combined notes with transcripts:', combined)
      console.log('NotesList: Setting notesWithTranscripts to:', combined.length, 'items')
      setNotesWithTranscripts(combined)
    } catch (err) {
      console.error('NotesList: Failed to load notes:', err)
      console.error('NotesList: Error details:', err instanceof Error ? err.message : String(err))
      setError(`Failed to load notes: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadNotesAndTranscripts()
  }, [refreshKey])

  // Respond to external refresh trigger
  useEffect(() => {
    if (refreshTrigger && refreshTrigger > 0) {
      console.log('NotesList: External refresh trigger received:', refreshTrigger)
      loadNotesAndTranscripts()
    }
  }, [refreshTrigger])

  // Expose refresh function for parent components
  const refreshNotes = useCallback(() => {
    console.log('NotesList: refreshNotes called, incrementing refreshKey')
    setRefreshKey(prev => prev + 1)
  }, [])
  
  useEffect(() => {
    if (onRefreshReady) {
      console.log('NotesList: Registering refresh function with parent component')
      onRefreshReady(refreshNotes)
    } else {
      console.log('NotesList: No onRefreshReady callback provided')
    }
  }, [onRefreshReady, refreshNotes])

  const generateNoteTitle = (note: NoteResponse, transcript: Transcript | null): string => {
    const templateDisplay = note.template_used.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())
    const date = new Date(note.created_at).toLocaleDateString()
    const filename = transcript?.filename || 'Unknown Audio'
    return `${templateDisplay} - ${filename} (${date})`
  }

  const formatRelativeTime = (dateString: string): string => {
    const date = new Date(dateString)
    const now = new Date()
    const diffInMs = now.getTime() - date.getTime()
    const diffInMinutes = Math.floor(diffInMs / (1000 * 60))
    const diffInHours = Math.floor(diffInMinutes / 60)
    const diffInDays = Math.floor(diffInHours / 24)

    if (diffInMinutes < 1) return 'Just now'
    if (diffInMinutes < 60) return `${diffInMinutes}m ago`
    if (diffInHours < 24) return `${diffInHours}h ago`
    if (diffInDays < 7) return `${diffInDays}d ago`
    return date.toLocaleDateString()
  }

  const handleDeleteNote = async (noteId: string, event: React.MouseEvent) => {
    event.stopPropagation()
    
    // Ask for confirmation
    if (!window.confirm('Are you sure you want to delete this note? This action cannot be undone.')) {
      return
    }
    
    try {
      console.log('Deleting note:', noteId)
      const result = await AmbientScribeAPI.deleteNote(noteId)
      console.log('Note deleted successfully:', result.message)
      
      // Refresh the notes list
      refreshNotes()
      
      // Notify parent if this was the currently viewed note
      if (onNoteDeleted) {
        onNoteDeleted(noteId)
      }
      
      // Show success message (you could replace this with a toast notification)
      console.log(`Deleted note: ${result.deleted_note_title}`)
      
    } catch (error) {
      console.error('Failed to delete note:', error)
      alert('Failed to delete note. Please try again.')
    }
  }

  if (isLoading) {
    return (
      <div className="p-4">
        <div className="flex items-center space-x-2 mb-4">
          <FileText className="h-5 w-5 text-brand" />
          <h2 className="text-lg font-medium text-primary">Previous Notes</h2>
        </div>
        <div className="space-y-2">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="bg-surface-sunken rounded-lg p-3 animate-pulse">
              <div className="h-4 bg-surface-base rounded w-3/4 mb-2"></div>
              <div className="h-3 bg-surface-base rounded w-1/2"></div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-4">
        <div className="flex items-center space-x-2 mb-4">
          <FileText className="h-5 w-5 text-brand" />
          <h2 className="text-lg font-medium text-primary">Previous Notes</h2>
        </div>
        <div className="bg-accent-red-subtle border border-accent-red rounded-lg p-3">
          <div className="flex items-center space-x-2 text-accent-red">
            <AlertCircle className="h-4 w-4" />
            <span className="text-sm">{error}</span>
          </div>
          <button
            onClick={loadNotesAndTranscripts}
            className="mt-2 text-sm text-accent-red hover:text-accent-red-hover underline"
          >
            Try again
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-2">
          <FileText className="h-5 w-5 text-brand" />
          <h2 className="text-lg font-medium text-primary">Previous Notes</h2>
        </div>
        <div className="flex items-center space-x-2">
          <button
            onClick={onNewNote}
            className="flex items-center space-x-1 text-sm text-brand hover:text-brand-hover font-medium"
          >
            <Plus className="h-4 w-4" />
            <span>New</span>
          </button>
        </div>
      </div>

      {/* Notes List */}
      <div className="space-y-2 max-h-80 overflow-y-auto">
        {notesWithTranscripts.length === 0 ? (
          <div className="text-center py-8 text-secondary">
            <FileText className="h-8 w-8 mx-auto mb-2 text-subtle" />
            <p className="text-sm">No notes yet</p>
            <p className="text-xs text-subtle">Generate your first note to see it here</p>
          </div>
        ) : (
          notesWithTranscripts.map(({ note, transcript, isLocked }) => (
            <button
              key={note.id}
              onClick={() => transcript && onNoteSelect(note, transcript)}
              className={`w-full text-left p-3 rounded-lg border transition-colors ${
                currentNoteId === note.id
                  ? 'bg-accent-blue-subtle border-accent-blue shadow-sm'
                  : 'bg-surface-raised border-base hover:bg-surface-sunken'
              } ${!transcript ? 'opacity-50 cursor-not-allowed' : ''}`}
              disabled={!transcript}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center space-x-2 mb-1">
                    <span className="text-sm font-medium text-primary truncate">
                      {note.title}
                    </span>
                    {isLocked && (
                      <div className="flex-shrink-0 w-2 h-2 bg-orange-500 rounded-full animate-pulse" />
                    )}
                  </div>
                  
                  <div className="flex items-center space-x-3 text-xs text-secondary">
                    <div className="flex items-center space-x-1">
                      <Calendar className="h-3 w-3" />
                      <span>{formatRelativeTime(note.created_at)}</span>
                    </div>
                    
                    <div className="flex items-center space-x-1">
                      <Clock className="h-3 w-3" />
                      <span>{Math.round(note.generation_time)}s</span>
                    </div>
                  </div>
                  
                  {transcript && (
                    <div className="mt-1 text-xs text-subtle truncate">
                      {transcript.filename} • {transcript.segments.length} segments
                    </div>
                  )}
                  
                  {!transcript && (
                    <div className="mt-1 text-xs text-accent-red">
                      Transcript not found
                    </div>
                  )}
                </div>
                
                <button
                  onClick={(e) => handleDeleteNote(note.id!, e)}
                  className="flex-shrink-0 p-1 text-secondary hover:text-accent-red rounded"
                  title="Delete note"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  )
}
