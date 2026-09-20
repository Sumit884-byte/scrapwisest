/** Shared types for the ScrapSense chat client. */

export type Role = 'user' | 'assistant'

export type MessageStatus = 'sending' | 'sent' | 'error'

/** A user-attached photo (kept only for the composer preview + the request). */
export interface PendingImage {
  file: File
  /** Object URL for the thumbnail preview — revoke after send/dismiss. */
  previewUrl: string
}

export interface ChatMessage {
  id: string
  role: Role
  text: string
  /** Present only on user messages that carried a photo. */
  image?: PendingImage
  timestamp: number
  status: MessageStatus
  error?: string
}

/** Shape of the backend's `POST /chat` success response. */
export interface ChatResponse {
  reply: string
  /** Backend always returns an empty list — the client owns the transcript. */
  history: unknown[]
}
