/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * API client for Ambient Scribe backend
 */
import axios from 'axios'
import { 
  Transcript, 
  NoteRequest, 
  NoteResponse, 
  TemplateInfo, 
  TemplateRequest,
  SuggestionResponse,
  HealthResponse,
  // ErrorResponse,
  StreamEvent
} from './schema'

// Configure axios defaults
const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Add response interceptor for error handling
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.data?.error) {
      throw new Error(error.response.data.error)
    }
    throw error
  }
)

export class AmbientScribeAPI {
  // Health endpoints
  static async healthCheck(): Promise<HealthResponse> {
    const response = await apiClient.get<HealthResponse>('/health/')
    return response.data
  }

  // Transcription endpoints
  static async transcribeFile(file: File): Promise<Transcript> {
    const formData = new FormData()
    formData.append('file', file)
    
    const response = await apiClient.post<Transcript>('/transcribe/file', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      timeout: 300000, // 5 minutes for transcription
    })
    
    return response.data
  }

  static createStreamingTranscriptionStream(file: File): EventSource {
    // Create a unique URL for the streaming request
    const formData = new FormData()
    formData.append('file', file)
    
    // For EventSource, we need to create a POST request to /transcribe/stream
    // Since EventSource only supports GET, we'll need to use a different approach
    // We'll use a custom implementation that supports POST with FormData
    
    const url = `${apiClient.defaults.baseURL}/transcribe/stream`
    
    // Create a custom EventSource-like implementation
    return this.createCustomEventSource(url, formData)
  }

  private static createCustomEventSource(url: string, formData: FormData): EventSource {
    // Create a custom EventSource implementation using fetch
    const controller = new AbortController()
    let eventSource: any = null
    
    const customEventSource = {
      onmessage: null as ((event: MessageEvent) => void) | null,
      onerror: null as ((event: Event) => void) | null,
      onopen: null as ((event: Event) => void) | null,
      readyState: EventSource.CONNECTING as number,
      close: () => {
        controller.abort()
        if (eventSource) {
          eventSource.readyState = EventSource.CLOSED
        }
      },
      CONNECTING: EventSource.CONNECTING,
      OPEN: EventSource.OPEN,
      CLOSED: EventSource.CLOSED,
    }

    // Start the fetch request
    fetch(url, {
      method: 'POST',
      body: formData,
      signal: controller.signal,
      headers: {
        'Accept': 'text/event-stream',
        'Cache-Control': 'no-cache',
      },
    })
    .then(response => {
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }
      
      customEventSource.readyState = EventSource.OPEN as number
      if (customEventSource.onopen) {
        customEventSource.onopen(new Event('open'))
      }

      const reader = response.body?.getReader()
      if (!reader) {
        throw new Error('Failed to get response reader')
      }

      const decoder = new TextDecoder()
      let buffer = ''

      const processStream = async () => {
        try {
          while (true) {
            const { done, value } = await reader.read()
            if (done) break

            buffer += decoder.decode(value, { stream: true })
            
            // Process complete lines
            const lines = buffer.split('\n')
            buffer = lines.pop() || '' // Keep incomplete line in buffer

            for (const line of lines) {
              if (line.startsWith('data: ')) {
                const data = line.slice(6) // Remove 'data: ' prefix
                if (data.trim() && customEventSource.onmessage) {
                  customEventSource.onmessage(new MessageEvent('message', { data }))
                }
              }
            }
          }
        } catch (error) {
          if (!controller.signal.aborted && customEventSource.onerror) {
            customEventSource.onerror(new Event('error'))
          }
        } finally {
          customEventSource.readyState = EventSource.CLOSED as number
        }
      }

      processStream()
    })
    .catch(() => {
      if (!controller.signal.aborted && customEventSource.onerror) {
        customEventSource.onerror(new Event('error'))
      }
      customEventSource.readyState = EventSource.CLOSED as number
    })

    eventSource = customEventSource
    return customEventSource as EventSource
  }

  static async getTranscript(transcriptId: string): Promise<Transcript> {
    const response = await apiClient.get<Transcript>(`/transcribe/${transcriptId}`)
    return response.data
  }

  static async listTranscripts(): Promise<Transcript[]> {
    const response = await apiClient.get<Transcript[]>('/transcribe/')
    return response.data
  }

  // Note generation endpoints
  static async buildNote(request: NoteRequest): Promise<NoteResponse> {
    // Fallback method - convert streaming to single response
    return new Promise((resolve, reject) => {
      const eventSource = this.createNoteStream(request)
      let finalNote: NoteResponse | null = null
      
      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          if (data.type === 'complete') {
            // Convert streaming response to NoteResponse format
            finalNote = {
              id: `${request.transcript_id}_${request.template_name}`,
              note_markdown: data.note_markdown,
              trace_events: [],
              citations: [],
              template_used: request.template_name,
              generation_time: 0,
              created_at: new Date().toISOString(),
              transcript_id: request.transcript_id,
              title: `${request.template_name.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())} Note`
            }
          } else if (data.type === 'end') {
            eventSource.close()
            if (finalNote) {
              resolve(finalNote)
            } else {
              reject(new Error('Note generation completed but no final note received'))
            }
          } else if (data.type === 'error') {
            eventSource.close()
            reject(new Error(data.message || 'Note generation failed'))
          }
        } catch (e) {
          eventSource.close()
          reject(new Error('Failed to parse streaming response'))
        }
      }
      
      eventSource.onerror = () => {
        eventSource.close()
        reject(new Error('Streaming connection failed'))
      }
    })
  }

  static async getNote(noteId: string): Promise<NoteResponse> {
    const response = await apiClient.get<NoteResponse>(`/notes/${noteId}`)
    return response.data
  }

  static async listNotes(): Promise<NoteResponse[]> {
    const response = await apiClient.get<NoteResponse[]>('/notes/')
    return response.data
  }

  static async deleteNote(noteId: string): Promise<{ message: string; deleted_note_title?: string }> {
    const response = await apiClient.delete(`/notes/${noteId}`)
    return response.data
  }

  static async getSuggestions(
    prefix: string, 
    transcriptId?: string, 
    context?: string
  ): Promise<SuggestionResponse> {
    const params = new URLSearchParams({ prefix })
    if (transcriptId) params.append('transcript_id', transcriptId)
    if (context) params.append('context', context)
    
    const response = await apiClient.get<SuggestionResponse>(`/notes/suggest?${params}`)
    return response.data
  }

  // Template endpoints
  static async listTemplates(): Promise<TemplateInfo[]> {
    const response = await apiClient.get<TemplateInfo[]>('/templates/')
    return response.data
  }

  static async getTemplate(templateName: string): Promise<TemplateInfo> {
    const response = await apiClient.get<TemplateInfo>(`/templates/${templateName}`)
    return response.data
  }

  static async getTemplateDefaults(templateName: string): Promise<string[]> {
    const response = await apiClient.get<string[]>(`/templates/${templateName}/defaults`)
    return response.data
  }

  static async createTemplate(request: TemplateRequest): Promise<TemplateInfo> {
    const response = await apiClient.post<TemplateInfo>('/templates/', request)
    return response.data
  }

  static async uploadTemplate(file: File, name?: string): Promise<{ message: string }> {
    const formData = new FormData()
    formData.append('file', file)
    if (name) formData.append('name', name)
    
    const response = await apiClient.post('/templates/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
    
    return response.data
  }

  static async previewTemplate(
    templateName: string, 
    sampleData?: Record<string, any>
  ): Promise<{ template_name: string; rendered_content: string; sample_data: Record<string, any> }> {
    const response = await apiClient.post(`/templates/${templateName}/preview`, sampleData || {})
    return response.data
  }

  static async deleteTemplate(templateName: string): Promise<{ message: string }> {
    const response = await apiClient.delete(`/templates/${templateName}`)
    return response.data
  }

  // Streaming endpoints
  static createNoteStream(request: NoteRequest): EventSource {
    const params = new URLSearchParams({
      transcript_id: request.transcript_id,
      template_name: request.template_name,
    })
    
    if (request.custom_sections) {
      request.custom_sections.forEach(section => {
        params.append('custom_sections', section)
      })
    }
    
    if (request.system_instructions) {
      params.append('system_instructions', request.system_instructions)
    }
    
    const url = `${apiClient.defaults.baseURL}/notes/stream?${params}`
    return new EventSource(url)
  }

  static createTranscriptionStream(transcriptId: string): EventSource {
    const url = `${apiClient.defaults.baseURL}/transcribe/stream/${transcriptId}`
    return new EventSource(url)
  }
}

// Utility functions for stream handling
export function parseStreamEvent(data: string): StreamEvent | null {
  try {
    return JSON.parse(data) as StreamEvent
  } catch {
    return null
  }
}

export function createStreamHandler<T>(
  onEvent: (event: T) => void,
  onError?: (error: Event) => void,
) {
  return {
    onmessage: (event: MessageEvent) => {
      const data = parseStreamEvent(event.data)
      if (data) {
        onEvent(data as T)
      }
    },
    onerror: (error: Event) => {
      console.error('Stream error:', error)
      onError?.(error)
    },
    onopen: () => {
      console.log('Stream opened')
    },
  }
}

// Export the configured API client for custom requests
export { apiClient }
export default AmbientScribeAPI
