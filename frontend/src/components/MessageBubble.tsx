import { useRef, useState } from 'react'
import type { ChatMessage, PriceData } from '../lib/types'
import { speakReply, cancelSpeech } from '../lib/speech'
import { readSettings } from '../lib/settings'
import {
  compareSalePerKg,
  estimateSampleCount,
  evidenceSalesText,
  formatMoney,
  formatPerKg,
  isComparableCurrency,
  pendingSaleText,
  reportPlaceLabel,
  tierLabel,
  trustedSaleText,
} from '../lib/market'
import { Volume2, Square, RotateCcw, ExternalLink, AlertTriangle, CheckCircle2, TrendingUp, MapPin, FileText, BarChart3, Box } from 'lucide-react'

interface Props {
  message: ChatMessage
  onRetry: (message: ChatMessage) => void
  onFollowUp: (text: string) => void
}

function isRtlText(text: string): boolean {
  return /[\u0590-\u05FF\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]/.test(text)
}

export function MessageBubble({ message, onRetry, onFollowUp }: Props) {
  const [isPlaying, setIsPlaying] = useState(false)
  const playingRef = useRef(false)
  const isUser = message.role === 'user'
  const rtl = isRtlText(message.text)
  const time = new Date(message.timestamp).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  })

  const handleToggleSpeak = () => {
    if (playingRef.current) {
      playingRef.current = false
      cancelSpeech()
      setIsPlaying(false)
      return
    }
    playingRef.current = true
    setIsPlaying(true)
    void speakReply(message.text, () => {
      playingRef.current = false
      setIsPlaying(false)
    })
  }

  if (isUser) {
    return (
      <div className="flex justify-end message-enter" dir={rtl ? 'rtl' : 'ltr'}>
        <div className="max-w-[85%] rounded-[18px] rounded-tr-[6px] bg-[var(--color-user-bubble)] px-4 py-3 text-[var(--color-user-text)] shadow-[var(--shadow-sm)]">
          {message.image && (
            <img
              src={message.image.previewUrl}
              alt="Attached photo"
              className="mb-2.5 max-h-44 w-auto rounded-xl object-cover"
            />
          )}
          {message.text && (
            <p className="whitespace-pre-wrap break-words text-[15px] leading-[1.6]">{message.text}</p>
          )}
          <p className={`mt-1.5 text-[11px] text-white/50 ${rtl ? 'text-left' : 'text-right'}`}>{time}</p>
          {message.status === 'error' && (
            <div className={`mt-2 flex items-center gap-2 ${rtl ? 'justify-start' : 'justify-end'}`}>
              <span className="text-[11px] font-medium text-red-300">
                {message.error ?? 'Not sent'}
              </span>
              <button
                type="button"
                onClick={() => onRetry(message)}
                className="flex items-center gap-1 rounded-lg bg-white/15 px-2.5 py-1 text-[11px] font-semibold text-white transition hover:bg-white/25 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/50"
              >
                <RotateCcw className="h-3 w-3" />
                Retry
              </button>
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="flex justify-start message-enter" dir={rtl ? 'rtl' : 'ltr'}>
      <div className="max-w-[85%] rounded-[18px] rounded-tl-[6px] border border-[var(--color-card-border)] bg-[var(--color-surface)] px-4 py-3 text-[var(--color-text)] shadow-[var(--shadow-sm)]">
        <p className="whitespace-pre-wrap break-words text-[15px] leading-[1.6]">{message.text}</p>
        {message.reportData && message.priceData ? (
          <SaleVerdictCard
            report={message.reportData}
            price={message.priceData}
            onFollowUp={onFollowUp}
          />
        ) : (
          <>
            {message.priceData && <PriceCard data={message.priceData} />}
            {message.reportData && (
              <ReportReviewCard data={message.reportData} onFollowUp={onFollowUp} />
            )}
          </>
        )}
        <div className="mt-2.5 flex items-center justify-between gap-4 border-t border-[var(--color-card-border)] pt-2.5">
          <p className="text-[11px] text-[var(--color-text-muted)]">{time}</p>
          {message.text && (
            <button
              type="button"
              onClick={handleToggleSpeak}
              className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-surface)] ${
                isPlaying
                  ? 'bg-[var(--color-accent)] text-white animate-pulse'
                  : 'bg-[var(--color-accent-soft)] text-[var(--color-accent-dark)] hover:bg-[var(--color-accent)] hover:text-white'
              }`}
              title={isPlaying ? 'Stop listening' : 'Listen to response'}
            >
              {isPlaying ? (
                <>
                  <Square className="h-3 w-3 fill-current" />
                  Stop
                </>
              ) : (
                <>
                  <Volume2 className="h-3.5 w-3.5" />
                  Listen
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

function materialLabel(value: string, language: string): string {
  const key = value.replace(/^plastic_/, '').replace(/^metal_/, '').replace(/_/g, ' ')
  if (language === 'hi') {
    const hindi: Record<string, string> = {
      pet: 'पीईटी',
      hdpe: 'एचडीपीई',
      aluminum: 'एल्युमिनियम',
      steel: 'स्टील',
      glass: 'कांच',
      cardboard: 'गत्ता',
      'mixed paper': 'कागज',
    }
    return hindi[key.toLowerCase()] ?? key
  }
  return key.replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function confidenceLabel(value: number): string {
  if (value >= 0.75) return 'High confidence'
  if (value >= 0.45) return 'Medium confidence'
  return 'Early estimate'
}

function confidenceColor(value: number): string {
  if (value >= 0.75) return 'var(--color-accent)'
  if (value >= 0.45) return '#D97706'
  return 'var(--color-text-muted)'
}

function hindiPlace(location: string): string {
  const map: Record<string, string> = {
    india: 'भारत',
    pakistan: 'पाकिस्तान',
    bangladesh: 'बांग्लादेश',
    nepal: 'नेपाल',
    kolkata: 'कोलकाता',
    calcutta: 'कोलकाता',
    mumbai: 'मुंबई',
    delhi: 'दिल्ली',
    karachi: 'कराची',
    lahore: 'लाहौर',
  }
  return location
    .split(/([,\s]+)/)
    .map((part) => map[part.trim().toLowerCase()] ?? part)
    .join('')
    .replace(/\s+,/g, ',')
    .trim()
}

function RangeIndicator({ low, high, current }: { low: number; high: number; current: number }) {
  const range = high - low
  if (range <= 0) return null
  const position = ((current - low) / range) * 100
  const clampedPosition = Math.max(5, Math.min(95, position))

  return (
    <div className="mt-3">
      <div className="flex items-center justify-between text-[11px] font-medium text-[var(--color-text-muted)]">
        <span>{low}</span>
        <span>{high}</span>
      </div>
      <div className="relative mt-1.5 h-1.5 rounded-full bg-[var(--color-border)]">
        <div
          className="absolute top-0 h-full rounded-full bg-[var(--color-accent)]"
          style={{ width: `${clampedPosition}%` }}
        />
        <div
          className="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-[var(--color-accent)] bg-white shadow-[var(--shadow-sm)]"
          style={{ left: `${clampedPosition}%` }}
        />
      </div>
      <div className="mt-1 text-center text-[11px] font-semibold text-[var(--color-accent-dark)]">
        {current}
      </div>
    </div>
  )
}

function formatPileQty(value: number): string {
  if (value >= 10) return value.toFixed(0)
  return String(Number(value.toFixed(1)))
}

function volumeLine(data: PriceData, hindi: boolean): string {
  const kg = data.estimated_quantity_kg
  const liters = data.estimated_volume_liters
  if (kg == null && liters == null) return ''
  const kgText = kg != null ? `${formatPileQty(kg)} kg` : ''
  const literText = liters != null ? `${formatPileQty(liters)} L` : ''
  if (hindi) {
    if (kgText && literText) return `करीब ${kgText} (~${literText})`
    return `करीब ${kgText || literText}`
  }
  if (kgText && literText) return `About ${kgText} (~${literText})`
  return `About ${kgText || literText}`
}

function PriceCard({ data }: { data: PriceData }) {
  const language = readSettings().language
  const hindi = language === 'hi'
  const low = Math.round(data.min_price_per_kg ?? data.estimated_price_per_kg)
  const high = Math.round(data.max_price_per_kg ?? data.estimated_price_per_kg)
  const current = Math.round(data.estimated_price_per_kg)
  const sampleCount = estimateSampleCount(data)
  const unavailable = (data.tier_used ?? '').trim().toLowerCase() === 'unavailable'
  const rateText = unavailable
    ? '—'
    : formatPerKg(data.estimated_price_per_kg, data.currency)
  const place =
    !data.location || data.location.toLowerCase() === 'unknown'
      ? hindi
        ? 'आम शहर का भाव'
        : 'Typical city rate'
      : hindi
        ? hindiPlace(data.location)
        : data.location

  return (
    <div className="mt-3.5 rounded-[18px] border border-[var(--color-card-border)] bg-[var(--color-surface)] p-4 card-enter">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <p className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
            <TrendingUp className="h-3.5 w-3.5 text-[var(--color-accent)]" />
            {hindi ? 'कबाड़ भाव' : 'Estimated scrap rate'}
          </p>
          <div className="mt-1.5 flex items-baseline gap-2">
            <p className="text-[28px] font-bold leading-none tracking-tight text-[var(--color-accent-dark)]">
              {rateText}
            </p>
          </div>
          <p className="mt-2 inline-flex items-center gap-1 rounded-full bg-[var(--color-accent-soft)] px-2.5 py-1 text-[12px] font-semibold text-[var(--color-accent-dark)]">
            {materialLabel(data.material_type, language)}
          </p>
        </div>
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-[var(--color-accent-soft)] text-[var(--color-accent)]">
          <BarChart3 className="h-5 w-5" />
        </div>
      </div>

      {!unavailable && low !== high && <RangeIndicator low={low} high={high} current={current} />}

      <div className="mt-4 grid grid-cols-2 gap-3">
        <div className="rounded-xl bg-[var(--color-bg-chat)] p-3">
          <p className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
            <BarChart3 className="h-3 w-3" />
            {hindi ? 'रेंज' : 'Observed range'}
          </p>
          <p className="mt-1 text-[14px] font-semibold text-[var(--color-text)]">
            {unavailable ? '—' : `${low}–${high}`}
          </p>
        </div>
        <div className="rounded-xl bg-[var(--color-bg-chat)] p-3">
          <p className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
            <MapPin className="h-3 w-3" />
            {hindi ? 'स्थान' : 'Location'}
          </p>
          <p className="mt-1 text-[14px] font-semibold text-[var(--color-text)] truncate">{place}</p>
        </div>
        <div className="rounded-xl bg-[var(--color-bg-chat)] p-3">
          <p className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
            <CheckCircle2 className="h-3 w-3" style={{ color: confidenceColor(data.confidence) }} />
            {hindi ? 'विश्वास' : 'Confidence'}
          </p>
          <p className="mt-1 text-[14px] font-semibold" style={{ color: confidenceColor(data.confidence) }}>
            {hindi ? 'अनुमान' : confidenceLabel(data.confidence)}
          </p>
        </div>
        <div className="rounded-xl bg-[var(--color-bg-chat)] p-3">
          <p className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
            <FileText className="h-3 w-3" />
            {hindi ? 'रिपोर्ट' : 'Reports'}
          </p>
          <p className="mt-1 text-[14px] font-semibold text-[var(--color-text)]">
            {hindi ? `${sampleCount} रिपोर्ट` : `${sampleCount} report${sampleCount === 1 ? '' : 's'}`}
          </p>
        </div>
        {volumeLine(data, hindi) && (
          <div className="rounded-xl bg-[var(--color-bg-chat)] p-3 col-span-2">
            <p className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
              <Box className="h-3 w-3" />
              {hindi ? 'अनुमानित मात्रा' : 'Estimated volume'}
            </p>
            <p className="mt-1 text-[14px] font-semibold text-[var(--color-text)]">
              {volumeLine(data, hindi)}
            </p>
          </div>
        )}
      </div>

      <div className="mt-3 border-t border-[var(--color-card-border)] pt-3">
        <p className="text-[11px] text-[var(--color-text-muted)]">
          {hindi ? 'स्रोत: ' : 'Source: '}
          <span className="font-medium text-[var(--color-text)]">
            {tierLabel(data.tier_used, language)}
          </span>
          {!hindi && data.used_external_context ? ' + checked listings' : ''}
        </p>
        {data.external_sources && data.external_sources.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-2">
            {data.external_sources.slice(0, 2).map((source) => (
              <a
                key={source}
                href={source}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 rounded-lg bg-[var(--color-accent-soft)] px-2.5 py-1 text-[11px] font-medium text-[var(--color-accent-dark)] transition hover:bg-[var(--color-accent)] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
              >
                <ExternalLink className="h-3 w-3" />
                External source
              </a>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function ReportReviewCard({
  data,
  onFollowUp,
}: {
  data: NonNullable<ChatMessage['reportData']>
  onFollowUp: (text: string) => void
}) {
  const label = materialLabel(data.material_type, readSettings().language)
  const needsReview = data.needs_confirmation || data.is_anomalous
  const totalText = formatMoney(data.total_price, data.currency)
  const perKgText = formatPerKg(data.price_per_kg, data.currency)
  const placeText = reportPlaceLabel(data)

  return (
    <div className={`mt-3.5 rounded-[18px] border p-4 card-enter ${needsReview ? 'border-amber-200 bg-amber-50/80' : 'border-[var(--color-card-border)] bg-[var(--color-bg-chat)]'}`}>
      <p className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
        {needsReview ? (
          <AlertTriangle className="h-3.5 w-3.5 text-amber-600" />
        ) : (
          <CheckCircle2 className="h-3.5 w-3.5 text-[var(--color-accent)]" />
        )}
        Sale details
      </p>
      <div className="mt-3 grid grid-cols-2 gap-2.5">
        <div className="rounded-lg bg-[var(--color-surface)] p-2.5 border border-[var(--color-card-border)]">
          <p className="text-[10px] font-medium text-[var(--color-text-muted)]">Material</p>
          <p className="mt-0.5 text-[14px] font-semibold text-[var(--color-text)]">{label}</p>
        </div>
        <div className="rounded-lg bg-[var(--color-surface)] p-2.5 border border-[var(--color-card-border)]">
          <p className="text-[10px] font-medium text-[var(--color-text-muted)]">Quantity</p>
          <p className="mt-0.5 text-[14px] font-semibold text-[var(--color-text)]">{data.quantity_kg} kg</p>
        </div>
        <div className="rounded-lg bg-[var(--color-surface)] p-2.5 border border-[var(--color-card-border)]">
          <p className="text-[10px] font-medium text-[var(--color-text-muted)]">Total paid</p>
          <p className="mt-0.5 text-[14px] font-semibold text-[var(--color-text)]">{totalText}</p>
        </div>
        <div className="rounded-lg bg-[var(--color-surface)] p-2.5 border border-[var(--color-card-border)]">
          <p className="text-[10px] font-medium text-[var(--color-text-muted)]">Per kg</p>
          <p className="mt-0.5 text-[14px] font-semibold text-[var(--color-text)]">{perKgText}</p>
        </div>
        <div className="col-span-2 rounded-lg bg-[var(--color-surface)] p-2.5 border border-[var(--color-card-border)]">
          <p className="text-[10px] font-medium text-[var(--color-text-muted)]">Location</p>
          <p className="mt-0.5 text-[14px] font-semibold text-[var(--color-text)]">{placeText}</p>
        </div>
      </div>
      {needsReview && (
        <>
          <p className="mt-3 flex items-start gap-1.5 text-[12px] leading-snug text-amber-800">
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
            {data.confirmation_reason ?? data.anomaly_reason ?? 'This sale needs a quick review.'}
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => onFollowUp('The sale details are correct. Please accept this report.')}
              className="flex items-center gap-1.5 rounded-xl bg-[var(--color-accent)] px-3.5 py-2 text-[12px] font-semibold text-white transition hover:bg-[var(--color-accent-dark)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2"
            >
              <CheckCircle2 className="h-3.5 w-3.5" />
              Details are correct
            </button>
            <button
              type="button"
              onClick={() => onFollowUp('I need to correct the weight or price in my sale report.')}
              className="flex items-center gap-1.5 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3.5 py-2 text-[12px] font-semibold text-[var(--color-text)] transition hover:bg-[var(--color-surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2"
            >
              Correct details
            </button>
          </div>
        </>
      )}
    </div>
  )
}

function SaleVerdictCard({
  report,
  price,
  onFollowUp,
}: {
  report: NonNullable<ChatMessage['reportData']>
  price: NonNullable<ChatMessage['priceData']>
  onFollowUp: (text: string) => void
}) {
  const language = readSettings().language
  const hindi = language === 'hi'
  const verdict = compareSalePerKg(report, price)
  const needsReview = report.needs_confirmation || report.is_anomalous
  const label = materialLabel(report.material_type, language)
  const totalText = formatMoney(report.total_price, report.currency)
  const placeText = reportPlaceLabel(report)
  const paidText = formatPerKg(report.price_per_kg, report.currency)
  const typicalText =
    verdict.typicalPerKg !== null ? formatPerKg(verdict.typicalPerKg, price.currency) : '—'
  const evidenceText = evidenceSalesText(price, language)
  const currencyMismatch =
    verdict.status === 'not-comparable' &&
    !isComparableCurrency(report.currency, price.currency)

  const directionWord =
    verdict.direction === 'less'
      ? hindi
        ? 'कम'
        : 'less'
      : verdict.direction === 'more'
        ? hindi
          ? 'ज़्यादा'
          : 'more'
        : null
  const diffText =
    verdict.diffPerKg !== null && verdict.direction !== null && verdict.direction !== 'same'
      ? `~${formatPerKg(Math.abs(verdict.diffPerKg), verdict.currency)} ${directionWord}`
      : hindi
        ? 'आम भाव के लगभग बराबर'
        : 'About the same as typical'
  const hasComparison = verdict.status === 'ok' || verdict.status === 'seed'

  return (
    <div
      className={`mt-3.5 rounded-[18px] border p-4 card-enter ${needsReview ? 'border-amber-200 bg-amber-50/80' : 'border-[var(--color-card-border)] bg-[var(--color-bg-chat)]'}`}
    >
      <p className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
        <TrendingUp className="h-3.5 w-3.5 text-[var(--color-accent)]" />
        {hindi ? 'बिक्री नतीजा' : 'Sale verdict'}
      </p>
      <p className="mt-1.5 inline-flex items-center gap-1 rounded-full bg-[var(--color-accent-soft)] px-2.5 py-1 text-[12px] font-semibold text-[var(--color-accent-dark)]">
        {label}
      </p>

      <div className="mt-3 grid grid-cols-2 gap-2.5">
        <div className="rounded-xl bg-[var(--color-surface)] p-3 border border-[var(--color-card-border)]">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
            {hindi ? 'आपको मिला' : 'You got'}
          </p>
          <p className="mt-1 text-[18px] font-bold leading-tight text-[var(--color-text)]">{paidText}</p>
        </div>
        <div className="rounded-xl bg-[var(--color-surface)] p-3 border border-[var(--color-card-border)]">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
            {hindi ? 'यहाँ का आम भाव' : 'Typical here'}
          </p>
          <p className="mt-1 text-[18px] font-bold leading-tight text-[var(--color-accent-dark)]">
            {hasComparison ? typicalText : '—'}
          </p>
        </div>
      </div>

      {hasComparison ? (
        <div className="mt-2.5 rounded-xl bg-[var(--color-accent-soft)] px-3 py-2.5">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-accent-dark)]">
            {hindi ? 'अंतर' : 'Difference'}
          </p>
          <p className="mt-0.5 text-[15px] font-bold text-[var(--color-accent-dark)]">{diffText}</p>
        </div>
      ) : (
        <div className="mt-2.5 rounded-xl bg-[var(--color-surface)] border border-[var(--color-card-border)] px-3 py-2.5">
          <p className="text-[13px] font-semibold text-[var(--color-text)]">
            {hindi ? 'अभी आस-पास का पर्याप्त डेटा नहीं है' : 'Not enough local data yet'}
          </p>
          <p className="mt-0.5 text-[12px] leading-snug text-[var(--color-text-muted)]">
            {currencyMismatch
              ? hindi
                ? 'स्थानीय अनुमान अलग मुद्रा में है, इसलिए सीधी तुलना नहीं कर सकते।'
                : "The local estimate uses a different currency, so we can't compare directly."
              : hindi
                ? 'इस बिक्री के लिए अभी कोई तुलनीय स्थानीय भाव नहीं मिला, इसलिए तुलना नहीं दिखा रहे।'
                : "We couldn't find a comparable local rate for this sale, so there's no fair-price comparison yet."}
          </p>
        </div>
      )}

      {verdict.status === 'seed' && (
        <p className="mt-2.5 text-[12px] leading-snug text-[var(--color-text-muted)]">
          {hindi
            ? 'शुरुआती अनुमान — अभी स्थानीय बिक्री से नहीं है। पक्का करने से पहले 1–2 खरीदारों से पूछ लें।'
            : 'Early starting estimate — not from local sales yet. Check with 1–2 buyers before deciding.'}
        </p>
      )}

      {!needsReview && (
        <div className="mt-2.5 space-y-1">
          <p className="flex items-center gap-1.5 text-[11px] font-medium text-[var(--color-text)]">
            <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-[var(--color-accent)]" />
            {trustedSaleText(language)}
          </p>
          {evidenceText && (
            <p className="text-[11px] text-[var(--color-text-muted)]">{evidenceText}</p>
          )}
        </div>
      )}

      <div className="mt-3 grid grid-cols-2 gap-2.5">
        <div className="rounded-lg bg-[var(--color-surface)] p-2.5 border border-[var(--color-card-border)]">
          <p className="text-[10px] font-medium text-[var(--color-text-muted)]">Material</p>
          <p className="mt-0.5 text-[14px] font-semibold text-[var(--color-text)]">{label}</p>
        </div>
        <div className="rounded-lg bg-[var(--color-surface)] p-2.5 border border-[var(--color-card-border)]">
          <p className="text-[10px] font-medium text-[var(--color-text-muted)]">Quantity</p>
          <p className="mt-0.5 text-[14px] font-semibold text-[var(--color-text)]">{report.quantity_kg} kg</p>
        </div>
        <div className="rounded-lg bg-[var(--color-surface)] p-2.5 border border-[var(--color-card-border)]">
          <p className="text-[10px] font-medium text-[var(--color-text-muted)]">Total paid</p>
          <p className="mt-0.5 text-[14px] font-semibold text-[var(--color-text)]">{totalText}</p>
        </div>
        <div className="rounded-lg bg-[var(--color-surface)] p-2.5 border border-[var(--color-card-border)]">
          <p className="text-[10px] font-medium text-[var(--color-text-muted)]">Location</p>
          <p className="mt-0.5 text-[14px] font-semibold text-[var(--color-text)]">{placeText}</p>
        </div>
      </div>

      {needsReview && (
        <>
          <p className="mt-3 flex items-start gap-1.5 text-[12px] leading-snug text-amber-800">
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
            {pendingSaleText(language)}
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => onFollowUp('The sale details are correct. Please accept this report.')}
              className="flex items-center gap-1.5 rounded-xl bg-[var(--color-accent)] px-3.5 py-2 text-[12px] font-semibold text-white transition hover:bg-[var(--color-accent-dark)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2"
            >
              <CheckCircle2 className="h-3.5 w-3.5" />
              Details are correct
            </button>
            <button
              type="button"
              onClick={() => onFollowUp('I need to correct the weight or price in my sale report.')}
              className="flex items-center gap-1.5 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3.5 py-2 text-[12px] font-semibold text-[var(--color-text)] transition hover:bg-[var(--color-surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2"
            >
              Correct details
            </button>
          </div>
        </>
      )}
    </div>
  )
}