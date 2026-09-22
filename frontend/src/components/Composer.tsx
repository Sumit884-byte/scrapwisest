import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent, DragEvent, KeyboardEvent } from 'react'
import type { PendingImage } from '../lib/types'
import { ApiError, transcribeAudio } from '../lib/api'
import { setDetectedLang } from '../lib/language'
import {
  isMicSupported,
  isRecordingSupported,
  isSpeechSupported,
  startDictation,
  startRecording,
  type ActiveRecording,
} from '../lib/speech'
import { Camera, Mic, Square, ArrowUp, X, Loader2 } from 'lucide-react'

interface Props {
  disabled: boolean
  onSend: (text: string, image: File | null) => void
  speechLocale?: string
}

const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/webp']
const MAX_IMAGE_BYTES = 8 * 1024 * 1024

function isAcceptedImage(file: File): boolean {
  if (ACCEPTED_TYPES.includes(file.type)) return true
  return /\.(jpe?g|png|webp)$/i.test(file.name)
}

function firstDroppedImage(event: DragEvent): File | null {
  const files = event.dataTransfer?.files
  if (!files?.length) return null
  return Array.from(files).find((file) => isAcceptedImage(file) || file.type.startsWith('image/')) ?? files[0]
}

export function Composer({ disabled, onSend, speechLocale = 'en-IN' }: Props) {
  const [text, setText] = useState('')
  const [image, setImage] = useState<PendingImage | null>(null)
  const [listening, setListening] = useState(false)
  const [transcribing, setTranscribing] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const taRef = useRef<HTMLTextAreaElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const stopRef = useRef<(() => void) | null>(null)
  const recordingRef = useRef<ActiveRecording | null>(null)
  const imageRef = useRef<PendingImage | null>(null)
  const dragDepthRef = useRef(0)
  imageRef.current = image

  const micSupported = isMicSupported()

  useEffect(() => {
    return () => {
      if (imageRef.current) URL.revokeObjectURL(imageRef.current.previewUrl)
    }
  }, [])

  const autoResize = () => {
    const el = taRef.current
    if (!el) return
    el.style.height = '0px'
    el.style.height = `${Math.min(el.scrollHeight, 132)}px`
  }

  const handleTextChange = (event: ChangeEvent<HTMLTextAreaElement>) => {
    setText(event.target.value)
    setError(null)
    autoResize()
  }

  const attachImage = (file: File | null | undefined) => {
    if (!file || disabled) return
    if (!isAcceptedImage(file)) {
      setError('Please drop a JPG, PNG, or WebP photo.')
      return
    }
    if (file.size > MAX_IMAGE_BYTES) {
      setError('Photo is too large (max 8 MB).')
      return
    }

    const current = imageRef.current
    if (current) URL.revokeObjectURL(current.previewUrl)
    setImage({ file, previewUrl: URL.createObjectURL(file) })
    setError(null)
  }

  const pickImage = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    attachImage(file)
  }

  const hasFilePayload = (event: DragEvent) =>
    Array.from(event.dataTransfer?.types ?? []).includes('Files')

  const handleDragEnter = (event: DragEvent<HTMLDivElement>) => {
    if (disabled || !hasFilePayload(event)) return
    event.preventDefault()
    dragDepthRef.current += 1
    setDragOver(true)
  }

  const handleDragOver = (event: DragEvent<HTMLDivElement>) => {
    if (disabled || !hasFilePayload(event)) return
    event.preventDefault()
    event.dataTransfer.dropEffect = 'copy'
  }

  const handleDragLeave = (event: DragEvent<HTMLDivElement>) => {
    if (!hasFilePayload(event)) return
    event.preventDefault()
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1)
    if (dragDepthRef.current === 0) setDragOver(false)
  }

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    dragDepthRef.current = 0
    setDragOver(false)
    if (disabled) return
    attachImage(firstDroppedImage(event))
  }

  const clearImage = () => {
    if (image) URL.revokeObjectURL(image.previewUrl)
    setImage(null)
  }

  const startBrowserDictation = () => {
    setListening(true)
    stopRef.current = startDictation(
      {
        onResult: (interim, final) => {
          setText(final + interim)
        },
        onEnd: () => setListening(false),
        onError: (code) => {
          setListening(false)
          if (code === 'not-allowed') setError('Microphone permission was denied.')
          else if (code === 'unsupported') setError('Voice input is not supported in this browser.')
          else setError('Could not hear anything — please type instead.')
        },
      },
      speechLocale,
    )
  }

  const startListening = async () => {
    setError(null)
    if (isRecordingSupported()) {
      try {
        recordingRef.current = await startRecording()
        setListening(true)
        return
      } catch {
        recordingRef.current = null
        if (!isSpeechSupported()) {
          setError('Microphone permission was denied.')
          return
        }
      }
    }
    if (isSpeechSupported()) startBrowserDictation()
    else setError('Voice input is not supported in this browser.')
  }

  const stopListening = async () => {
    const recording = recordingRef.current
    recordingRef.current = null
    if (recording) {
      setListening(false)
      setTranscribing(true)
      try {
        const blob = await recording.stop()
        const result = await transcribeAudio(blob)
        setDetectedLang(result.language)
        setText((prev) => {
          const next = prev.trim() ? `${prev.trim()} ${result.text}` : result.text
          return next
        })
        requestAnimationFrame(autoResize)
      } catch (err) {
        if (err instanceof ApiError && err.status === 503 && isSpeechSupported()) {
          startBrowserDictation()
        } else if (err instanceof ApiError) {
          setError(err.message)
        } else {
          setError('Could not hear anything — please type instead.')
        }
      } finally {
        setTranscribing(false)
      }
      return
    }
    stopRef.current?.()
    setListening(false)
  }

  const handleSend = () => {
    const trimmed = text.trim()
    if (!trimmed && !image) {
      setError('Type a message or attach a photo first.')
      return
    }
    if (listening) void stopListening()
    onSend(trimmed, image?.file ?? null)
    setText('')
    if (image) URL.revokeObjectURL(image.previewUrl)
    setImage(null)
    requestAnimationFrame(autoResize)
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      handleSend()
    }
  }

  const canSend = Boolean(text.trim() || image)

  return (
    <div
      className="border-t border-[var(--color-border)] bg-[var(--color-surface)]"
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <div className="mx-auto w-full max-w-[1200px] px-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-3 sm:px-6 lg:px-8">
        {dragOver && (
          <p className="mb-2 rounded-xl border border-dashed border-[var(--color-accent)] bg-[var(--color-accent-soft)] px-3 py-2.5 text-center text-[12px] font-medium text-[var(--color-accent-dark)]">
            Drop a photo to attach it
          </p>
        )}
        {error && (
          <p className="mb-2 flex items-center justify-center gap-1.5 rounded-xl bg-[var(--color-error-bg)] border border-[var(--color-error-border)] px-3 py-2 text-center text-[12px] font-medium text-[var(--color-error)]" role="alert">
            {error}
          </p>
        )}

        {image && (
          <div className="mb-2.5 flex items-center gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-chat)] px-3 py-2.5">
            <img
              src={image.previewUrl}
              alt="Photo preview"
              className="h-14 w-14 rounded-lg object-cover"
            />
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13px] font-medium text-[var(--color-text)]">{image.file.name}</p>
              <p className="text-[11px] text-[var(--color-text-muted)]">{(image.file.size / 1024).toFixed(0)} KB</p>
            </div>
            <button
              type="button"
              onClick={clearImage}
              aria-label="Remove photo"
              className="flex h-8 w-8 items-center justify-center rounded-lg text-[var(--color-text-muted)] transition hover:bg-[var(--color-border)] hover:text-[var(--color-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        )}

        <div className="flex items-end gap-2.5">
          <div
            className={`flex flex-1 items-end gap-1 rounded-[18px] border bg-[var(--color-surface)] px-2 py-1.5 transition-all shadow-[var(--shadow-composer)] ${
              dragOver
                ? 'border-[var(--color-accent)] ring-4 ring-[var(--color-focus-ring)]'
                : 'border-[var(--color-composer-border)] focus-within:border-[var(--color-accent)] focus-within:ring-4 focus-within:ring-[var(--color-focus-ring)]'
            }`}
          >
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              disabled={disabled}
              aria-label="Attach a photo"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-[var(--color-text-muted)] transition hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text)] disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2"
            >
              <Camera className="h-[18px] w-[18px]" />
            </button>
            <textarea
              ref={taRef}
              rows={1}
              value={text}
              onChange={handleTextChange}
              onKeyDown={handleKeyDown}
              placeholder="Ask a rate or log a sale..."
              className="max-h-[132px] flex-1 resize-none bg-transparent px-1 py-2 text-[15px] leading-[1.5] text-[var(--color-text)] placeholder:text-[var(--color-text-muted)] focus:outline-none"
            />
            {micSupported && (
              <button
                type="button"
                onClick={() => {
                  if (listening) void stopListening()
                  else void startListening()
                }}
                disabled={disabled || transcribing}
                aria-label={listening ? 'Stop voice input' : 'Speak a message'}
                className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl transition disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 ${
                  listening
                    ? 'bg-[var(--color-error)] text-white animate-pulse'
                    : transcribing
                      ? 'text-[var(--color-accent)]'
                      : 'text-[var(--color-text-muted)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text)]'
                }`}
              >
                {listening ? (
                  <Square className="h-4 w-4 fill-current" />
                ) : transcribing ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Mic className="h-[18px] w-[18px]" />
                )}
              </button>
            )}
          </div>
          <button
            type="button"
            onClick={handleSend}
            disabled={disabled || !canSend}
            aria-label="Send message"
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[14px] bg-[var(--color-accent)] text-white shadow-[var(--shadow-md)] transition-all hover:bg-[var(--color-accent-dark)] hover:shadow-[var(--shadow-lg)] hover:-translate-y-0.5 active:translate-y-0 active:shadow-[var(--shadow-sm)] disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:translate-y-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2"
          >
            <ArrowUp className="h-5 w-5" strokeWidth={2.5} />
          </button>
        </div>

        <input
          ref={fileRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          capture="environment"
          onChange={pickImage}
          className="hidden"
        />
      </div>
    </div>
  )
}