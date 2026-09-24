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
  /** Generic backend contract: total money received for the sale. */
  total_price: number
  /** Generic backend contract: derived rate per kilogram. */
  price_per_kg: number
  /** ISO currency code from the backend (e.g. PKR, INR, USD, or "unknown"). */
  currency?: string | null
  country?: string | null
  city?: string | null
  neighborhood?: string | null
  /** Legacy free-form place string; prefer country/city/neighborhood. */
  location?: string | null
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
  /** Currency the estimate is denominated in ("unknown" when never named). */
  currency?: string | null
  min_price_per_kg?: number | null
  max_price_per_kg?: number | null
  confidence: number
  /** Backend tier: "local" | "local+city" | "city" | "country" | "seed" | "unavailable" */
  tier_used: string
  local_report_count: number
  city_report_count: number
  /** Reports pooled at the country/market scope. Defaults to 0 downstream. */
  country_report_count?: number | null
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
