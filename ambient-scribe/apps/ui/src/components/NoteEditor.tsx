/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */

import { useCallback, useMemo, useState, useRef, useImperativeHandle, forwardRef, useEffect } from 'react'
import { Transcript } from '@/lib/schema'
import { marked } from 'marked'
import TurndownService from 'turndown'
import { 
  Bold, 
  Italic, 
  List, 
  ListOrdered, 
  Quote,
  Eye,
  Edit3
} from 'lucide-react'

interface NoteEditorProps {
  value: string
  onChange: (value: string) => void
  transcript?: Transcript
  isReadOnly?: boolean
}

// Expose methods to parent via ref
export interface NoteEditorRef {
  insertTimestamp: (timestamp: number) => void
}

export const NoteEditor = forwardRef<NoteEditorRef, NoteEditorProps>(({ 
  value, 
  onChange, 
  transcript, 
  isReadOnly = false 
}, ref) => {
  
  // Internal state to track user edits and prevent overwrites
  const [internalValue, setInternalValue] = useState(value)
  const [hasUserEdits, setHasUserEdits] = useState(false)
  const [lastTranscriptId, setLastTranscriptId] = useState<string | null>(null)
  
  // Autocomplete state
  const [showAutocomplete, setShowAutocomplete] = useState(false)
  const [autocompleteOptions, setAutocompleteOptions] = useState<string[]>([])
  const [selectedOptionIndex, setSelectedOptionIndex] = useState(0)
  const [autocompletePosition, setAutocompletePosition] = useState({ top: 0, left: 0 })
  
  // State for editor mode (edit/preview)
  const [viewMode, setViewMode] = useState<'edit' | 'preview' | 'split'>('edit')
  const editorRef = useRef<HTMLDivElement>(null)
  const isUpdatingRef = useRef(false)
  const updateTimeoutRef = useRef<number | null>(null)
  
  // Markdown/HTML conversion
  const turndown = useMemo(() => {
    const td = new TurndownService({
      headingStyle: 'atx',
      codeBlockStyle: 'fenced'
    })
    return td
  }, [])

  const markdownToHtml = useCallback((markdown: string) => {
    if (!markdown) return ''
    try {
      // Configure marked for safe HTML output
      marked.setOptions({
        breaks: true,
        gfm: true,
        async: false // Ensure synchronous operation
      })
      const result = marked(markdown)
      return typeof result === 'string' ? result : markdown
    } catch (error) {
      console.error('Error converting markdown to HTML:', error)
      return markdown
    }
  }, [])
  
  const htmlToMarkdown = useCallback((html: string) => {
    if (!html) return ''
    try {
      return turndown.turndown(html)
    } catch (error) {
      console.error('Error converting HTML to markdown:', error)
      return html
    }
  }, [turndown])

  // Common medical terms and phrases for autocomplete
  const medicalTerms = useMemo(() => [
    'heart rate', 'blood pressure', 'temperature', 'respiratory rate', 'oxygen saturation',
    'chest pain', 'shortness of breath', 'abdominal pain', 'headache', 'nausea', 'vomiting',
    'hypertension', 'diabetes', 'asthma', 'pneumonia', 'bronchitis', 'sinusitis',
    'patient reports', 'patient denies', 'physical examination', 'vital signs',
    'medical history', 'family history', 'social history', 'review of systems',
    'assessment and plan', 'differential diagnosis', 'treatment plan',
    'follow up', 'return to clinic', 'prescription', 'medication', 'dosage',
    'blood glucose', 'heart rhythm', 'lung sounds', 'bowel sounds',
    'range of motion', 'muscle strength', 'reflexes', 'sensation',
    'allergies', 'medications', 'surgical history', 'hospitalizations'
  ], [])

  // Get autocomplete suggestions based on current phrase (multi-word support)
  const getAutocompleteSuggestions = useCallback((phrase: string) => {
    if (!phrase || phrase.length < 2) return []
    
    const lowerPhrase = phrase.toLowerCase().trim()
    
    // First try exact phrase matching (for multi-word phrases like "heart ra")
    const exactMatches = medicalTerms
      .filter(term => term.toLowerCase().startsWith(lowerPhrase))
      .slice(0, 5)
    
    if (exactMatches.length > 0) {
      return exactMatches
    }
    
    // If no exact matches, try matching individual words
    const words = lowerPhrase.split(/\s+/)
    const lastWord = words[words.length - 1]
    
    if (lastWord.length >= 2) {
      return medicalTerms
        .filter(term => term.toLowerCase().includes(lastWord))
        .slice(0, 5)
    }
    
    return []
  }, [medicalTerms])

  // Get cursor position for autocomplete positioning
  const getCursorPosition = useCallback(() => {
    const selection = window.getSelection()
    if (!selection || !selection.rangeCount || !editorRef.current) return null
    
    const range = selection.getRangeAt(0)
    const rect = range.getBoundingClientRect()
    const editorRect = editorRef.current.getBoundingClientRect()
    
    return {
      top: rect.bottom - editorRect.top,
      left: rect.left - editorRect.left
    }
  }, [])

  // Normalize HTML for comparison to avoid unnecessary updates
  // Note: This function is kept for potential future use but currently unused
  // const normalizeHtml = useCallback((html: string) => {
  //   return html
  //     .replace(/\s+/g, ' ') // Normalize whitespace
  //     .replace(/>\s+</g, '><') // Remove whitespace between tags
  //     .trim()
  // }, [])

  // Handle external value changes (from parent component) - simplified
  useEffect(() => {
    const isNewSession = transcript?.id !== lastTranscriptId
    
    if (!hasUserEdits || isNewSession || isReadOnly) {
      setInternalValue(value)
      
      if (isNewSession) {
        setHasUserEdits(false)
        setLastTranscriptId(transcript?.id || null)
      }
    }
  }, [value, hasUserEdits, transcript?.id, lastTranscriptId, isReadOnly])

  // Simplified content change handler with autocomplete
  const handleContentChange = useCallback(() => {
    if (!editorRef.current || isReadOnly || isUpdatingRef.current) return
    
    // Clear existing timeout
    if (updateTimeoutRef.current) {
      clearTimeout(updateTimeoutRef.current)
    }
    
    // Check for autocomplete immediately
    const selection = window.getSelection()
    if (selection && selection.rangeCount > 0) {
      const range = selection.getRangeAt(0)
      const textNode = range.startContainer
      
      if (textNode.nodeType === Node.TEXT_NODE) {
        const text = textNode.textContent || ''
        const cursorPos = range.startOffset
        
        // Get text before cursor
        const beforeCursor = text.substring(0, cursorPos)
        
        // Look for the current phrase (up to 3 words back for better context)
        const phraseMatch = beforeCursor.match(/(\b\w+(?:\s+\w+){0,2})$/i)
        const currentPhrase = phraseMatch ? phraseMatch[1].trim() : ''
        
        if (currentPhrase && currentPhrase.length >= 2) {
          const suggestions = getAutocompleteSuggestions(currentPhrase)
          if (suggestions.length > 0) {
            const position = getCursorPosition()
            if (position) {
              setAutocompleteOptions(suggestions)
              setAutocompletePosition(position)
              setSelectedOptionIndex(0)
              setShowAutocomplete(true)
            }
          } else {
            setShowAutocomplete(false)
          }
        } else {
          setShowAutocomplete(false)
        }
      }
    }
    
    // Use debouncing to prevent rapid conversions
    updateTimeoutRef.current = setTimeout(() => {
      if (!editorRef.current || isUpdatingRef.current) return
      
      // Get HTML content and convert to markdown
      const htmlContent = editorRef.current.innerHTML
      const markdownContent = htmlToMarkdown(htmlContent)
      
      // Only update if content actually changed
      if (markdownContent !== internalValue) {
        setInternalValue(markdownContent)
        setHasUserEdits(true)
        
        // Set updating flag to prevent external interference
        isUpdatingRef.current = true
        onChange(markdownContent)
        setTimeout(() => {
          isUpdatingRef.current = false
        }, 50)
      }
    }, 300)
  }, [htmlToMarkdown, onChange, isReadOnly, internalValue, getAutocompleteSuggestions, getCursorPosition])

  // Formatting functions using document.execCommand (works with contentEditable)
  const applyFormat = useCallback((command: string, value?: string) => {
    if (isReadOnly) return
    
    editorRef.current?.focus()
    document.execCommand(command, false, value)
    handleContentChange()
  }, [isReadOnly, handleContentChange])

  // Handle keyboard shortcuts - with autocomplete support
  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLDivElement>) => {
    if (isReadOnly) return

    // Handle autocomplete navigation
    if (showAutocomplete) {
      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault()
          setSelectedOptionIndex(prev => 
            prev < autocompleteOptions.length - 1 ? prev + 1 : 0
          )
          return
        case 'ArrowUp':
          e.preventDefault()
          setSelectedOptionIndex(prev => 
            prev > 0 ? prev - 1 : autocompleteOptions.length - 1
          )
          return
        case 'Tab':
        case 'Enter':
          e.preventDefault()
          if (autocompleteOptions[selectedOptionIndex]) {
            insertAutocompleteOption(autocompleteOptions[selectedOptionIndex])
          }
          return
        case 'Escape':
          e.preventDefault()
          setShowAutocomplete(false)
          return
      }
    }

    // Handle formatting shortcuts
    if (e.ctrlKey || e.metaKey) {
      switch (e.key.toLowerCase()) {
        case 'b':
          e.preventDefault()
          applyFormat('bold')
          return
        case 'i':
          e.preventDefault()
          applyFormat('italic')
          return
      }
    }

    // Hide autocomplete on space or other keys
    if (e.key === ' ' || e.key === 'Backspace') {
      setShowAutocomplete(false)
    }
  }, [isReadOnly, applyFormat, showAutocomplete, autocompleteOptions, selectedOptionIndex])

  // Insert selected autocomplete option with proper phrase replacement
  const insertAutocompleteOption = useCallback((option: string) => {
    if (!editorRef.current) return
    
    const selection = window.getSelection()
    if (!selection || !selection.rangeCount) return
    
    const range = selection.getRangeAt(0)
    const textNode = range.startContainer
    
    if (textNode.nodeType === Node.TEXT_NODE) {
      const text = textNode.textContent || ''
      const cursorPos = range.startOffset
      
      // Get text before cursor
      const beforeCursor = text.substring(0, cursorPos)
      const afterCursor = text.substring(cursorPos)
      
      // Find the current phrase (up to 3 words back)
      const phraseMatch = beforeCursor.match(/(\b\w+(?:\s+\w+){0,2})$/i)
      if (!phraseMatch) return
      
      const currentPhrase = phraseMatch[1].trim()
      const phraseStartPos = cursorPos - currentPhrase.length
      
      // Determine if the original phrase was capitalized
      const wasCapitalized = currentPhrase[0] && currentPhrase[0] === currentPhrase[0].toUpperCase()
      
      // Apply proper capitalization to the replacement
      let replacement = option
      if (wasCapitalized && option[0]) {
        replacement = option[0].toUpperCase() + option.slice(1)
      }
      
      // Replace the current phrase with the selected option
      const beforePhrase = text.substring(0, phraseStartPos)
      const newText = beforePhrase + replacement + afterCursor
      
      // Update the text node
      textNode.textContent = newText
      
      // Position cursor after the inserted text
      const newCursorPos = phraseStartPos + replacement.length
      range.setStart(textNode, newCursorPos)
      range.setEnd(textNode, newCursorPos)
      selection.removeAllRanges()
      selection.addRange(range)
    }
    
    setShowAutocomplete(false)
    handleContentChange()
  }, [handleContentChange])

  // Citation functionality - expose to parent
  const insertTimestampCitation = useCallback((timestamp: number) => {
    const minutes = Math.floor(timestamp / 60)
    const seconds = Math.floor(timestamp % 60)
    const citation = `[${minutes}:${seconds.toString().padStart(2, '0')}]`
    
    if (editorRef.current) {
      editorRef.current.focus()
      document.execCommand('insertText', false, citation + ' ')
      handleContentChange()
    }
  }, [handleContentChange])

  // Expose methods to parent via ref
  useImperativeHandle(ref, () => ({
    insertTimestamp: insertTimestampCitation
  }), [insertTimestampCitation])

  // Stable HTML content update - only updates when necessary and prevents interference
  useEffect(() => {
    if (editorRef.current && viewMode === 'edit' && !isUpdatingRef.current && !hasUserEdits) {
      const html = markdownToHtml(internalValue)
      const currentHtml = editorRef.current.innerHTML
      
      // Only update if content is significantly different to prevent jitter
      if (html !== currentHtml && html.trim() !== currentHtml.trim()) {
        console.log('[NoteEditor] Updating HTML content from external source')
        
        // Save cursor position before updating
        const selection = window.getSelection()
        let cursorOffset = 0
        
        if (selection && selection.rangeCount > 0) {
          const range = selection.getRangeAt(0)
          const preCaretRange = range.cloneRange()
          preCaretRange.selectNodeContents(editorRef.current)
          preCaretRange.setEnd(range.startContainer, range.startOffset)
          cursorOffset = preCaretRange.toString().length
        }
        
        // Set flag to prevent recursive updates
        isUpdatingRef.current = true
        
        // Update content
        editorRef.current.innerHTML = html
        
        // Restore cursor position only if user was actively editing
        if (cursorOffset > 0 && document.activeElement === editorRef.current) {
          requestAnimationFrame(() => {
            try {
              const textContent = editorRef.current?.textContent || ''
              const newOffset = Math.min(cursorOffset, textContent.length)
              
              const walker = document.createTreeWalker(
                editorRef.current!,
                NodeFilter.SHOW_TEXT,
                null
              )
              
              let currentOffset = 0
              let node
              while (node = walker.nextNode()) {
                const nodeLength = node.textContent?.length || 0
                if (currentOffset + nodeLength >= newOffset) {
                  const range = document.createRange()
                  const selection = window.getSelection()
                  const localOffset = newOffset - currentOffset
                  
                  range.setStart(node, Math.min(localOffset, nodeLength))
                  range.collapse(true)
                  
                  selection?.removeAllRanges()
                  selection?.addRange(range)
                  break
                }
                currentOffset += nodeLength
              }
            } catch (error) {
              console.warn('Failed to restore cursor position:', error)
            }
            
            isUpdatingRef.current = false
          })
        } else {
          isUpdatingRef.current = false
        }
      }
    }
  }, [internalValue, markdownToHtml, viewMode, hasUserEdits])

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (updateTimeoutRef.current) {
        clearTimeout(updateTimeoutRef.current)
      }
    }
  }, [])

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Toolbar */}
      <div className="flex items-center justify-between p-2 border-b border-base bg-surface-subtle flex-shrink-0">
          <div className="flex items-center space-x-1">
          {/* View Mode Toggle */}
          <div className="flex items-center bg-surface-base rounded-md p-1">
            <button
              onClick={() => setViewMode('edit')}
              className={`px-2 py-1 text-xs rounded ${
                viewMode === 'edit' 
                  ? 'bg-primary text-primary-foreground' 
                  : 'text-secondary hover:bg-surface-subtle'
              }`}
            >
              <Edit3 className="w-3 h-3" />
            </button>
            <button
              onClick={() => setViewMode('preview')}
              className={`px-2 py-1 text-xs rounded ${
                viewMode === 'preview' 
                  ? 'bg-primary text-primary-foreground' 
                  : 'text-secondary hover:bg-surface-subtle'
              }`}
            >
              <Eye className="w-3 h-3" />
            </button>
          </div>

          {/* Formatting Buttons */}
          {viewMode === 'edit' && (
            <>
              <div className="w-px h-4 bg-border mx-1" />
              
            <button
                onClick={() => applyFormat('bold')}
                className="p-1 text-secondary hover:bg-surface-subtle rounded"
                title="Bold (Ctrl+B)"
                disabled={isReadOnly}
              >
                <Bold className="w-4 h-4" />
            </button>
            <button
                onClick={() => applyFormat('italic')}
                className="p-1 text-secondary hover:bg-surface-subtle rounded"
                title="Italic (Ctrl+I)"
                disabled={isReadOnly}
              >
                <Italic className="w-4 h-4" />
            </button>
            <button
                onClick={() => applyFormat('insertUnorderedList')}
                className="p-1 text-secondary hover:bg-surface-subtle rounded"
                title="Bullet List"
                disabled={isReadOnly}
              >
                <List className="w-4 h-4" />
            </button>
            <button
                onClick={() => applyFormat('insertOrderedList')}
                className="p-1 text-secondary hover:bg-surface-subtle rounded"
                title="Numbered List"
                disabled={isReadOnly}
              >
                <ListOrdered className="w-4 h-4" />
            </button>
            <button
                onClick={() => applyFormat('formatBlock', 'blockquote')}
                className="p-1 text-secondary hover:bg-surface-subtle rounded"
                title="Quote"
                disabled={isReadOnly}
              >
                <Quote className="w-4 h-4" />
                </button>
            </>
          )}
        </div>
      </div>

      {/* Editor Content */}
      <div className="flex-1 min-h-0 overflow-hidden relative">
        {viewMode === 'edit' && (
          <>
            <div
              ref={editorRef}
              contentEditable={!isReadOnly}
              onInput={handleContentChange}
              onKeyDown={handleKeyDown}
              className="flex-1 p-4 focus:outline-none bg-surface-base text-primary prose prose-sm max-w-none overflow-y-auto min-h-0 h-full"
              style={{ 
                minHeight: '300px',
                lineHeight: '1.6'
              }}
              suppressContentEditableWarning={true}
              data-placeholder="Your medical note will appear here. Start typing to see formatted text..."
            />
            
            {/* Autocomplete Dropdown */}
            {showAutocomplete && (
              <div
                className="absolute z-50 bg-surface-raised border border-base rounded-md shadow-lg max-w-xs"
                style={{
                  top: autocompletePosition.top + 20,
                  left: autocompletePosition.left,
                  maxHeight: '200px',
                  overflowY: 'auto'
                }}
              >
                {/* Keyboard instructions */}
                <div className="px-3 py-1 text-xs text-secondary border-b border-base bg-surface-subtle">
                  ↑↓ navigate • Tab/Enter select • Esc close
                </div>
                
                {autocompleteOptions.map((option, index) => (
                  <div
                    key={option}
                    className={`px-3 py-2 text-sm cursor-pointer ${
                      index === selectedOptionIndex
                        ? 'bg-accent-blue-subtle text-accent-blue'
                        : 'text-primary hover:bg-surface-subtle'
                    }`}
                    onClick={() => insertAutocompleteOption(option)}
                  >
                    {option}
                  </div>
                ))}
              </div>
            )}
          </>
        )}

        {viewMode === 'preview' && (
          <div className="flex-1 p-4 bg-surface-base text-primary prose prose-sm max-w-none overflow-y-auto">
            <div 
              dangerouslySetInnerHTML={{ 
                __html: markdownToHtml(internalValue) 
              }} 
            />
          </div>
        )}
        </div>
    </div>
  )
})

export default NoteEditor