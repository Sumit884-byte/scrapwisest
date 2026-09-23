/**
 * Minimal client for the Scrapwisest FastAPI backend.
 *
 * Backend routes used by the client:
 *   POST /chat        (multipart form: message, picker_id, optional image)
 *   GET  /health
 *   POST /transcribe  (audio file → text + detected language)
 *   POST /speak       (text + optional language → mp3)
 *
 * In dev, the Vite server proxies these to the FastAPI backend
 * (see vite.config.ts), so requests stay same-origin here. In production,
 * set VITE_API_BASE to the backend origin and the same paths are used.
 */

import type { ChatResponse } from './types'

const BASE = import.meta.env.VITE_API_BASE ?? ''

export interface PostChatArgs {
  text: string
  image: File | null
  pickerId: string
  region?: string | null
  language?: string | null
  city?: string | null
  country?: string | null
  currency?: string | null
  neighborhood?: string | null
}

/**
 * A small error carrying the server's human-readable `detail` when the
 * backend rejects the request (e.g. "Image too large (max 8MB).").
 */
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function parseDetail(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown }
    if (typeof body.detail === 'string') return body.detail
    return 'Something went wrong. Please try again.'
  } catch {
    return 'Something went wrong. Please try again.'
  }
}

export async function postChat({
  text,
  image,
  pickerId,
  region,
  language,
  city,
  country,
  currency,
  neighborhood,
}: PostChatArgs): Promise<ChatResponse> {
  const form = new FormData()
  if (text.trim()) form.append('message', text)
  form.append('picker_id', pickerId)
  if (region) form.append('region', region)
  if (language && language !== 'auto') form.append('language', language)
  if (city?.trim()) form.append('city', city.trim())
  if (country?.trim()) form.append('country', country.trim())
  if (currency?.trim()) form.append('currency', currency.trim().toUpperCase())
  if (neighborhood?.trim()) form.append('neighborhood', neighborhood.trim())
  if (image) form.append('image', image)

  const res = await fetch(`${BASE}/chat`, { method: 'POST', body: form })
  if (!res.ok) {
    throw new ApiError(res.status, await parseDetail(res))
  }
  return (await res.json()) as ChatResponse
}

export interface Transcript {
  text: string
  language: string
}

export async function transcribeAudio(audio: Blob): Promise<Transcript> {
  const form = new FormData()
  const ext = audio.type.includes('mp4') ? 'mp4' : 'webm'
  form.append('file', audio, `clip.${ext}`)

  const res = await fetch(`${BASE}/transcribe`, { method: 'POST', body: form })
  if (!res.ok) {
    throw new ApiError(res.status, await parseDetail(res))
  }
  return (await res.json()) as Transcript
}

export async function fetchSpeech(
  text: string,
  language?: string,
  signal?: AbortSignal,
): Promise<Blob> {
  const form = new FormData()
  form.append('text', text)
  if (language) form.append('language', language)

  const res = await fetch(`${BASE}/speak`, { method: 'POST', body: form, signal })
  if (!res.ok) {
    throw new ApiError(res.status, await parseDetail(res))
  }
  return await res.blob()
}
