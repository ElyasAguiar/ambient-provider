/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * Shared schemas and types between frontend and backend
 */
import { z } from 'zod'

// Transcript types
export const TranscriptSegmentSchema = z.object({
  start: z.number(),
  end: z.number(),
  text: z.string(),
  speaker_tag: z.number().optional(),
  confidence: z.number().optional(),
})

export const TranscriptSchema = z.object({
  id: z.string(),
  segments: z.array(TranscriptSegmentSchema),
  language: z.string().default('en-US'),
  duration: z.number().optional(),
  created_at: z.string(),
  filename: z.string().optional(),
  audio_url: z.string().optional(),
  speaker_roles: z.record(z.string()).optional(),
})

// Note types
export const NoteRequestSchema = z.object({
  transcript_id: z.string(),
  template_name: z.string(),
  custom_sections: z.array(z.string()).optional(),
  system_instructions: z.string().optional(),
  include_traces: z.boolean().default(true),
})

export const CitationSchema = z.object({
  text: z.string(),
  start_time: z.number(),
  end_time: z.number(),
  segment_id: z.string().optional(),
})

export const TraceEventSchema = z.object({
  timestamp: z.string(),
  event_type: z.string(),
  message: z.string(),
  metadata: z.record(z.any()).optional(),
})

export const NoteResponseSchema = z.object({
  id: z.string().optional(), // Add ID for note identification
  note_markdown: z.string(),
  trace_events: z.array(TraceEventSchema),
  citations: z.array(CitationSchema),
  template_used: z.string(),
  generation_time: z.number(),
  created_at: z.string(),
  transcript_id: z.string().optional(), // Link back to transcript
  title: z.string().optional(), // Display title for the note
})

// Template types
export const TemplateInfoSchema = z.object({
  name: z.string(),
  display_name: z.string(),
  description: z.string(),
  sections: z.array(z.string()),
  is_custom: z.boolean().default(false),
})

export const TemplateRequestSchema = z.object({
  name: z.string(),
  display_name: z.string(),
  description: z.string(),
  template_content: z.string(),
  sections: z.array(z.string()),
})

// API Response types
export const ErrorResponseSchema = z.object({
  error: z.string(),
  detail: z.string().optional(),
  code: z.string().optional(),
})

export const HealthResponseSchema = z.object({
  status: z.string(),
  timestamp: z.string(),
  version: z.string(),
  services: z.record(z.string()),
})

export const SuggestionResponseSchema = z.object({
  suggestions: z.array(z.string()),
  context: z.string().optional(),
})

// Type exports
export type TranscriptSegment = z.infer<typeof TranscriptSegmentSchema>
export type Transcript = z.infer<typeof TranscriptSchema>
export type NoteRequest = z.infer<typeof NoteRequestSchema>
export type Citation = z.infer<typeof CitationSchema>
export type TraceEvent = z.infer<typeof TraceEventSchema>
export type NoteResponse = z.infer<typeof NoteResponseSchema>
export type TemplateInfo = z.infer<typeof TemplateInfoSchema>
export type TemplateRequest = z.infer<typeof TemplateRequestSchema>
export type ErrorResponse = z.infer<typeof ErrorResponseSchema>
export type HealthResponse = z.infer<typeof HealthResponseSchema>
export type SuggestionResponse = z.infer<typeof SuggestionResponseSchema>

// Stream event types for real-time updates
export type StreamEvent = 
  | { type: 'trace'; event: string; message: string; timestamp: string; metadata?: Record<string, any> }
  | { type: 'section_complete'; section: string; content: string; timestamp: string }
  | { type: 'complete'; note_markdown: string; timestamp: string }
  | { type: 'error'; message: string; timestamp: string }
  | { type: 'progress'; progress: number; status: string; transcript?: Transcript }
