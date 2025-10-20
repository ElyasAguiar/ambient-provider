/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState, useEffect, useMemo } from 'react'
import { TraceEvent } from '@/lib/schema'
import { Activity, CheckCircle2, AlertCircle, Loader2, ChevronDown, Brain, FileText, Zap } from 'lucide-react'
import { MarkdownRenderer } from './MarkdownRenderer'

interface TracePanelProps {
  traces: TraceEvent[]
  isGenerating: boolean
}

interface GroupedTrace {
  id: string
  category: 'section' | 'general' | 'finalization'
  title: string
  status: 'pending' | 'processing' | 'completed' | 'error'
  startTime: string
  endTime?: string
  events: TraceEvent[]
  currentStreaming?: {
    type: 'reasoning' | 'content'
    text: string
  }
  reasoning?: string
  sectionContent?: string
}

export function TracePanel({ traces, isGenerating }: TracePanelProps) {
  // Track which individual trace accordion is open (showing full details)
  const [openTraceIndex, setOpenTraceIndex] = useState<number | null>(null)

  // Group traces by logical operations
  const groupedTraces = useMemo(() => {
    const groups: GroupedTrace[] = []
    
    for (const trace of traces) {
      const eventType = trace.event_type
      
      if (eventType === 'processing_section') {
        // Start a new section group
        const sectionName = trace.message.match(/Processing (.+) section/)?.[1] || 'Section'
        groups.push({
          id: `section-${groups.length}`,
          category: 'section',
          title: `${sectionName} Section`,
          status: 'processing',
          startTime: trace.timestamp,
          events: [trace]
        })
      } else if (eventType === 'llm_prompt_sent' || eventType === 'llm_reasoning_complete' || 
                 eventType === 'llm_reasoning_start' || eventType === 'llm_reasoning_stream' ||
                 eventType === 'llm_content_start' || eventType === 'llm_content_stream' || 
                 eventType === 'section_complete') {
        // Add to the current section group
        const currentGroup = groups[groups.length - 1]
        if (currentGroup && currentGroup.category === 'section') {
          currentGroup.events.push(trace)
          
          // Update streaming content based on event type
          if (eventType === 'llm_reasoning_stream' && trace.metadata?.partial_reasoning) {
            // Clean up partial reasoning
            let cleanReasoning = trace.metadata.partial_reasoning
              .replace(/\*\*\n?/g, '') // Remove standalone asterisks
              .replace(/^\s+|\s+$/gm, '') // Trim lines
              .replace(/^:+/, '') // Remove leading colons
              .trim()
            currentGroup.currentStreaming = {
              type: 'reasoning',
              text: cleanReasoning
            }
          } else if (eventType === 'llm_content_stream' && trace.metadata?.partial_content) {
            // Clean up partial content
            let cleanContent = trace.metadata.partial_content
              .replace(/\*\*\n?/g, '') // Remove standalone asterisks
              .trim()
            currentGroup.currentStreaming = {
              type: 'content',
              text: cleanContent
            }
          } else if (eventType === 'llm_reasoning_complete') {
            // Mark the section as completed and store both reasoning and content
            currentGroup.status = 'completed'
            currentGroup.endTime = trace.timestamp
            
            // Store reasoning and content separately for proper display
            if (trace.metadata?.reasoning) {
              // Clean up reasoning content
              let cleanReasoning = trace.metadata.reasoning
                .replace(/\*\*\n?/g, '') // Remove standalone asterisks
                .replace(/^\s+|\s+$/gm, '') // Trim lines
                .replace(/\n{3,}/g, '\n\n') // Reduce excessive line breaks
                .replace(/^:+/, '') // Remove leading colons
                .trim()
              currentGroup.reasoning = cleanReasoning
            }
            
            if (trace.metadata?.section_content) {
              currentGroup.sectionContent = trace.metadata.section_content
              // For streaming display, show the content as the primary item
              currentGroup.currentStreaming = {
                type: 'content',
                text: trace.metadata.section_content
              }
            }
          } else if (eventType === 'section_complete') {
            // Final section completion - ensure it's marked as completed
            currentGroup.status = 'completed'
            currentGroup.endTime = trace.timestamp
            
            if (trace.metadata?.content) {
              currentGroup.sectionContent = trace.metadata.content
            }
          }
        }
      } else if (eventType === 'started') {
        // General initialization
        groups.push({
          id: `general-${groups.length}`,
          category: 'general',
          title: 'Note Generation Started',
          status: 'completed',
          startTime: trace.timestamp,
          endTime: trace.timestamp,
          events: [trace]
        })
      } else if (eventType === 'rendering') {
        // Finalization
        groups.push({
          id: `final-${groups.length}`,
          category: 'finalization',
          title: 'Finalizing Note',
          status: 'processing',
          startTime: trace.timestamp,
          events: [trace]
        })
      } else if (eventType === 'complete') {
        // Final completion - mark the finalization section as completed
        const currentGroup = groups[groups.length - 1]
        if (currentGroup && currentGroup.category === 'finalization') {
          currentGroup.events.push(trace)
          currentGroup.status = 'completed'
          currentGroup.endTime = trace.timestamp
        } else {
          // Create a new completion group if no finalization group exists
          groups.push({
            id: `complete-${groups.length}`,
            category: 'finalization',
            title: 'Note Completed',
            status: 'completed',
            startTime: trace.timestamp,
            endTime: trace.timestamp,
            events: [trace]
          })
        }
      } else {
        // Handle other events by adding to existing group or creating new one
        const currentGroup = groups[groups.length - 1]
        if (currentGroup) {
          currentGroup.events.push(trace)
          
          // Update status based on event type
          if (eventType.includes('error')) {
            currentGroup.status = 'error'
          } else if (eventType.includes('complete') && eventType !== 'complete') {
            // Handle other completion events (but not the final 'complete' event)
            currentGroup.status = 'completed'
            currentGroup.endTime = trace.timestamp
            
            // For section content completion, update the streaming content
            if (trace.metadata?.section_content) {
              currentGroup.currentStreaming = {
                type: 'content',
                text: trace.metadata.section_content
              }
            }
          }
        } else {
          // Create standalone event
          groups.push({
            id: `event-${groups.length}`,
            category: 'general',
            title: trace.message,
            status: eventType.includes('error') ? 'error' : 'completed',
            startTime: trace.timestamp,
            endTime: trace.timestamp,
            events: [trace]
          })
        }
      }
    }
    
    return groups
  }, [traces])

  // Auto-open newest trace and collapse previous when a new event arrives
  useEffect(() => {
    if (groupedTraces.length > 0) {
      setOpenTraceIndex(groupedTraces.length - 1)
    }
  }, [groupedTraces.length])

  const getGroupIcon = (group: GroupedTrace) => {
    switch (group.status) {
      case 'error':
        return <AlertCircle className="h-4 w-4 text-accent-red" />
      case 'completed':
        return <CheckCircle2 className="h-4 w-4 text-accent-green" />
      case 'processing':
        return <Loader2 className="h-4 w-4 text-accent-blue animate-spin" />
      default:
        return <Activity className="h-4 w-4 text-brand" />
    }
  }

  const getCategoryIcon = (category: string) => {
    switch (category) {
      case 'section':
        return <Brain className="h-3 w-3" />
      case 'finalization':
        return <Zap className="h-3 w-3" />
      default:
        return <FileText className="h-3 w-3" />
    }
  }

  const formatTime = (timestamp: string) => {
    try {
      const date = new Date(timestamp)
      return date.toLocaleTimeString([], { hour12: false, timeStyle: 'medium' })
    } catch {
      return timestamp
    }
  }

  // Streaming text component
  function StreamingText({ text, isStreaming = false }: { text: string; isStreaming?: boolean }) {
    const [displayedText, setDisplayedText] = useState('')
    
    useEffect(() => {
      if (!isStreaming) {
        setDisplayedText(text)
        return
      }
      
      // Immediately show the text if streaming is enabled (real-time updates)
      setDisplayedText(text)
    }, [text, isStreaming])
    
    return (
      <div className="relative">
        <MarkdownRenderer content={displayedText} className="prose-blue" />
        {isStreaming && (
          <span className="ml-1 inline-block w-2 h-4 bg-accent-blue animate-pulse rounded-sm opacity-75 absolute top-0 right-0"></span>
        )}
      </div>
    )
  }

  if (groupedTraces.length === 0 && !isGenerating) {
    return (
      <div className="bg-surface-raised rounded-lg shadow h-full flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-base flex-shrink-0">
          <div className="flex items-center space-x-2">
            <Activity className="h-5 w-5 text-brand" />
            <h3 className="text-sm font-medium text-primary">Generation Progress</h3>
          </div>
        </div>
        
        {/* Empty State Content */}
        <div className="flex-1 flex items-center justify-center p-6">
          <div className="text-center text-secondary">
            <Activity className="h-8 w-8 mx-auto mb-2 text-brand" />
            <p className="text-sm">No processing traces yet</p>
            <p className="text-xs text-subtle">Generation traces will appear here</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-surface-raised rounded-lg shadow h-full flex flex-col">
      {/* Header */}
      <div 
        className="flex items-center justify-between p-4 border-b border-gray-200 flex-shrink-0"
      >
        <div className="flex items-center space-x-2">
          <Activity className="h-5 w-5 text-brand" />
          <h3 className="text-sm font-medium text-primary">
            Generation Progress
          </h3>
          {isGenerating && (
            <Loader2 className="h-4 w-4 text-brand animate-spin" />
          )}
        </div>
        
        {groupedTraces.length > 0 && (
          <span className="text-xs text-secondary bg-surface-sunken px-2 py-1 rounded">
            {groupedTraces.length} step{groupedTraces.length !== 1 ? 's' : ''}
          </span>
        )}
      </div>

      {/* Grouped Traces List */}
      <div className="flex-1 overflow-y-auto">
          {groupedTraces.length > 0 ? (
            <div className="p-4 space-y-3">
              {groupedTraces.map((group, index) => {
                const isOpen = openTraceIndex === index
                const isCurrentlyStreaming = group.status === 'processing' && group.currentStreaming
                
                return (
                  <div key={group.id} className="trace-item border border-gray-200 rounded-lg">
                    {/* Group header */}
                    <button
                      className="w-full flex items-start space-x-3 text-sm p-3 hover:bg-surface-sunken rounded-lg transition"
                      onClick={() => setOpenTraceIndex(isOpen ? null : index)}
                      aria-expanded={isOpen}
                      aria-controls={`trace-panel-${index}`}
                    >
                      <div className="mt-0.5 flex items-center space-x-1">
                        {getGroupIcon(group)}
                        <div className="text-secondary">
                          {getCategoryIcon(group.category)}
                        </div>
                      </div>
                      <div className="flex-1 min-w-0 text-left">
                        <div className="flex items-center justify-between">
                          <p className="text-primary truncate pr-3 font-medium">{group.title}</p>
                          <ChevronDown
                            className={`h-4 w-4 text-secondary transform transition-transform ${isOpen ? 'rotate-180' : ''}`}
                          />
                        </div>
                        <div className="mt-1 flex items-center gap-2 text-xs text-secondary">
                          <span className="inline-flex items-center gap-1">
                            <span
                              className={`inline-block h-1.5 w-1.5 rounded-full ${
                                group.status === 'processing' ? 'bg-accent-blue animate-pulse' :
                                group.status === 'completed' ? 'bg-accent-green' :
                                group.status === 'error' ? 'bg-accent-red' :
                                'bg-subtle'
                              }`}
                              aria-hidden
                            />
                            {group.status}
                          </span>
                          <span>•</span>
                          <span>{formatTime(group.startTime)}</span>
                          {group.endTime && group.endTime !== group.startTime && (
                            <>
                              <span>→</span>
                              <span>{formatTime(group.endTime)}</span>
                            </>
                          )}
                        </div>
                        
                        {/* Show streaming content in preview */}
                        {isCurrentlyStreaming && group.currentStreaming && (
                          <div className="mt-2 text-xs text-accent-blue font-medium flex items-center space-x-2">
                            <div className="flex space-x-1">
                              <div className="w-1 h-1 bg-accent-blue rounded-full animate-bounce" style={{animationDelay: '0ms'}}></div>
                              <div className="w-1 h-1 bg-accent-blue rounded-full animate-bounce" style={{animationDelay: '150ms'}}></div>
                              <div className="w-1 h-1 bg-accent-blue rounded-full animate-bounce" style={{animationDelay: '300ms'}}></div>
                            </div>
                            <span>
                              {group.currentStreaming.type === 'reasoning' ? 'Analyzing transcript...' : 'Generating content...'}
                            </span>
                          </div>
                        )}
                      </div>
                    </button>
                    
                    {/* Group expanded content */}
                    {isOpen && (
                      <div id={`trace-panel-${index}`} className="px-3 pb-3 space-y-3">
                        
                        {/* Show reasoning section if available */}
                        {group.reasoning && (
                          <div>
                            <div className="text-xs font-medium text-accent-purple mb-2 flex items-center space-x-1">
                              <Brain className="w-3 h-3" />
                              <span>LLM Reasoning</span>
                            </div>
                            <div className="text-sm bg-accent-purple-subtle border border-accent-purple rounded p-3">
                              <MarkdownRenderer content={group.reasoning} className="prose-purple" />
                            </div>
                          </div>
                        )}
                        
                        {/* Show section content if available */}
                        {group.sectionContent && (
                          <div>
                            <div className="text-xs font-medium text-accent-green mb-2 flex items-center space-x-1">
                              <FileText className="w-3 h-3" />
                              <span>Generated Content</span>
                            </div>
                            <div className="text-sm bg-accent-green-subtle border border-accent-green rounded p-3">
                              <MarkdownRenderer content={group.sectionContent} className="prose-green" />
                            </div>
                          </div>
                        )}
                        
                        {/* Show streaming content prominently when still processing */}
                        {group.status === 'processing' && group.currentStreaming && (
                          <div>
                            <div className="text-xs font-medium text-blue-700 mb-2 flex items-center space-x-1">
                              <Brain className="w-3 h-3" />
                              <span>LLM {group.currentStreaming.type === 'reasoning' ? 'Reasoning' : 'Response'} (Live)</span>
                            </div>
                            <div className="text-sm bg-accent-blue-subtle border border-accent-blue rounded p-3">
                              <StreamingText 
                                text={group.currentStreaming.text} 
                                isStreaming={true} 
                              />
                            </div>
                          </div>
                        )}
                        
                        {/* Show consolidated metadata from latest event */}
                        {group.events.length > 0 && (() => {
                          const latestEvent = group.events[group.events.length - 1]
                          return latestEvent.metadata && (
                            <div className="space-y-3">
                              {/* Show section content if available */}
                              {latestEvent.metadata.section_content && (
                                <div>
                                  <div className="text-xs font-medium text-accent-green mb-2 flex items-center space-x-1">
                                    <FileText className="w-3 h-3" />
                                    <span>Generated Content</span>
                                  </div>
                                  <div className="text-sm bg-accent-green-subtle border border-accent-green rounded p-3">
                                    <MarkdownRenderer content={latestEvent.metadata.section_content} className="prose-green" />
                                  </div>
                                </div>
                              )}
                              
                              {/* Show token usage if available */}
                              {latestEvent.metadata.usage && (
                                <div>
                                  <div className="text-xs font-medium text-primary mb-2 flex items-center space-x-1">
                                    <Zap className="w-3 h-3" />
                                    <span>Token Usage</span>
                                  </div>
                                  <div className="text-xs bg-surface-sunken border border-base rounded p-2">
                                    <div className="grid grid-cols-3 gap-2">
                                      <div>Prompt: {latestEvent.metadata.usage.prompt_tokens || 0}</div>
                                      <div>Response: {latestEvent.metadata.usage.completion_tokens || 0}</div>
                                      <div>Total: {latestEvent.metadata.usage.total_tokens || 0}</div>
                                    </div>
                                  </div>
                                </div>
                              )}
                            </div>
                          )
                        })()}
                        
                        {/* Show detailed events (collapsed by default) */}
                        <details className="text-xs">
                          <summary className="text-secondary cursor-pointer hover:text-primary font-medium">
                            View detailed events ({group.events.length})
                          </summary>
                          <div className="mt-2 space-y-2 pl-4 border-l-2 border-base">
                            {group.events.map((event, eventIndex) => (
                              <div key={eventIndex} className="text-secondary">
                                <div className="font-medium">{event.event_type}</div>
                                <div className="text-secondary">{event.message}</div>
                                <div className="text-subtle">{formatTime(event.timestamp)}</div>
                              </div>
                            ))}
                          </div>
                        </details>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          ) : (
            <div className="p-4 text-center text-secondary">
              <div className="flex items-center justify-center space-x-2">
                <Loader2 className="h-4 w-4 animate-spin" />
                <span className="text-sm">Starting generation...</span>
              </div>
            </div>
          )}
      </div>
    </div>
  )
}
