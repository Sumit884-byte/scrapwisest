import { recommendationCount, useDevice } from '../lib/useDevice'
import { BookOpen, Recycle, FlaskConical, Store, Languages, MessageCircle } from 'lucide-react'

interface Props {
  onPick: (text: string) => void
  disabled: boolean
}

const ACTIONS: Array<{
  category: string
  label: string
  hint: string
  text: string
  icon: ActionIconName
}> = [
  { category: 'Log a sale', label: 'I sold something', hint: 'Record in the khata', text: 'I sold something', icon: 'book' },
  { category: 'Roman Urdu', label: 'Plastic ka rate?', hint: 'Ask a local rate', text: 'Plastic ka rate kya hai?', icon: 'recycle' },
  { category: 'Urdu', label: 'پلاسٹک کا ریٹ؟', hint: 'Rate in Urdu', text: 'پلاسٹک کا ریٹ کیا ہے؟', icon: 'language' },
  { category: 'Telugu', label: 'Plastic dhar entha?', hint: 'Rate in Telugu', text: 'plastic dhar entha per kg?', icon: 'chat' },
  { category: 'Compare', label: 'PET vs HDPE', hint: 'Which pays more', text: 'PET or HDPE plastic?', icon: 'flask' },
  { category: 'Nearby', label: 'Nearby rates', hint: 'In your city', text: 'What are scrap rates near me today?', icon: 'store' },
]

type ActionIconName = 'book' | 'recycle' | 'language' | 'chat' | 'flask' | 'store'

function ActionIcon({ name }: { name: ActionIconName }) {
  const className = 'h-5 w-5'
  if (name === 'book') return <BookOpen className={className} />
  if (name === 'recycle') return <Recycle className={className} />
  if (name === 'language') return <Languages className={className} />
  if (name === 'chat') return <MessageCircle className={className} />
  if (name === 'flask') return <FlaskConical className={className} />
  return <Store className={className} />
}

export function QuickActions({ onPick, disabled }: Props) {
  const device = useDevice()
  const visible = ACTIONS.slice(0, recommendationCount(device))

  return (
    <div className="grid w-full grid-cols-2 gap-2.5" data-device={device}>
      {visible.map((action) => (
        <button
          key={action.text}
          type="button"
          disabled={disabled}
          onClick={() => onPick(action.text)}
          className="group flex min-h-[7.5rem] flex-col justify-between rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3.5 text-left shadow-[var(--shadow-sm)] transition active:translate-y-0.5 disabled:opacity-40"
        >
          <span className="flex items-start justify-between gap-2">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--color-accent-soft)] text-[var(--color-accent-dark)]">
              <ActionIcon name={action.icon} />
            </span>
            <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--color-copper)]">
              {action.category}
            </span>
          </span>
          <span>
            <span className="block text-[15px] font-semibold leading-tight text-[var(--color-text)]">
              {action.label}
            </span>
            <span className="mt-0.5 block text-[11px] text-[var(--color-text-muted)]">{action.hint}</span>
          </span>
        </button>
      ))}
    </div>
  )
}
