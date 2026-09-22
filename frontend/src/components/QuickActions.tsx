import { recommendationCount, useDevice } from '../lib/useDevice'
import { Receipt, MessageCircle, Languages, ArrowLeftRight, MapPin } from 'lucide-react'

interface Props {
  onPick: (text: string) => void
  disabled: boolean
}

const ACTIONS: Array<{ category: string; label: string; text: string; icon: ActionIconName }> = [
  { category: 'Log a sale', label: 'I sold something', text: 'I sold 2 kg of plastic for 300 rupees near Income Colony', icon: 'receipt' },
  { category: 'Roman Urdu', label: 'Plastic ka rate kya hai?', text: 'plastic ka rate kya hai Income Colony mein?', icon: 'chat' },
  { category: 'Urdu', label: 'پلاسٹک کا ریٹ کیا ہے؟', text: 'پلاسٹک کا ریٹ کیا ہے؟ انکم کالونی میں', icon: 'language' },
  { category: 'Telugu', label: 'Plastic dhar entha?', text: 'plastic dhar entha per kg?', icon: 'language' },
  { category: 'Compare prices', label: 'PET or HDPE plastic?', text: 'What is the difference in rate between PET and HDPE plastic?', icon: 'compare' },
  { category: 'Nearby prices', label: 'Rates near Income Colony', text: 'What are scrap rates in Income Colony today?', icon: 'location' },
]

type ActionIconName = 'receipt' | 'chat' | 'language' | 'compare' | 'location'

function ActionIcon({ name }: { name: ActionIconName }) {
  const className = "h-[18px] w-[18px] text-[var(--color-accent)]"
  if (name === 'receipt') return <Receipt className={className} />
  if (name === 'chat') return <MessageCircle className={className} />
  if (name === 'language') return <Languages className={className} />
  if (name === 'compare') return <ArrowLeftRight className={className} />
  return <MapPin className={className} />
}

export function QuickActions({ onPick, disabled }: Props) {
  const device = useDevice()
  const visible = ACTIONS.slice(0, recommendationCount(device))

  return (
    <div className="grid w-full grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3" data-device={device}>
      {visible.map((action) => (
        <button
          key={action.text}
          type="button"
          disabled={disabled}
          onClick={() => onPick(action.text)}
          className="group flex min-h-12 items-center gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3 text-left text-[14px] font-medium text-[var(--color-text)] shadow-[var(--shadow-sm)] transition-all hover:-translate-y-0.5 hover:border-[var(--color-accent)] hover:shadow-[var(--shadow-md)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-bg)] disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:translate-y-0"
        >
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--color-accent-soft)]" aria-hidden="true">
            <ActionIcon name={action.icon} />
          </span>
          <span className="flex-1 min-w-0">
            <span className="block text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)] mb-0.5">
              {action.category}
            </span>
            <span className="block leading-snug">{action.label}</span>
          </span>
          <span className="text-[var(--color-text-muted)] transition-all group-hover:text-[var(--color-accent)] group-hover:translate-x-0.5" aria-hidden="true">→</span>
        </button>
      ))}
    </div>
  )
}