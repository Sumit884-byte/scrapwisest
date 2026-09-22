import { useState } from 'react'
import type { ChatMessage, PriceData } from '../lib/types'
import { isSpeechSynthesisSupported, speakText, cancelSpeech } from '../lib/speech'

interface Props {
  message: ChatMessage
  onRetry: (message: ChatMessage) => void
  onFollowUp: (text: string) => void
}

/** One chat bubble. User messages are dark and right-aligned; assistant
 *  replies are white cards on the left. A failed user message shows a small
 *  "Not sent / Retry" affordance. Assistant messages include a Listen button. */
export function MessageBubble({ message, onRetry, onFollowUp }: Props) {
  const [isPlaying, setIsPlaying] = useState(false)
  const isUser = message.role === 'user'
  const time = new Date(message.timestamp).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  })

  const handleToggleSpeak = () => {
    if (isPlaying) {
      cancelSpeech()
      setIsPlaying(false)
    } else {
      setIsPlaying(true)
      speakText(message.text, () => setIsPlaying(false))
    }
  }

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-tr-md bg-slate-800 px-3.5 py-2.5 text-slate-50 shadow-sm">
          {message.image && (
            <img
              src={message.image.previewUrl}
              alt="Attached photo"
              className="mb-2 max-h-44 w-auto rounded-lg object-cover"
            />
          )}
          {message.text && (
            <p className="whitespace-pre-wrap break-words text-[15px] leading-snug">{message.text}</p>
          )}
          <p className="mt-1 text-right text-[10px] text-slate-400">{time}</p>
          {message.status === 'error' && (
            <div className="mt-1.5 flex items-center justify-end gap-2">
              <span className="text-[11px] font-medium text-red-300">
                {message.error ?? 'Not sent'}
              </span>
              <button
                type="button"
                onClick={() => onRetry(message)}
                className="rounded-md bg-slate-600 px-2.5 py-1 text-[11px] font-semibold text-white transition hover:bg-slate-500"
              >
                Retry
              </button>
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] rounded-2xl rounded-tl-md border border-slate-200 bg-white px-3.5 py-2.5 text-slate-800 shadow-sm">
        <p className="whitespace-pre-wrap break-words text-[15px] leading-snug">{message.text}</p>
        {message.priceData && <PriceCard data={message.priceData} />}
        {message.reportData && (
          <ReportReviewCard data={message.reportData} onFollowUp={onFollowUp} />
        )}
        <div className="mt-1.5 flex items-center justify-between gap-4">
          <p className="text-[10px] text-slate-400">{time}</p>
          {isSpeechSynthesisSupported() && message.text && (
            <button
              type="button"
              onClick={handleToggleSpeak}
              className="flex items-center gap-1 text-[11px] font-medium text-emerald-700 hover:text-emerald-800 focus:outline-none"
              title={isPlaying ? 'Stop listening' : 'Listen to response'}
            >
              <span>{isPlaying ? '🔊 Stop' : '🔊 Listen'}</span>
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

function materialLabel(value: string): string {
  return value
    .replace(/^plastic_/, '')
    .replace(/^metal_/, '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function tierLabel(tier: string): string {
  if (tier === 'local' || tier === 'local+city') return 'Neighborhood reports'
  if (tier === 'city') return 'Wider-area reports'
  return 'Seed market baseline'
}

function confidenceLabel(value: number): string {
  if (value >= 0.75) return 'High confidence'
  if (value >= 0.45) return 'Medium confidence'
  return 'Early estimate'
}

function PriceCard({ data }: { data: PriceData }) {
  const low = Math.round(data.min_price_per_kg ?? data.estimated_price_per_kg)
  const high = Math.round(data.max_price_per_kg ?? data.estimated_price_per_kg)
  const sampleCount = data.local_report_count || data.city_report_count

  return (
    <div className="mt-3 rounded-xl border border-emerald-200 bg-emerald-50/70 p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-emerald-700">Estimated scrap rate</p>
          <p className="mt-0.5 text-sm font-semibold text-slate-800">{materialLabel(data.material_type)}</p>
        </div>
        <p className="text-right text-lg font-bold text-emerald-800">{data.estimated_price_per_kg} PKR/kg</p>
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2 text-[11px] text-slate-600">
        <span>Observed range: {low}–{high}</span>
        <span className="text-right">{confidenceLabel(data.confidence)}</span>
        <span>{data.location}</span>
        <span className="text-right">{sampleCount} report{sampleCount === 1 ? '' : 's'}</span>
      </div>
      <p className="mt-2 text-[11px] text-slate-500">
        Source: {tierLabel(data.tier_used)}{data.used_external_context ? ' + Tavily market context' : ''}
      </p>
      {data.external_sources && data.external_sources.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-x-2 gap-y-1">
          {data.external_sources.slice(0, 2).map((source) => (
            <a
              key={source}
              href={source}
              target="_blank"
              rel="noreferrer"
              className="text-[10px] text-emerald-700 underline hover:text-emerald-900"
            >
              External source
            </a>
          ))}
        </div>
      )}
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
  const label = materialLabel(data.material_type)
  const needsReview = data.needs_confirmation || data.is_anomalous

  return (
    <div className={`mt-3 rounded-xl border p-3 ${needsReview ? 'border-amber-200 bg-amber-50/80' : 'border-slate-200 bg-slate-50'}`}>
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Sale details</p>
      <div className="mt-1 grid grid-cols-2 gap-x-3 gap-y-1 text-[12px] text-slate-700">
        <span>{label}</span>
        <span className="text-right">{data.quantity_kg} kg</span>
        <span>{data.price_paid_pkr} PKR total</span>
        <span className="text-right">{data.price_paid_pkr_per_kg} PKR/kg</span>
        <span className="col-span-2">{data.location}</span>
      </div>
      {needsReview && (
        <>
          <p className="mt-2 text-[11px] leading-snug text-amber-800">
            {data.confirmation_reason ?? data.anomaly_reason ?? 'This sale needs a quick review.'}
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => onFollowUp('The sale details are correct. Please accept this report.')}
              className="rounded-lg bg-amber-700 px-2.5 py-1.5 text-[11px] font-semibold text-white hover:bg-amber-800"
            >
              Details are correct
            </button>
            <button
              type="button"
              onClick={() => onFollowUp('I need to correct the weight or price in my sale report.')}
              className="rounded-lg border border-amber-300 bg-white px-2.5 py-1.5 text-[11px] font-semibold text-amber-800 hover:bg-amber-100"
            >
              Correct details
            </button>
          </div>
        </>
      )}
    </div>
  )
}
