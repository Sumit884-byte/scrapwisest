import { COUNTRIES, LANGUAGES, placeLabel, type PickerSettings } from '../lib/settings'
import { X, Check } from 'lucide-react'

interface Props {
  open: boolean
  settings: PickerSettings
  onChange: (patch: Partial<PickerSettings>) => void
  onClose: () => void
}

export function SettingsPanel({ open, settings, onChange, onClose }: Props) {
  if (!open) return null

  const place = placeLabel(settings)

  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center sm:items-center">
      <button
        type="button"
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        aria-label="Close settings"
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-labelledby="settings-title"
        className="relative z-10 w-full max-w-md rounded-t-[24px] sm:rounded-[24px] border border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-[var(--shadow-xl)] max-h-[90vh] overflow-y-auto"
      >
        <div className="mb-5 flex items-start justify-between gap-3">
          <div>
            <h2 id="settings-title" className="text-[18px] font-bold text-[var(--color-text)]">
              Settings
            </h2>
            <p className="mt-0.5 text-[13px] text-[var(--color-text-muted)]">
              Language, city, and country for rates and voice.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl text-[var(--color-text-muted)] transition hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2"
            aria-label="Close settings"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <p className="mb-2.5 text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
          Language
        </p>
        <div className="mb-5 grid grid-cols-2 gap-2">
          {LANGUAGES.map((item) => {
            const selected = settings.language === item.id
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => onChange({ language: item.id })}
                className={`relative rounded-xl border px-3.5 py-3 text-left transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 ${
                  selected
                    ? 'border-[var(--color-accent)] bg-[var(--color-accent-soft)] shadow-[var(--shadow-sm)]'
                    : 'border-[var(--color-border)] bg-[var(--color-surface)] hover:bg-[var(--color-surface-hover)]'
                }`}
              >
                {selected && (
                  <span className="absolute top-2 right-2 flex h-4 w-4 items-center justify-center rounded-full bg-[var(--color-accent)] text-white">
                    <Check className="h-3 w-3" strokeWidth={3} />
                  </span>
                )}
                <span className={`block text-[14px] font-semibold ${selected ? 'text-[var(--color-accent-dark)]' : 'text-[var(--color-text)]'}`}>
                  {item.label}
                </span>
                <span className="block text-[11px] text-[var(--color-text-muted)]">{item.hint}</span>
              </button>
            )
          })}
        </div>

        <label className="mb-2.5 block text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
          Country
        </label>
        <div className="mb-2.5 flex flex-wrap gap-2">
          {COUNTRIES.filter((item) => item !== 'Other').map((country) => {
            const selected = settings.country === country
            return (
              <button
                key={country}
                type="button"
                onClick={() => onChange({ country })}
                className={`rounded-full border px-3.5 py-1.5 text-[13px] font-semibold transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 ${
                  selected
                    ? 'border-[var(--color-accent)] bg-[var(--color-accent-soft)] text-[var(--color-accent-dark)]'
                    : 'border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-muted)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text)]'
                }`}
              >
                {country}
              </button>
            )
          })}
        </div>
        <input
          value={settings.country}
          onChange={(event) => onChange({ country: event.target.value })}
          placeholder="Or type another country"
          className="mb-4 w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3.5 py-3 text-[15px] text-[var(--color-text)] placeholder:text-[var(--color-text-muted)] transition focus:border-[var(--color-accent)] focus:outline-none focus:ring-4 focus:ring-[var(--color-focus-ring)]"
        />

        <label className="mb-2.5 block text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
          City
        </label>
        <input
          value={settings.city}
          onChange={(event) => onChange({ city: event.target.value })}
          placeholder="Karachi, Lahore, Kolkata…"
          className="mb-4 w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3.5 py-3 text-[15px] text-[var(--color-text)] placeholder:text-[var(--color-text-muted)] transition focus:border-[var(--color-accent)] focus:outline-none focus:ring-4 focus:ring-[var(--color-focus-ring)]"
        />

        {place && (
          <div className="flex items-center gap-1.5 rounded-xl bg-[var(--color-accent-soft)] px-3.5 py-2.5 text-[13px] font-medium text-[var(--color-accent-dark)]">
            <Check className="h-4 w-4" />
            Rates will use {place}.
          </div>
        )}

        <div className="mt-5 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl bg-[var(--color-accent)] px-5 py-2.5 text-[14px] font-semibold text-white transition hover:bg-[var(--color-accent-dark)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  )
}