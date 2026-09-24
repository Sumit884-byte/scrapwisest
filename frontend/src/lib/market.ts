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

/** True for the backend "no estimate" tier (never a comparable number). */
export function isUnavailableTier(tier: string | null | undefined): boolean {
  return normalizeTier(tier) === 'unavailable'
}

/** True for the verified seed fallback tier (early estimate, not local sales). */
export function isSeedTier(tier: string | null | undefined): boolean {
  return normalizeTier(tier) === 'seed'
}

/**
 * Upper-cased currency code, or null when missing/unknown.
 * Same rule as displayCurrency, exposed for verdict comparison.
 */
export function comparableCurrencyCode(currency: string | null | undefined): string | null {
  return displayCurrency(currency)
}

/**
 * Two per-kg values are only comparable when they share one currency.
 * Both-unknown (legacy bare amounts) counts as comparable; a known code
 * against unknown/missing, or two different codes, never compares.
 */
export function isComparableCurrency(
  a: string | null | undefined,
  b: string | null | undefined,
): boolean {
  const left = displayCurrency(a)
  const right = displayCurrency(b)
  if (left === null && right === null) return true
  if (left === null || right === null) return false
  return left === right
}

export type SaleVerdictStatus = 'ok' | 'seed' | 'unavailable' | 'not-comparable'

export type SaleVerdictDirection = 'less' | 'more' | 'same'

export interface SaleComparison {
  status: SaleVerdictStatus
  /** Currency code to display the difference with (null = bare amount). */
  currency: string | null
  paidPerKg: number
  typicalPerKg: number | null
  /** paidPerKg - typicalPerKg, rounded to 2 decimals. Null when not comparable. */
  diffPerKg: number | null
  direction: SaleVerdictDirection | null
}

export interface SaleVerdictInputs {
  material_type?: string | null
  price_per_kg?: number | null
  currency?: string | null
}

export interface SaleEstimateInputs {
  material_type?: string | null
  estimated_price_per_kg?: number | null
  currency?: string | null
  tier_used?: string | null
}

/**
 * Deterministic paid-vs-typical comparison for the Sale Verdict card.
 *
 * Rules (no backend change, no conversion, no invented numbers):
 * - per-kg only, never totals
 * - unavailable tier -> 'unavailable'
 * - non-finite values or mismatched materials -> 'not-comparable'
 *   (callers render "Not enough local data yet")
 * - different currencies (or known-vs-unknown) -> 'not-comparable'
 * - seed tier -> 'seed' (numbers still shown, caller must label as early)
 * - otherwise -> 'ok'
 */
export function compareSalePerKg(
  report: SaleVerdictInputs,
  estimate: SaleEstimateInputs,
): SaleComparison {
  const paid = report.price_per_kg ?? NaN
  const typical = estimate.estimated_price_per_kg ?? NaN
  const currency = displayCurrency(report.currency) ?? displayCurrency(estimate.currency)

  if (isUnavailableTier(estimate.tier_used)) {
    return {
      status: 'unavailable',
      currency,
      paidPerKg: paid,
      typicalPerKg: null,
      diffPerKg: null,
      direction: null,
    }
  }

  if (
    typeof paid !== 'number' ||
    typeof typical !== 'number' ||
    Number.isNaN(paid) ||
    Number.isNaN(typical) ||
    !Number.isFinite(paid) ||
    !Number.isFinite(typical)
  ) {
    return {
      status: 'not-comparable',
      currency,
      paidPerKg: paid,
      typicalPerKg: null,
      diffPerKg: null,
      direction: null,
    }
  }

  const reportMaterial = (report.material_type ?? '').trim().toLowerCase()
  const estimateMaterial = (estimate.material_type ?? '').trim().toLowerCase()
  if (reportMaterial && estimateMaterial && reportMaterial !== estimateMaterial) {
    return {
      status: 'not-comparable',
      currency,
      paidPerKg: paid,
      typicalPerKg: null,
      diffPerKg: null,
      direction: null,
    }
  }

  if (!isComparableCurrency(report.currency, estimate.currency)) {
    return {
      status: 'not-comparable',
      currency,
      paidPerKg: paid,
      typicalPerKg: null,
      diffPerKg: null,
      direction: null,
    }
  }

  const diff = Math.round((paid - typical) * 100) / 100
  const direction: SaleVerdictDirection = diff === 0 ? 'same' : diff < 0 ? 'less' : 'more'
  return {
    status: isSeedTier(estimate.tier_used) ? 'seed' : 'ok',
    currency,
    paidPerKg: paid,
    typicalPerKg: typical,
    diffPerKg: diff,
    direction,
  }
}

