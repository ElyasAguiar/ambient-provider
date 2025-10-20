/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState, useRef, useEffect, useImperativeHandle, forwardRef } from 'react'
import { Play, Pause, RotateCcw, Volume2, VolumeX } from 'lucide-react'
import { Soundwaves } from '@nv-brand-assets/react-icons-inline'

interface AudioPlayerProps {
  audioUrl: string | null
  onTimeUpdate?: (currentTime: number, duration: number) => void
  className?: string
}

export interface AudioPlayerRef {
  seekToTime: (seconds: number) => void
}

const AudioPlayer = forwardRef<AudioPlayerRef, AudioPlayerProps>(({ audioUrl, onTimeUpdate, className = '' }, ref) => {
  const audioRef = useRef<HTMLAudioElement>(null)
  const progressRef = useRef<HTMLDivElement>(null)
  
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [playbackRate, setPlaybackRate] = useState(1)
  const [volume, setVolume] = useState(1)
  const [isMuted, setIsMuted] = useState(false)
  const [isLoading, setIsLoading] = useState(false)

  const playbackSpeeds = [0.75, 1, 1.25, 1.5, 2]

  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return

    const handleLoadStart = () => {
      console.log('Audio loading started:', audioUrl)
      setIsLoading(true)
    }
    
    const handleCanPlay = () => {
      console.log('Audio can play:', audioUrl)
      setIsLoading(false)
    }
    
    const handleLoadedMetadata = () => {
      console.log('Audio metadata loaded:', { duration: audio.duration, src: audio.src })
      setDuration(audio.duration)
      setIsLoading(false)
    }
    
    const handleTimeUpdate = () => {
      const time = audio.currentTime
      setCurrentTime(time)
      onTimeUpdate?.(time, audio.duration)
    }

    const handleEnded = () => {
      setIsPlaying(false)
      setCurrentTime(0)
    }

    const handleError = (e: Event) => {
      setIsLoading(false)
      const errorEvent = e as ErrorEvent
      console.error('Audio loading error:', {
        url: audioUrl,
        src: audio.src,
        error: errorEvent.error,
        networkState: audio.networkState,
        readyState: audio.readyState
      })
      
      // Try to provide more specific error info
      if (audio.networkState === HTMLMediaElement.NETWORK_NO_SOURCE) {
        console.error('No audio source found')
      } else if (audio.networkState === HTMLMediaElement.NETWORK_LOADING) {
        console.error('Audio still loading')
      } else if (audio.error) {
        console.error('Audio error code:', audio.error.code, audio.error.message)
        
        // Provide specific error codes explanation
        switch (audio.error.code) {
          case MediaError.MEDIA_ERR_ABORTED:
            console.error('Audio playback was aborted')
            break
          case MediaError.MEDIA_ERR_NETWORK:
            console.error('Network error occurred while fetching audio')
            break
          case MediaError.MEDIA_ERR_DECODE:
            console.error('Audio decoding error')
            break
          case MediaError.MEDIA_ERR_SRC_NOT_SUPPORTED:
            console.error('Audio format not supported')
            break
        }
      }
    }

    audio.addEventListener('loadstart', handleLoadStart)
    audio.addEventListener('canplay', handleCanPlay)
    audio.addEventListener('loadedmetadata', handleLoadedMetadata)
    audio.addEventListener('timeupdate', handleTimeUpdate)
    audio.addEventListener('ended', handleEnded)
    audio.addEventListener('error', handleError)

    return () => {
      audio.removeEventListener('loadstart', handleLoadStart)
      audio.removeEventListener('canplay', handleCanPlay)
      audio.removeEventListener('loadedmetadata', handleLoadedMetadata)
      audio.removeEventListener('timeupdate', handleTimeUpdate)
      audio.removeEventListener('ended', handleEnded)
      audio.removeEventListener('error', handleError)
    }
  }, [onTimeUpdate, audioUrl])

  useEffect(() => {
    if (audioRef.current) {
      audioRef.current.playbackRate = playbackRate
    }
  }, [playbackRate])

  useEffect(() => {
    if (audioRef.current) {
      audioRef.current.volume = isMuted ? 0 : volume
    }
  }, [volume, isMuted])

  // Reset audio when URL changes
  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return

    if (audioUrl) {
      console.log('Setting new audio source:', audioUrl)
      audio.src = audioUrl
      audio.load() // Force reload
      setCurrentTime(0)
      setDuration(0)
      setIsPlaying(false)
      setIsLoading(true)
    } else {
      console.log('Clearing audio source')
      audio.src = ''
      setCurrentTime(0)
      setDuration(0)
      setIsPlaying(false)
      setIsLoading(false)
    }
  }, [audioUrl])

  const togglePlayPause = async () => {
    const audio = audioRef.current
    if (!audio || !audioUrl) return

    try {
      if (isPlaying) {
        audio.pause()
        setIsPlaying(false)
      } else {
        await audio.play()
        setIsPlaying(true)
      }
    } catch (error) {
      console.error('Audio playback error:', error)
    }
  }

  const resetAudio = () => {
    const audio = audioRef.current
    if (!audio) return

    audio.currentTime = 0
    setCurrentTime(0)
    if (isPlaying) {
      audio.pause()
      setIsPlaying(false)
    }
  }

  const seekToTime = (seekTime: number) => {
    const audio = audioRef.current
    if (!audio || !duration) return

    const clampedTime = Math.max(0, Math.min(seekTime, duration))
    audio.currentTime = clampedTime
    setCurrentTime(clampedTime)
  }

  useImperativeHandle(ref, () => ({
    seekToTime
  }))

  const handleProgressClick = (event: React.MouseEvent<HTMLDivElement>) => {
    const progressBar = progressRef.current
    if (!progressBar || !duration) return

    const rect = progressBar.getBoundingClientRect()
    const x = event.clientX - rect.left
    const percentage = x / rect.width
    const seekTime = percentage * duration

    seekToTime(seekTime)
  }

  const formatTime = (seconds: number) => {
    if (!Number.isFinite(seconds)) return '0:00'
    
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  const toggleMute = () => {
    setIsMuted(!isMuted)
  }

  const handleVolumeChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const newVolume = parseFloat(event.target.value)
    setVolume(newVolume)
    if (newVolume > 0 && isMuted) {
      setIsMuted(false)
    }
  }

  if (!audioUrl) {
    return (
      <div className={`bg-surface-raised rounded-lg shadow h-full flex flex-col ${className}`}>
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-base flex-shrink-0">
          <div className="flex items-center space-x-2">
            <Soundwaves className="h-5 w-5 text-brand" />
            <h3 className="text-sm font-medium text-primary">Audio Player</h3>
          </div>
        </div>
        
        {/* Empty State Content */}
        <div className="flex-1 flex items-center justify-center p-6">
          <div className="text-center text-secondary">
            <Volume2 className="h-8 w-8 mx-auto mb-2 text-brand" />
            <p className="text-sm">No audio file available</p>
            <p className="text-xs text-subtle">Upload an audio file to get started</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className={`bg-surface-raised rounded-lg shadow h-full flex flex-col ${className}`}>
      <audio ref={audioRef} preload="metadata" />
      
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-base flex-shrink-0">
        <div className="flex items-center space-x-2">
          <Soundwaves className="h-5 w-5 text-brand" />
          <h3 className="text-sm font-medium text-primary">Audio Player</h3>
        </div>
      </div>
      
      {/* Audio Player Content */}
      <div className="flex-1 flex flex-col justify-center p-3">
        {/* Main Controls */}
        <div className="flex items-center space-x-2 mb-3">
        {/* Play/Pause Button */}
        <button
          onClick={togglePlayPause}
          disabled={isLoading}
          className="flex-shrink-0 w-10 h-10 bg-brand hover:bg-brand/90 disabled:bg-subtle 
                     text-inverse rounded-full flex items-center justify-center transition-colors"
          title={isPlaying ? 'Pause' : 'Play'}
        >
          {isLoading ? (
            <div className="w-4 h-4 border-2 border-inverse border-t-transparent rounded-full animate-spin" />
          ) : isPlaying ? (
            <Pause className="h-4 w-4" />
          ) : (
            <Play className="h-4 w-4 ml-0.5" />
          )}
        </button>

        {/* Reset Button */}
        <button
          onClick={resetAudio}
          className="flex-shrink-0 w-8 h-8 text-secondary hover:text-primary 
                     rounded flex items-center justify-center transition-colors"
          title="Reset to beginning"
        >
          <RotateCcw className="h-4 w-4" />
        </button>

        {/* Time Display */}
        <div className="flex-shrink-0 text-xs text-secondary font-mono min-w-0">
          <div className="truncate">
            {formatTime(currentTime)} / {formatTime(duration)}
          </div>
        </div>
      </div>

      {/* Progress Bar */}
      <div 
        ref={progressRef}
        className="relative w-full h-2 bg-surface-sunken rounded-full cursor-pointer mb-3"
        onClick={handleProgressClick}
      >
        <div 
          className="absolute top-0 left-0 h-full bg-brand rounded-full transition-all duration-100"
          style={{ width: duration > 0 ? `${(currentTime / duration) * 100}%` : '0%' }}
        />
        <div 
          className="absolute top-1/2 transform -translate-y-1/2 w-3 h-3 bg-brand 
                     border-2 border-surface-raised rounded-full shadow-sm"
          style={{ 
            left: duration > 0 ? `calc(${(currentTime / duration) * 100}% - 6px)` : '-6px',
            opacity: duration > 0 ? 1 : 0
          }}
        />
      </div>

      {/* Secondary Controls */}
      <div className="flex items-center justify-between gap-2">
        {/* Playback Speed */}
        <div className="flex items-center space-x-1 min-w-0">
          <span className="text-xs text-secondary whitespace-nowrap">Speed:</span>
          <select
            value={playbackRate}
            onChange={(e) => setPlaybackRate(parseFloat(e.target.value))}
            className="text-xs bg-surface-sunken border border-base text-primary rounded px-1 py-0.5 focus:outline-none focus:ring-1 focus:ring-brand/50 min-w-0"
          >
            {playbackSpeeds.map(speed => (
              <option key={speed} value={speed}>
                {speed}x
              </option>
            ))}
          </select>
        </div>

        {/* Volume Control */}
        <div className="flex items-center space-x-1 min-w-0">
          <button
            onClick={toggleMute}
            className="text-secondary hover:text-primary transition-colors"
            title={isMuted ? 'Unmute' : 'Mute'}
          >
            {isMuted || volume === 0 ? (
              <VolumeX className="h-4 w-4" />
            ) : (
              <Volume2 className="h-4 w-4" />
            )}
          </button>
          <input
            type="range"
            min="0"
            max="1"
            step="0.1"
            value={isMuted ? 0 : volume}
            onChange={handleVolumeChange}
            className="w-12 h-1 bg-surface-sunken rounded-lg appearance-none cursor-pointer flex-shrink-0
                       slider:appearance-none slider:h-2 slider:w-2 slider:rounded-full 
                       slider:bg-brand slider:cursor-pointer"
            title="Volume"
          />
        </div>
      </div>
      </div>
    </div>
  )
})

AudioPlayer.displayName = 'AudioPlayer'

export { AudioPlayer }
