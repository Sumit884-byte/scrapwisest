import { useEffect, useState } from 'react'
import {
  COUNTRY_SUGGESTIONS,
  CURRENCIES,
  LANGUAGES,
  citySuggestionOptions,
  currencyForCountry,
  filterSuggestions,
  placeLabel,
  type AppLanguage,
  type PickerSettings,
} from '../lib/settings'
import { SuggestField } from './SuggestField'
import { X, Check } from 'lucide-react'

interface Props {
  open: boolean
  settings: PickerSettings
  onChange: (patch: Partial<PickerSettings>) => void
  onClose: () => void
}

function languageLabel(id: AppLanguage): string {
  return LANGUAGES.find((item) => item.id === id)?.label ?? ''
}

function languageOptions(query: string) {
  const needle = query.trim().toLowerCase()
  const ranked = LANGUAGES.filter((item) => {
    if (!needle) return true
    return (
      item.label.toLowerCase().includes(needle) ||
      item.hint.toLowerCase().includes(needle) ||
      item.id.toLowerCase().includes(needle)
    )
  })
  return ranked.map((item) => ({
    value: item.id,
    label: item.label,
    hint: item.hint,
  }))
}

export function SettingsPanel({ open, settings, onChange, onClose }: Props) {
  const [languageDraft, setLanguageDraft] = useState(() => languageLabel(settings.language))

  useEffect(() => {
    if (open) setLanguageDraft(languageLabel(settings.language))
  }, [open, settings.language])

  if (!open) return null

  const place = placeLabel(settings)
  const countryMatches = filterSuggestions(settings.country, [...COUNTRY_SUGGESTIONS]).map((name) => ({
    value: name,
    label: name,
  }))
  const cityMatches = citySuggestionOptions(settings.city, settings.country).map((item) => ({
    value: item.city,
    label: item.city,
    hint: item.country,
  }))
  const currencyMatches = filterSuggestions(settings.currency, [...CURRENCIES]).map((code) => ({
    value: code,
    label: code,
  }))

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
              Language, place, and currency for rates and voice.
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

        <label id="language-label" className="mb-2.5 block text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
          Language
        </label>
        <SuggestField
          value={languageDraft}
          onChange={setLanguageDraft}
          placeholder="Type Hindi, Urdu, Hinglish…"
          labelId="language-label"
          options={languageOptions(languageDraft)}
          onPick={(option) => {
            onChange({ language: option.value as AppLanguage })
            setLanguageDraft(option.label)
          }}
        />

        <label id="country-label" className="mb-2.5 block text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
          Country
        </label>
        <SuggestField
          value={settings.country}
          placeholder="Type India, Pakistan…"
          labelId="country-label"
          options={countryMatches}
          onChange={(country) =>
            onChange({ country, currency: currencyForCountry(country) || settings.currency })
          }
          onPick={(option) =>
            onChange({
              country: option.value,
              currency: currencyForCountry(option.value) || settings.currency,
            })
          }
        />

        <label id="city-label" className="mb-2.5 block text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
          City
        </label>
        <SuggestField
          value={settings.city}
          placeholder="Type Delhi, Karachi, Kolkata…"
          labelId="city-label"
          options={cityMatches}
          onChange={(city) => onChange({ city })}
          onPick={(option) =>
            onChange({
              city: option.value,
              country: settings.country || option.hint || '',
              currency:
                settings.currency || currencyForCountry(settings.country || option.hint || ''),
            })
          }
        />

        <label className="mb-2.5 block text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
          Area
        </label>
        <input
          value={settings.neighborhood}
          onChange={(event) => onChange({ neighborhood: event.target.value })}
          placeholder="Optional neighborhood"
          className="mb-4 w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3.5 py-3 text-[15px] text-[var(--color-text)] placeholder:text-[var(--color-text-muted)] transition focus:border-[var(--color-accent)] focus:outline-none focus:ring-4 focus:ring-[var(--color-focus-ring)]"
        />

        <label id="currency-label" className="mb-2.5 block text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
          Currency
        </label>
        <SuggestField
          value={settings.currency}
          placeholder="Type PKR, INR, USD…"
          labelId="currency-label"
          options={currencyMatches}
          onChange={(currency) => onChange({ currency: currency.toUpperCase() })}
          onPick={(option) => onChange({ currency: option.value })}
        />

        {place && (
          <div className="flex items-center gap-1.5 rounded-xl bg-[var(--color-accent-soft)] px-3.5 py-2.5 text-[13px] font-medium text-[var(--color-accent-dark)]">
            <Check className="h-4 w-4" />
            Rates will use {place}
            {settings.currency ? ` · ${settings.currency}` : ''}.
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
