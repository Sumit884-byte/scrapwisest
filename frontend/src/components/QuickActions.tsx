import { recommendationCount, useDevice } from '../lib/useDevice'

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
  const common = { width: 19, height: 19, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }
  if (name === 'receipt') return <svg {...common}><path d="M5 3h14v18l-3-2-4 2-4-2-3 2V3Z" /><path d="M8 8h8M8 12h6" /></svg>
  if (name === 'chat') return <svg {...common}><path d="M20 11.5a7.5 7.5 0 0 1-8 7.5 8.5 8.5 0 0 1-3.5-.8L4 20l1.2-3.4A7.5 7.5 0 1 1 20 11.5Z" /><path d="M8 11h.01M12 11h.01M16 11h.01" /></svg>
  if (name === 'language') return <svg {...common}><circle cx="12" cy="12" r="8.5" /><path d="M3.8 9h16.4M3.8 15h16.4M12 3.5c2 2.3 3 5.1 3 8.5s-1 6.2-3 8.5c-2-2.3-3-5.1-3-8.5s1-6.2 3-8.5Z" /></svg>
  if (name === 'compare') return <svg {...common}><path d="M7 4v16M7 4l-3 3M7 4l3 3M17 20V4M17 20l-3-3M17 20l3-3" /></svg>
  return <svg {...common}><path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0Z" /><circle cx="12" cy="10" r="2.3" /></svg>
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
          className="group flex min-h-12 items-center gap-2.5 rounded-xl border border-[#d4d7ca] bg-[#fffefa] px-3.5 py-3 text-left text-[14px] font-semibold text-[#263324] shadow-[0_2px_0_rgba(39,51,39,0.04)] transition hover:-translate-y-0.5 hover:border-[#9aad7f] hover:bg-[#fafff2] disabled:opacity-40 sm:px-4"
        >
          <span className="quick-icon" aria-hidden="true"><ActionIcon name={action.icon} /></span>
          <span className="quick-category">{action.category}</span>
          <span className="flex-1 leading-snug">{action.label}</span>
          <span className="quick-arrow" aria-hidden="true">→</span>
        </button>
      ))}
    </div>
  )
}
