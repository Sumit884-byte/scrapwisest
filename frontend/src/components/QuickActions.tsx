import { recommendationCount, useDevice } from '../lib/useDevice'

interface Props {
  onPick: (text: string) => void
  disabled: boolean
}

/** English prompts — count shown depends on phone / tablet / desktop. */
const ACTIONS: Array<{ icon: string; label: string; text: string }> = [
  { icon: '💵', label: 'What’s plastic worth?', text: 'What is the rate for plastic?' },
  { icon: '🔩', label: 'What’s steel worth?', text: 'What is the rate for steel?' },
  {
    icon: '📦',
    label: 'I sold something',
    text: 'I sold 2 kg of plastic for 300 rupees near Income Colony',
  },
  { icon: '🥫', label: 'Aluminum rate', text: 'What is the rate for aluminum per kg?' },
  { icon: '📄', label: 'Cardboard price', text: 'What is cardboard worth per kg?' },
  { icon: '🍾', label: 'Glass rate', text: 'What is the rate for glass?' },
  {
    icon: '♻️',
    label: 'PET vs HDPE',
    text: 'What is the difference in rate between PET and HDPE plastic?',
  },
  {
    icon: '📍',
    label: 'Rates near me',
    text: 'What are scrap rates in Income Colony today?',
  },
  {
    icon: '⚖️',
    label: 'Mixed metals',
    text: 'I have mixed steel and aluminum. What should I ask for per kg?',
  },
]

export function QuickActions({ onPick, disabled }: Props) {
  const device = useDevice()
  const visible = ACTIONS.slice(0, recommendationCount(device))

  return (
    <div
      className="grid w-full grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3"
      data-device={device}
    >
      {visible.map((action) => (
        <button
          key={action.text}
          type="button"
          disabled={disabled}
          onClick={() => onPick(action.text)}
          className="flex min-h-12 items-center gap-2.5 rounded-xl border border-slate-300 bg-white px-3.5 py-3 text-left text-[14px] font-medium text-slate-800 shadow-sm transition hover:border-slate-400 hover:bg-slate-50 disabled:opacity-40 sm:px-4"
        >
          <span className="shrink-0" aria-hidden="true">
            {action.icon}
          </span>
          <span className="leading-snug">{action.label}</span>
        </button>
      ))}
    </div>
  )
}