export interface SaleTrustInputs {
  needs_confirmation?: boolean | null
  is_anomalous?: boolean | null
}

/** Plain trust state: pending review means not counted yet. No tiers exposed. */
export function isSalePendingReview(report: SaleTrustInputs | null | undefined): boolean {
  if (!report) return false
  return Boolean(report.needs_confirmation) || Boolean(report.is_anomalous)
}

/** Accepted sales are trusted and counted toward local prices. */
export function isSaleTrusted(report: SaleTrustInputs | null | undefined): boolean {
  return !isSalePendingReview(report)
}

export interface VerdictEvidenceInputs {
  tier_used?: string | null
  local_report_count?: number | null
  city_report_count?: number | null
  country_report_count?: number | null
  evidence?: {
    source?: string | null
    report_count?: number | null
  } | null
}

/**
 * Meaningful local-sales count for the verdict's quiet evidence line.
 * Prefers the backend `PriceEvidence.report_count` when present; falls back
 * to the tier-scoped counts for older payloads without evidence. Returns
 * null when there is no meaningful count so callers never invent one.
 * Seed and unavailable tiers never produce a count.
 */
export function verdictEvidenceCount(
  price: VerdictEvidenceInputs | null | undefined,
): number | null {
  if (!price) return null
  if (isUnavailableTier(price.tier_used) || isSeedTier(price.tier_used)) return null
  const ev = price.evidence
  if (ev && typeof ev.report_count === 'number' && Number.isFinite(ev.report_count)) {
    const source = (ev.source ?? '').trim().toLowerCase()
    if (ev.report_count >= 1 && (source === 'reports' || source === '')) {
      return Math.floor(ev.report_count)
    }
    // Evidence explicitly says no reports (e.g. report_count 0) — respect it.
    if (source === 'reports' || source === 'seed' || source === 'unavailable') return null
  }
  const fallback = estimateSampleCount(price)
  return fallback >= 1 ? fallback : null
}

/** Quiet trust confirmation for an accepted sale. No tiers, no confidence. */
export function trustedSaleText(language?: AppLanguageCode | null): string {
  if (isHindi(language)) return 'सहेजा गया और स्थानीय भाव में गिना गया।'
  return 'Saved and counted in local rates.'
}

/** Plain pending explanation. Never exposes backend validation/anomaly reasons. */
export function pendingSaleText(language?: AppLanguageCode | null): string {
  if (isHindi(language))
    return 'यह बिक्री अभी स्थानीय भाव में नहीं गिनी गई क्योंकि विवरण असामान्य लग रहा है।'
  return "This sale isn't counted in local prices yet because the details look unusual."
}

/**
 * Quiet evidence line ("Based on 4 recent local sales").
 * Returns null when there is no meaningful count — never invents one.
 */
export function evidenceSalesText(
  price: VerdictEvidenceInputs | null | undefined,
  language?: AppLanguageCode | null,
): string | null {
  const count = verdictEvidenceCount(price)
  if (count === null) return null
  if (isHindi(language)) return `${count} हाल की स्थानीय बिक्री पर आधारित`
  return count === 1 ? 'Based on 1 recent local sale' : `Based on ${count} recent local sales`
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
