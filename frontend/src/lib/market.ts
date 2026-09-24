/**
 * Market-aware display helpers for the global backend contract.
 *
 * Backend source of truth:
 *   - money is always (total_price / price_per_kg / estimated_price_per_kg, currency)
 *   - place is always (country, city, neighborhood) + legacy `location` string
 *   - currency defaults to "unknown" (UNKNOWN_CURRENCY) when never named --
 *     never a guessed code (see backend/app/schemas/market.py)
 *   - PriceEstimate.tier_used is one of:
 *     "local" | "local+city" | "city" | "country" | "seed" | "unavailable"
 *
 * These helpers are pure and UI-agnostic so they can be unit-tested.
 * No currency conversion happens here -- values are displayed as returned.
 */

export const UNKNOWN_CURRENCY = 'unknown'

export type EstimateTier =
  | 'local'
  | 'local+city'
  | 'city'
  | 'country'
  | 'seed'
  | 'unavailable'

export type AppLanguageCode = string

function cleanPart(value: string | null | undefined): string | null {
  if (value === null || value === undefined) return null
  const text = value.trim()
  return text ? text : null
}

/** True when the currency is a real code (not missing/unknown). */
export function isKnownCurrency(currency: string | null | undefined): boolean {
  if (currency === null || currency === undefined) return false
  const text = currency.trim()
  if (!text) return false
  return text.toLowerCase() !== UNKNOWN_CURRENCY
}

/** Upper-cased currency code, or null when missing/unknown. Never invents one. */
export function displayCurrency(currency: string | null | undefined): string | null {
  if (!isKnownCurrency(currency)) return null
  return (currency as string).trim().toUpperCase()
}

function formatAmount(value: number): string {
  if (Number.isInteger(value)) return String(value)
  // Keep up to 2 decimals without inventing precision (e.g. USD 2.40 -> "2.4").
  // Preserve the backend value; only trim float noise.
  const rounded = Math.round(value * 100) / 100
  return String(rounded)
}

/**
 * Format a total price with its currency.
 * Unknown/missing currency falls back to the bare amount (never guesses PKR).
 */
export function formatMoney(
  amount: number | null | undefined,
  currency: string | null | undefined,
): string {
  if (amount === null || amount === undefined || Number.isNaN(amount)) return '—'
  const code = displayCurrency(currency)
  const text = formatAmount(amount)
  return code ? `${code} ${text}` : text
}

/** Format a per-kg price with its currency (e.g. "PKR 180/kg", "180/kg"). */
export function formatPerKg(
  amount: number | null | undefined,
  currency: string | null | undefined,
): string {
  if (amount === null || amount === undefined || Number.isNaN(amount)) return '—'
  const code = displayCurrency(currency)
  const text = formatAmount(amount)
  return code ? `${code} ${text}/kg` : `${text}/kg`
}

function normalizeTier(tier: string | null | undefined): string {
  return (tier ?? '').trim().toLowerCase()
}

function isHindi(language: AppLanguageCode | null | undefined): boolean {
  return language === 'hi'
}

/**
 * Map the real backend `tier_used` to a human label.
 * Every backend tier has a distinct label; `unavailable` is never shown as a
 * valid seed estimate and `country` is never shown as a seed estimate.
 */
export function tierLabel(
  tier: string | null | undefined,
  language?: AppLanguageCode | null,
): string {
  const key = normalizeTier(tier)
  if (isHindi(language)) {
    switch (key) {
      case 'local':
        return 'इलाके की रिपोर्ट'
      case 'local+city':
        return 'इलाका + शहर रिपोर्ट'
      case 'city':
        return 'शहर की रिपोर्ट'
      case 'country':
        return 'देश/बाज़ार रिपोर्ट'
      case 'seed':
        return 'शुरुआती बाज़ार अनुमान'
      case 'unavailable':
        return 'अनुमान उपलब्ध नहीं'
      default:
        return 'बाज़ार अनुमान'
    }
  }
  switch (key) {
    case 'local':
      return 'Neighborhood reports'
    case 'local+city':
      return 'Neighborhood + city reports'
    case 'city':
      return 'Wider-area reports'
    case 'country':
      return 'Country/market reports'
    case 'seed':
      return 'Seed market baseline'
    case 'unavailable':
      return 'No estimate available'
    default:
      return 'Market estimate'
  }
}

export interface ReportPlace {
  country?: string | null
  city?: string | null
  neighborhood?: string | null
  location?: string | null
}

/**
 * Compose a place line from the fields that actually exist.
 * Prefers structured (neighborhood, city, country); falls back to the legacy
 * `location` string when it is meaningful; otherwise returns null so the
 * caller can render a neutral "Unknown" instead of fabricated text.
 */
export function reportPlace(report: ReportPlace): string | null {
  const parts = [report.neighborhood, report.city, report.country]
    .map(cleanPart)
    .filter((part): part is string => part !== null)
  if (parts.length > 0) return parts.join(', ')
  const legacy = cleanPart(report.location)
  if (legacy && legacy.toLowerCase() !== 'unknown') return legacy
  return null
}

/** Neutral location text: real place when known, "Unknown" otherwise. */
export function reportPlaceLabel(report: ReportPlace): string {
  return reportPlace(report) ?? 'Unknown'
}

export interface EstimateCounts {
  tier_used?: string | null
  local_report_count?: number | null
  city_report_count?: number | null
  country_report_count?: number | null
}

/**
 * Reports pooled for the estimate's own tier. A `country` estimate must show
 * the country/market count (local/city counts can be 0 there), otherwise the
 * card would show "0 reports" for a valid country estimate.
 */
export function estimateSampleCount(data: EstimateCounts): number {
  const local = data.local_report_count ?? 0
  const city = data.city_report_count ?? 0
  const country = data.country_report_count ?? 0
  const tier = normalizeTier(data.tier_used)
  if (tier === 'country') return country
  if (tier === 'city') return city || country
  if (tier === 'local' || tier === 'local+city') return local || city || country
  return Math.max(local, city, country)
}
