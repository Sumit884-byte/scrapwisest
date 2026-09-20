/**
 * Minimal client for the ScrapSense FastAPI backend.
 *
 * The backend only exposes two endpoints:
 *   POST /chat   (multipart form: message, picker_id, optional image)
 *   GET  /health
 *
 * In dev, the Vite server proxies /chat and /health to the FastAPI backend
 * (see vite.config.ts), so requests stay same-origin here. In production,
 * set VITE_API_BASE to the backend origin and the same paths are used.
 */

import type { ChatResponse } from './types'

const BASE = import.meta.env.VITE_API_BASE ?? ''

export interface PostChatArgs {
  text: string
  image: File | null
  pickerId: string
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

export async function postChat({ text, image, pickerId }: PostChatArgs): Promise<ChatResponse> {
  const form = new FormData()
  if (text.trim()) form.append('message', text)
  form.append('picker_id', pickerId)
  if (image) form.append('image', image)

  const res = await fetch(`${BASE}/chat`, { method: 'POST', body: form })
  if (!res.ok) {
    throw new ApiError(res.status, await parseDetail(res))
  }
  return (await res.json()) as ChatResponse
}
