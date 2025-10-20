/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */

import { useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import { Upload, Loader2, FileAudio } from 'lucide-react'

interface AudioDropzoneProps {
  onFileUpload: (file: File) => void
  isUploading?: boolean
  compact?: boolean
  disabled?: boolean
}

export function AudioDropzone({ onFileUpload, isUploading = false, compact = false, disabled = false }: AudioDropzoneProps) {
  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      if (acceptedFiles.length > 0) {
        onFileUpload(acceptedFiles[0])
      }
    },
    [onFileUpload]
  )

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'audio/*': ['.mp3', '.wav', '.m4a', '.flac', '.ogg'],
    },
    multiple: false,
    disabled: isUploading || disabled,
  })

  return (
    <div
      {...getRootProps()}
      className={`
        border-2 border-dashed rounded-lg text-center transition-colors
        ${compact ? 'p-4' : 'p-8'}
        ${isDragActive && !disabled && !isUploading ? 'border-brand bg-accent-blue-subtle' : 'border-base'}
        ${isUploading || disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer hover:border-brand hover:bg-surface-sunken'}
      `}
    >
      <input {...getInputProps()} />
      
      <div className={`flex ${compact ? 'flex-row items-center space-x-3' : 'flex-col items-center space-y-4'}`}>
        {isUploading ? (
          <>
            <Loader2 className={`text-brand animate-spin ${compact ? 'h-5 w-5' : 'h-12 w-12'}`} />
            <div className={compact ? 'text-left' : ''}>
              <p className={`font-medium text-primary ${compact ? 'text-sm' : 'text-lg'}`}>
                Transcribing audio...
              </p>
              {!compact && (
                <p className="text-sm text-secondary">This may take a few minutes</p>
              )}
            </div>
          </>
        ) : disabled ? (
          <>
            <FileAudio className={`text-subtle ${compact ? 'h-5 w-5' : 'h-12 w-12'}`} />
            <div className={compact ? 'text-left' : ''}>
              <p className={`font-medium text-secondary ${compact ? 'text-sm' : 'text-lg'}`}>
                {compact ? 'Audio upload disabled' : 'Audio upload disabled'}
              </p>
              <p className={`text-subtle ${compact ? 'text-xs' : 'text-sm'}`}>
                {compact ? 'Click "New" to upload audio' : 'Click "New" button to start a new session and upload audio'}
              </p>
            </div>
          </>
        ) : (
          <>
            {isDragActive ? (
              <Upload className={`text-brand ${compact ? 'h-5 w-5' : 'h-12 w-12'}`} />
            ) : (
              <FileAudio className={`text-brand ${compact ? 'h-5 w-5' : 'h-12 w-12'}`} />
            )}
            
            <div className={compact ? 'text-left' : ''}>
              <p className={`font-medium text-primary ${compact ? 'text-sm' : 'text-lg'}`}>
                {isDragActive ? 'Drop audio file here' : compact ? 'Upload audio' : 'Upload audio file'}
              </p>
              <p className={`text-secondary ${compact ? 'text-xs' : 'text-sm'}`}>
                {compact ? 'MP3, WAV, M4A, FLAC, OGG' : 'Drag & drop or click to select • MP3, WAV, M4A, FLAC, OGG'}
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
