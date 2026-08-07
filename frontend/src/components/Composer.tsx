import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent, KeyboardEvent } from 'react'
import type { PendingImage } from '../lib/types'
import { isSpeechSupported, startDictation } from '../lib/speech'

interface Props {
  disabled: boolean
  onSend: (text: string, image: File | null) => void
}

/** Backend's own limits — enforced client-side so the picker gets immediate
 *  feedback instead of a 400 round-trip. */
const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/webp']
const MAX_IMAGE_BYTES = 8 * 1024 * 1024

export function Composer({ disabled, onSend }: Props) {
  const [text, setText] = useState('')
  const [image, setImage] = useState<PendingImage | null>(null)
  const [listening, setListening] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const taRef = useRef<HTMLTextAreaElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const stopRef = useRef<(() => void) | null>(null)
  const imageRef = useRef<PendingImage | null>(null)
  imageRef.current = image

  const speechSupported = isSpeechSupported()

  // Revoke the preview object URL on unmount (new URL from the last render).
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

  const pickImage = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = '' // allow re-selecting the same file
    if (!file) return

    if (!ACCEPTED_TYPES.includes(file.type)) {
      setError('Please choose a JPG, PNG, or WebP photo.')
      return
    }
    if (file.size > MAX_IMAGE_BYTES) {
      setError('Photo is too large (max 8 MB).')
      return
    }

    if (image) URL.revokeObjectURL(image.previewUrl)
    setImage({ file, previewUrl: URL.createObjectURL(file) })
    setError(null)
  }

  const clearImage = () => {
    if (image) URL.revokeObjectURL(image.previewUrl)
    setImage(null)
  }

  const startListening = () => {
    setError(null)
    setListening(true)
    stopRef.current = startDictation({
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
    })
  }

  const stopListening = () => {
    stopRef.current?.()
    setListening(false)
  }

  const handleSend = () => {
    const trimmed = text.trim()
    if (!trimmed && !image) {
      setError('Type a message or attach a photo first.')
      return
    }
    if (listening) stopListening()
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
    <div className="border-t border-slate-200 bg-white">
      <div className="mx-auto max-w-2xl px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-2 sm:px-4">
        {error && (
          <p className="mb-2 text-center text-[12px] font-medium text-red-600" role="alert">
            {error}
          </p>
        )}

        {image && (
          <div className="mb-2 flex items-center gap-2.5 rounded-xl border border-slate-200 bg-slate-50 px-2.5 py-2">
            <img
              src={image.previewUrl}
              alt="Photo preview"
              className="h-14 w-14 rounded-lg object-cover"
            />
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13px] font-medium text-slate-800">{image.file.name}</p>
              <p className="text-[11px] text-slate-500">{(image.file.size / 1024).toFixed(0)} KB</p>
            </div>
            <button
              type="button"
              onClick={clearImage}
              aria-label="Remove photo"
              className="rounded-md px-2 py-1 text-sm text-slate-500 transition hover:bg-slate-100 hover:text-slate-700"
            >
              ✕
            </button>
          </div>
        )}

        <div className="flex items-end gap-2">
          <div className="flex flex-1 items-end gap-1 rounded-2xl border border-slate-300 bg-slate-50 px-1.5 py-1.5 focus-within:border-slate-400 focus-within:ring-2 focus-within:ring-slate-200">
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              disabled={disabled}
              aria-label="Attach a photo"
              className="rounded-full p-2 text-lg leading-none text-slate-500 transition hover:bg-slate-200 disabled:opacity-40"
            >
              📷
            </button>
            <textarea
              ref={taRef}
              rows={1}
              value={text}
              onChange={handleTextChange}
              onKeyDown={handleKeyDown}
              placeholder="Type a message…"
              className="max-h-[132px] flex-1 resize-none bg-transparent py-1.5 text-[15px] text-slate-900 placeholder:text-slate-400 focus:outline-none"
            />
            {speechSupported && (
              <button
                type="button"
                onClick={listening ? stopListening : startListening}
                disabled={disabled}
                aria-label={listening ? 'Stop voice input' : 'Speak a message'}
                className={`rounded-full p-2 text-lg leading-none transition disabled:opacity-40 ${
                  listening
                    ? 'animate-pulse bg-red-500 text-white'
                    : 'text-slate-500 hover:bg-slate-200'
                }`}
              >
                {listening ? '■' : '🎤'}
              </button>
            )}
          </div>
          <button
            type="button"
            onClick={handleSend}
            disabled={disabled || !canSend}
            aria-label="Send message"
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-slate-800 text-lg text-white shadow-sm transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            ↑
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
