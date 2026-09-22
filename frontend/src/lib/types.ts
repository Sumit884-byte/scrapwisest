/** Shared types for the Scrapwisest chat client. */

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
  priceData?: PriceData
  reportData?: ReportData
}

export interface ReportData {
  material_type: string
  quantity_kg: number
  price_paid_pkr: number
  price_paid_pkr_per_kg: number
  location: string
  needs_confirmation: boolean
  confirmation_reason?: string | null
  is_anomalous: boolean
  anomaly_reason?: string | null
  anomaly_method?: string | null
}

export interface PriceData {
  material_type: string
  location: string
  estimated_price_per_kg: number
  min_price_per_kg?: number | null
  max_price_per_kg?: number | null
  confidence: number
  tier_used: string
  local_report_count: number
  city_report_count: number
  used_external_context?: boolean
  external_context?: string | null
  external_sources?: string[]
}

/** Shape of the backend's `POST /chat` success response. */
export interface ChatResponse {
  reply: string
  /** Backend always returns an empty list — the client owns the transcript. */
  history: unknown[]
  price_data?: PriceData | null
  report_data?: ReportData | null
  region?: string
}
