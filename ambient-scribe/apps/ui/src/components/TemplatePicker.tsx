/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */

import { TemplateInfo } from '@/lib/schema'
import { ChevronDown, FileText, Plus } from 'lucide-react'

// Helper function to format section names from snake_case to Title Case
const formatSectionName = (sectionKey: string): string => {
  return sectionKey
    .replace(/_/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

interface TemplatePickerProps {
  templates: TemplateInfo[]
  selectedTemplate: string
  onTemplateChange: (templateName: string) => void
  compact?: boolean
  disabled?: boolean
  isTranscribing?: boolean
}

export function TemplatePicker({ 
  templates, 
  selectedTemplate, 
  onTemplateChange,
  compact = false,
  disabled = false,
  isTranscribing = false
}: TemplatePickerProps) {
  const selectedTemplateInfo = templates.find(t => t.name === selectedTemplate)

  if (compact) {
    return (
      <div className="flex items-center space-x-3">
        <label className="text-sm font-medium text-primary whitespace-nowrap">
          Template:
        </label>
        <div className="relative min-w-[200px]">
          <select
            value={selectedTemplate}
            onChange={(e) => onTemplateChange(e.target.value)}
            disabled={disabled}
            className={`w-full appearance-none border rounded-md px-3 py-2 pr-10 text-sm focus:outline-none focus:ring-2 focus:ring-brand focus:border-brand ${
              disabled 
                ? 'bg-surface-sunken border-base text-secondary cursor-not-allowed' 
                : 'bg-surface-raised border-base text-primary'
            }`}
          >
            {templates.map((template) => (
              <option key={template.name} value={template.name}>
                {template.display_name}
                {template.is_custom && ' (Custom)'}
              </option>
            ))}
          </select>
          <ChevronDown className="absolute right-3 top-2.5 h-4 w-4 text-secondary pointer-events-none" />
          
          {/* Status indicator when disabled */}
          {disabled && isTranscribing && (
            <div className="absolute -bottom-5 left-0 text-xs text-accent-yellow">
              Locked during transcription
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <label className="block text-sm font-medium text-primary">
          Note Template
        </label>
        <button className="text-sm text-brand hover:text-brand/80 flex items-center space-x-1">
          <Plus className="h-4 w-4" />
          <span>New Template</span>
        </button>
      </div>
      
      <div className="relative">
        <select
          value={selectedTemplate}
          onChange={(e) => onTemplateChange(e.target.value)}
          disabled={disabled}
          className={`w-full appearance-none border rounded-md px-3 py-2 pr-10 text-sm focus:outline-none focus:ring-2 focus:ring-brand focus:border-brand ${
            disabled 
              ? 'bg-surface-sunken border-base text-secondary cursor-not-allowed' 
              : 'bg-surface-raised border-base text-primary'
          }`}
        >
          {templates.map((template) => (
            <option key={template.name} value={template.name}>
              {template.display_name}
              {template.is_custom && ' (Custom)'}
            </option>
          ))}
        </select>
        
        <ChevronDown className="absolute right-3 top-2.5 h-4 w-4 text-secondary pointer-events-none" />
      </div>

      {selectedTemplateInfo && (
        <div className="bg-surface-sunken rounded-md p-3">
          <div className="flex items-start space-x-2">
            <FileText className="h-4 w-4 text-brand mt-0.5" />
            <div className="flex-1 min-w-0">
              <p className="text-sm text-primary mb-1">
                {selectedTemplateInfo.description}
              </p>
              
              {selectedTemplateInfo.sections.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {selectedTemplateInfo.sections.map((section) => (
                    <span
                      key={section}
                      className="inline-flex items-center px-2 py-1 text-xs font-medium bg-accent-blue-subtle text-accent-blue rounded"
                    >
                      {formatSectionName(section)}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
