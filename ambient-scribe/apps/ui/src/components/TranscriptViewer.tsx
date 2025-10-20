/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState, useEffect, useRef } from 'react'
import { Transcript, TranscriptSegment } from '@/lib/schema'
import { MessageSquare, Clock, User, Loader2, FileText, ChevronDown } from 'lucide-react'

interface TranscriptViewerProps {
  transcript: Transcript | null
  isLoading: boolean
  currentPartial?: {text: string, speaker: string, speaker_tag?: number} | null
  onSeekToTime?: (seconds: number) => void
  onInsertTimestamp?: (timestamp: number) => void // Add callback for timestamp insertion
}

export function TranscriptViewer({ transcript, isLoading, currentPartial, onSeekToTime, onInsertTimestamp }: TranscriptViewerProps) {
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(null)
  const [newSegmentIds, setNewSegmentIds] = useState<Set<string>>(new Set())
  const [isUserScrolling, setIsUserScrolling] = useState<boolean>(false)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const prevSegmentCountRef = useRef<number>(0)
  const scrollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Check if user is near the bottom of the scroll container
  const isNearBottom = () => {
    if (!scrollContainerRef.current) return false
    const { scrollTop, scrollHeight, clientHeight } = scrollContainerRef.current
    const threshold = 100 // pixels from bottom
    return scrollHeight - scrollTop - clientHeight < threshold
  }

  // Handle scroll events to detect user scrolling and auto-rejoin when back at bottom
  useEffect(() => {
    const scrollContainer = scrollContainerRef.current
    if (!scrollContainer) return

    const handleScroll = () => {
      // Clear existing timeout
      if (scrollTimeoutRef.current) {
        clearTimeout(scrollTimeoutRef.current)
      }

      // Check if user has scrolled back to the bottom
      if (isNearBottom()) {
        // User is back at the bottom, immediately rejoin the stream
        setIsUserScrolling(false)
      } else {
        // Mark as user scrolling
        setIsUserScrolling(true)

        // Reset user scrolling flag after 1 second of no scrolling (but only if still not at bottom)
        scrollTimeoutRef.current = setTimeout(() => {
          // Double-check they're still not at bottom before clearing the flag
          if (!isNearBottom()) {
            setIsUserScrolling(false)
          }
        }, 1000)
      }
    }

    scrollContainer.addEventListener('scroll', handleScroll, { passive: true })
    
    return () => {
      scrollContainer.removeEventListener('scroll', handleScroll)
      if (scrollTimeoutRef.current) {
        clearTimeout(scrollTimeoutRef.current)
      }
    }
  }, [])

  // Auto-scroll to bottom when new segments are added during streaming (only if user isn't scrolling and is near bottom)
  useEffect(() => {
    if (transcript && isLoading) {
      const currentSegmentCount = transcript.segments.length
      if (currentSegmentCount > prevSegmentCountRef.current) {
        // Only auto-scroll if user isn't actively scrolling and is near the bottom
        if (!isUserScrolling && isNearBottom() && scrollContainerRef.current) {
          scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight
        }
        
        // Mark new segments for animation
        const newSegments = transcript.segments.slice(prevSegmentCountRef.current)
        const newIds = new Set(newSegments.map((_, index) => 
          `seg_${prevSegmentCountRef.current + index}`
        ))
        setNewSegmentIds(newIds)
        
        // Clear animation after 2 seconds
        setTimeout(() => {
          setNewSegmentIds(new Set())
        }, 2000)
      }
      prevSegmentCountRef.current = currentSegmentCount
    }
  }, [transcript?.segments.length, isLoading, isUserScrolling])

  // Auto-scroll when partial transcript updates (only if user isn't scrolling and is near bottom)
  useEffect(() => {
    if (currentPartial && isLoading && !isUserScrolling && isNearBottom() && scrollContainerRef.current) {
      scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight
    }
  }, [currentPartial?.text, isLoading, isUserScrolling])

  // Detect and fix timestamp inconsistencies on the frontend
  const normalizeTranscriptTimestamps = (transcript: Transcript) => {
    if (!transcript?.segments || transcript.segments.length < 2) return transcript

    // Check for major inconsistencies (time going backwards, huge jumps)
    let hasIssues = false
    for (let i = 1; i < transcript.segments.length; i++) {
      const prev = transcript.segments[i-1]
      const curr = transcript.segments[i]
      
      // Time going backwards or huge gaps (> 30 min)
      if (curr.start < prev.start || (curr.start - prev.start) > 1800) {
        hasIssues = true
        console.warn(`Timestamp issue detected: ${prev.start}s -> ${curr.start}s`)
        break
      }
    }

    if (hasIssues) {
      console.warn('Fixing inconsistent timestamps with text-based estimation')
      
      // Regenerate timestamps based on text length
      const wordsPerSecond = 2.5
      let currentTime = 0
      
      const fixedSegments = transcript.segments.map((segment) => {
        const wordCount = segment.text.split(' ').length
        const duration = Math.max(1.0, wordCount / wordsPerSecond)
        
        const fixedSegment = {
          ...segment,
          start: currentTime,
          end: currentTime + duration
        }
        
        currentTime += duration + 0.5 // 0.5s pause between segments
        return fixedSegment
      })

      return {
        ...transcript,
        segments: fixedSegments
      }
    }

    return transcript
  }

  // Apply timestamp normalization and combine consecutive same-speaker segments
  const normalizeAndCombineTranscript = (transcript: Transcript) => {
    if (!transcript?.segments || transcript.segments.length < 2) return transcript

    // First normalize timestamps
    const normalizedTranscript = normalizeTranscriptTimestamps(transcript)
    
    // Then combine consecutive segments from the same speaker
    const segments = normalizedTranscript.segments
    const combined = []
    let currentSegment = { ...segments[0] }
    
    for (let i = 1; i < segments.length; i++) {
      const nextSegment = segments[i]
      
      // Combine if same speaker and within reasonable time gap (30 seconds)
      const isSameSpeaker = currentSegment.speaker_tag === nextSegment.speaker_tag
      const timeGap = nextSegment.start - currentSegment.end
      const shouldCombine = isSameSpeaker && timeGap <= 30.0
      
      if (shouldCombine) {
        // Combine segments
        currentSegment = {
          ...currentSegment,
          text: currentSegment.text + ' ' + nextSegment.text,
          end: nextSegment.end,
          confidence: nextSegment.confidence || currentSegment.confidence
        }
        console.log(`[UI COMBINE] Merged segments from speaker ${currentSegment.speaker_tag}, gap: ${timeGap.toFixed(1)}s`)
      } else {
        // Different speaker or too far apart - finalize current segment
        combined.push(currentSegment)
        currentSegment = { ...nextSegment }
      }
    }
    
    // Add the last segment
    combined.push(currentSegment)
    
    console.log(`[UI COMBINE] Combined ${segments.length} segments into ${combined.length} segments`)
    
    return {
      ...normalizedTranscript,
      segments: combined
    }
  }

  const formatTimestamp = (seconds: number) => {
    if (!Number.isFinite(seconds) || seconds < 0) return '00:00'
    
    // Validate and convert if timestamp seems to be in wrong units
    let normalizedSeconds = seconds
    
    // More aggressive detection: if > 3600 seconds (1 hour), it's probably wrong for typical conversations
    if (seconds > 3600) { 
      console.warn(`Large timestamp detected: ${seconds}s, attempting conversion`)
      
      // Try different conversion factors
      const candidates = [
        { factor: 1000, name: 'milliseconds' },
        { factor: 1000000, name: 'microseconds' },
        { factor: 1000000000, name: 'nanoseconds' },
        { factor: 60, name: 'minutes to seconds' } // Sometimes timestamps are in minutes
      ]
      
      for (const { factor, name } of candidates) {
        const converted = seconds / factor
        if (converted >= 0 && converted <= 3600) { // Reasonable range: 0 to 1 hour
          normalizedSeconds = converted
          console.warn(`Converted from ${name}: ${normalizedSeconds}s`)
          break
        }
      }
      
      // If still unreasonable, estimate based on position in sequence
      if (normalizedSeconds > 3600) {
        console.error(`Could not normalize large timestamp: ${seconds}s, using fallback`)
        return '??:??'
      }
    }
    
    // Ensure we're working with a valid number
    const safeSeconds = Math.max(0, normalizedSeconds)
    const minutes = Math.floor(safeSeconds / 60)
    const remainingSeconds = Math.floor(safeSeconds % 60)
    
    // Always return MM:SS format, never just seconds
    return `${minutes.toString().padStart(2, '0')}:${remainingSeconds.toString().padStart(2, '0')}`
  }

  const getSpeakerLabel = (speakerTag?: number) => {
    // Use stored speaker roles if available
    console.warn(transcript?.speaker_roles)
    if (transcript?.speaker_roles && speakerTag !== undefined && transcript.speaker_roles[speakerTag]) {
      const role = transcript.speaker_roles[speakerTag]
      return role === 'patient' ? 'Patient' : role === 'provider' ? 'Provider' : `Speaker ${speakerTag}`
    }
    
    // Fallback to original hardcoded logic
    if (speakerTag === 0) return 'Provider'
    if (speakerTag === 1) return 'Patient'
    if (speakerTag !== undefined) return `Speaker ${speakerTag}`
    return 'Speaker'
  }

  const getSpeakerClasses = (speakerTag?: number) => {
    switch (speakerTag) {
      case 0:
        return {
          text: 'text-primary',
          icon: 'text-accent-blue',
          badgeBg: 'bg-accent-blue-subtle',
          border: 'border-accent-blue',
          ring: 'ring-accent-blue',
        }
      case 1:
        return {
          text: 'text-primary',
          icon: 'text-accent-green',
          badgeBg: 'bg-accent-green-subtle',
          border: 'border-accent-green',
          ring: 'ring-accent-green',
        }
      case 2:
        return {
          text: 'text-primary',
          icon: 'text-accent-purple',
          badgeBg: 'bg-accent-purple-subtle',
          border: 'border-accent-purple',
          ring: 'ring-accent-purple',
        }
      case undefined:
      case null:
        // Neutral color for partial transcripts without speaker identification
        return {
          text: 'text-primary',
          icon: 'text-primary',
          badgeBg: 'bg-surface-raised',
          border: 'border-base',
          ring: 'ring-base',
        }
      default:
        return {
          text: 'text-primary',
          icon: 'text-primary',
          badgeBg: 'bg-surface-raised',
          border: 'border-base',
          ring: 'ring-base',
        }
    }
  }

  const handleSegmentClick = (segment: TranscriptSegment) => {
    const segmentId = `seg_${segment.start}`
    setSelectedSegmentId(segmentId === selectedSegmentId ? null : segmentId)
    
    // Insert timestamp into note editor if callback is provided
    if (onInsertTimestamp) {
      onInsertTimestamp(segment.start)
    }
  }

  // Show loading state only if we don't have any segments yet
  if (isLoading && (!transcript || transcript.segments.length === 0)) {
    return (
      <div className="bg-surface-raised rounded-lg shadow h-full flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-base flex-shrink-0">
          <div className="flex items-center space-x-2">
            <FileText className="h-5 w-5 text-brand" />
            <h3 className="text-sm font-medium text-primary">Transcript</h3>
          </div>
        </div>
        
        {/* Loading State Content */}
        <div className="flex-1 flex items-center justify-center p-6">
          <div className="text-center">
            <Loader2 className="h-8 w-8 mx-auto mb-4 text-brand animate-spin" />
            <p className="text-sm text-secondary">Transcribing audio...</p>
            <p className="text-xs text-subtle">Real-time streaming transcription</p>
          </div>
        </div>
      </div>
    )
  }

  if (!transcript) {
    return (
      <div className="bg-surface-raised rounded-lg shadow h-full flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-base flex-shrink-0">
          <div className="flex items-center space-x-2">
            <FileText className="h-5 w-5 text-brand" />
            <h3 className="text-sm font-medium text-primary">Transcript</h3>
          </div>
        </div>
        
        {/* Empty State Content */}
        <div className="flex-1 flex items-center justify-center p-6">
          <div className="text-center text-secondary">
            <MessageSquare className="h-8 w-8 mx-auto mb-2 text-brand" />
            <p className="text-sm">No transcript available</p>
            <p className="text-xs text-subtle">Upload an audio file to get started</p>
          </div>
        </div>
      </div>
    )
  }

  // Apply timestamp normalization and segment combining
  const normalizedTranscript = normalizeAndCombineTranscript(transcript)

  return (
    <div className="bg-surface-raised rounded-lg shadow h-full flex flex-col relative">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-base flex-shrink-0">
        <div className="flex items-center space-x-2">
          <FileText className="h-5 w-5 text-brand" />
          <h3 className="text-sm font-medium text-primary">Transcript</h3>
          {isLoading && (
            <div className="flex items-center space-x-1">
              <Loader2 className="h-3 w-3 text-brand animate-spin" />
              <span className="text-xs text-brand font-medium">Live</span>
            </div>
          )}
        </div>
        
        <div className="flex items-center space-x-4 text-xs text-secondary">
          {normalizedTranscript.duration && (
            <div className="flex items-center space-x-1">
              <Clock className="h-3 w-3" />
              <span>{formatTimestamp(normalizedTranscript.duration)}</span>
            </div>
          )}
          {isLoading && (
            <span className="text-brand font-medium">Streaming...</span>
          )}
        </div>
      </div>

      {/* Transcript Content */}
      <div className="flex-1 overflow-y-auto" ref={scrollContainerRef}>
        {normalizedTranscript.segments.length > 0 ? (
          <div className="p-4 space-y-3">
            {normalizedTranscript.segments.map((segment, index) => {
              const segmentId = `seg_${index}` // Use index for consistency during streaming
              const isSelected = selectedSegmentId === segmentId
              const isNew = newSegmentIds.has(segmentId)
              const speakerClasses = getSpeakerClasses(segment.speaker_tag)
              
              return (
                <div
                  key={index}
                  className={`
                    transcript-segment cursor-pointer transition-all duration-500
                    ${isSelected ? `ring-2 ${speakerClasses.ring}` : ''}
                    ${isNew ? 'animate-pulse bg-accent-green-subtle border border-accent-green rounded-lg p-2' : 'p-2'}
                  `}
                  onClick={() => handleSegmentClick(segment)}
                >
                  {/* Segment Header */}
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center space-x-2">
                      <User className={`h-3 w-3 ${speakerClasses.icon}`} />
                      <span className={`text-xs font-medium ${speakerClasses.text}`}>
                        {getSpeakerLabel(segment.speaker_tag)}
                      </span>
                    </div>
                    
                    <button
                      className="transcript-timestamp flex items-center space-x-1 text-xs text-primary hover:text-brand transition-colors"
                      onClick={(e) => {
                        e.stopPropagation()
                        onSeekToTime?.(segment.start)
                      }}
                      title="Seek to this time in audio"
                    >
                      <Clock className="h-3 w-3" />
                       <span>{formatTimestamp(segment.start)}</span>
                    </button>
                  </div>

                  {/* Segment Text */}
                  <p className="text-sm text-primary leading-relaxed">
                    {segment.text}
                  </p>

                  {/* Expanded Details */}
                  {isSelected && (
                    <div className="mt-3 pt-3 border-t border-base">
                      <div className="grid grid-cols-2 gap-4 text-xs text-primary">
                        <div>
                          <span className="font-medium">Start:</span> {segment.start.toFixed(1)}s
                        </div>
                        <div>
                          <span className="font-medium">End:</span> {segment.end.toFixed(1)}s
                        </div>
                        {segment.confidence && (
                          <div>
                            <span className="font-medium">Confidence:</span>{' '}
                            {(segment.confidence * 100).toFixed(1)}%
                          </div>
                        )}
                        <div>
                          <span className="font-medium">Duration:</span>{' '}
                          {(segment.end - segment.start).toFixed(1)}s
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
            
            {/* Current Partial Transcript - Show in real-time */}
            {currentPartial && isLoading && (
              (() => {
                const speakerClasses = getSpeakerClasses(currentPartial.speaker_tag)
                return (
                  <div className={`p-3 ${speakerClasses.badgeBg} border ${speakerClasses.border} rounded-lg animate-pulse`}>
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center space-x-2">
                        <User className={`h-3 w-3 ${speakerClasses.icon}`} />
                      </div>
                      <div className={`flex items-center space-x-1 text-xs ${speakerClasses.text}`}>
                        <Loader2 className="h-3 w-3 animate-spin" />
                        <span>transcribing...</span>
                      </div>
                    </div>
                    <p className={`text-sm ${speakerClasses.text} leading-relaxed italic`}>
                      {currentPartial.text}
                    </p>
                  </div>
                )
              })()
            )}
          </div>
        ) : (
          <div className="p-6 text-center">
            {/* Show partial even when no segments exist yet */}
            {currentPartial && isLoading ? (
              <div className="space-y-4">
                {(() => {
                  const speakerClasses = getSpeakerClasses(currentPartial.speaker_tag)
                  return (
                    <div className={`p-4 ${speakerClasses.badgeBg} border ${speakerClasses.border} rounded-lg`}>
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center space-x-2">
                          <User className={`h-3 w-3 ${speakerClasses.icon}`} />
                        </div>
                        <div className={`flex items-center space-x-1 text-xs ${speakerClasses.text}`}>
                          <Loader2 className="h-3 w-3 animate-spin" />
                          <span>transcribing...</span>
                        </div>
                      </div>
                      <p className={`text-sm ${speakerClasses.text} leading-relaxed italic`}>
                        {currentPartial.text}
                      </p>
                    </div>
                  )
                })()}
                <div className="text-secondary">
                  <MessageSquare className="h-6 w-6 mx-auto mb-2 text-brand" />
                  <p className="text-xs">Listening for more speech...</p>
                </div>
              </div>
            ) : (
              <div className="text-secondary">
                <MessageSquare className="h-8 w-8 mx-auto mb-2 text-brand" />
                <p className="text-sm">No segments found</p>
                <p className="text-xs text-subtle">The transcript appears to be empty</p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Footer */}
      {normalizedTranscript.filename && (
        <div className="px-4 py-2 border-t border-base bg-surface-sunken flex-shrink-0">
          <p className="text-xs text-secondary">
            Source: {normalizedTranscript.filename} • {normalizedTranscript.language}
          </p>
        </div>
      )}

      {/* Scroll to Bottom Button - Show when user has scrolled up during streaming */}
      {isLoading && isUserScrolling && !isNearBottom() && (
        <button
          onClick={() => {
            if (scrollContainerRef.current) {
              scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight
              setIsUserScrolling(false) // Reset scrolling state to resume auto-scroll
            }
          }}
          className="absolute bottom-4 right-4 bg-brand text-inverse p-2 rounded-full shadow-lg hover:bg-brand/90 transition-colors z-10"
          title="Scroll to latest transcript"
        >
          <ChevronDown className="h-4 w-4" />
        </button>
      )}
    </div>
  )
}
