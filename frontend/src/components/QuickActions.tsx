interface Props {
  onPick: (text: string) => void
  disabled: boolean
}

/** Suggestion chips for the two core flows — asking a price and reporting a
 *  sale — shown on the empty state so a first-time picker has a starting
 *  point. Payloads are the kind of Roman-Urdu messages the agent is built
 *  to parse. */
const ACTIONS: Array<{ icon: string; label: string; text: string }> = [
  { icon: '💵', label: 'What’s plastic worth?', text: 'plastic ka rate kya hai' },
  { icon: '🔩', label: 'What’s steel worth?', text: 'steel ka rate kya hai' },
  {
    icon: '📦',
    label: 'I sold something',
    text: 'maine 2 kilo plastic becha, 300 rupay mile, income colony ke qareeb',
  },
]

export function QuickActions({ onPick, disabled }: Props) {
  return (
    <div className="flex max-w-md flex-col items-stretch gap-2">
      {ACTIONS.map((action) => (
        <button
          key={action.text}
          type="button"
          disabled={disabled}
          onClick={() => onPick(action.text)}
          className="flex items-center gap-2.5 rounded-xl border border-slate-300 bg-white px-4 py-3 text-left text-[14px] font-medium text-slate-800 shadow-sm transition hover:border-slate-400 hover:bg-slate-50 disabled:opacity-40"
        >
          <span aria-hidden="true">{action.icon}</span>
          {action.label}
        </button>
      ))}
    </div>
  )
}
