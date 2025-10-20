import { useMemo } from 'react'
/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */

import { marked } from 'marked'

interface MarkdownRendererProps {
  content: string
  className?: string
}

export function MarkdownRenderer({ content, className = '' }: MarkdownRendererProps) {
  const renderedHtml = useMemo(() => {
    if (!content) return ''
    
    // Configure marked for security
    marked.setOptions({
      breaks: true,        // Enable line breaks for better formatting in traces
      gfm: true,          // GitHub Flavored Markdown
    })
    
    return marked(content)
  }, [content])

  return (
    <div 
      className={`prose prose-sm max-w-none ${className}`}
      dangerouslySetInnerHTML={{ __html: renderedHtml }}
    />
  )
}
