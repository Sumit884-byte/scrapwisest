import { COUNTRIES, LANGUAGES, placeLabel, type PickerSettings } from '../lib/settings'

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
        className="absolute inset-0 bg-[#162235]/40"
        aria-label="Close settings"
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-labelledby="settings-title"
        className="relative z-10 w-full max-w-md rounded-t-3xl border border-[#d9d5ca] bg-[#fbfaf6] p-5 shadow-xl sm:rounded-3xl"
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 id="settings-title" className="text-[17px] font-bold text-[#162235]">
              Settings
            </h2>
            <p className="mt-0.5 text-[12px] text-[#71806f]">
              Language, city, and country for rates and voice.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full px-2 py-1 text-[13px] font-semibold text-[#65705f] hover:bg-[#f0eee6]"
          >
            Done
          </button>
        </div>

        <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.12em] text-[#8b6b3e]">
          Language
        </p>
        <div className="mb-4 grid grid-cols-2 gap-2">
          {LANGUAGES.map((item) => {
            const selected = settings.language === item.id
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => onChange({ language: item.id })}
                className={`rounded-2xl border px-3 py-2.5 text-left transition ${
                  selected
                    ? 'border-[#3f6b4c] bg-[#eef4e2] text-[#263324]'
                    : 'border-[#d8d8c8] bg-white text-[#3d4a3f] hover:bg-[#f7f5ed]'
                }`}
              >
                <span className="block text-[14px] font-semibold">{item.label}</span>
                <span className="block text-[11px] text-[#71806f]">{item.hint}</span>
              </button>
            )
          })}
        </div>

        <label className="mb-2 block text-[11px] font-bold uppercase tracking-[0.12em] text-[#8b6b3e]">
          Country
        </label>
        <div className="mb-2 flex flex-wrap gap-2">
          {COUNTRIES.filter((item) => item !== 'Other').map((country) => {
            const selected = settings.country === country
            return (
              <button
                key={country}
                type="button"
                onClick={() => onChange({ country })}
                className={`rounded-full border px-3 py-1.5 text-[13px] font-semibold ${
                  selected
                    ? 'border-[#3f6b4c] bg-[#eef4e2] text-[#263324]'
                    : 'border-[#d8d8c8] bg-white text-[#65705f]'
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
          className="mb-3 w-full rounded-2xl border border-[#d8d8c8] bg-white px-3 py-3 text-[15px] text-[#1d2a22] placeholder:text-[#9aa196] focus:border-[#3f6b4c] focus:outline-none"
        />

        <label className="mb-2 block text-[11px] font-bold uppercase tracking-[0.12em] text-[#8b6b3e]">
          City
        </label>
        <input
          value={settings.city}
          onChange={(event) => onChange({ city: event.target.value })}
          placeholder="Karachi, Lahore, Kolkata…"
          className="mb-3 w-full rounded-2xl border border-[#d8d8c8] bg-white px-3 py-3 text-[15px] text-[#1d2a22] placeholder:text-[#9aa196] focus:border-[#3f6b4c] focus:outline-none"
        />

        {place && (
          <p className="text-[12px] text-[#3f6b4c]">Rates will use {place}.</p>
        )}
      </div>
    </div>
  )
}
