const STORAGE_KEY = 'scrapwisest.picker_settings'

export type AppLanguage =
  | 'auto'
  | 'en'
  | 'hi'
  | 'hi-latn'
  | 'ur'
  | 'ur-latn'
  | 'te'
  | 'te-latn'

export interface PickerSettings {
  language: AppLanguage
  city: string
  country: string
  currency: string
  neighborhood: string
}

export const LANGUAGES: { id: AppLanguage; label: string; hint: string }[] = [
  { id: 'auto', label: 'Auto', hint: 'Follow what you type or say' },
  { id: 'en', label: 'English', hint: 'English' },
  { id: 'hi', label: 'हिंदी', hint: 'Hindi' },
  { id: 'hi-latn', label: 'Hinglish', hint: 'Hindi in English letters' },
  { id: 'ur', label: 'اردو', hint: 'Urdu' },
  { id: 'ur-latn', label: 'Roman Urdu', hint: 'Urdu in English letters' },
  { id: 'te', label: 'తెలుగు', hint: 'Telugu' },
  { id: 'te-latn', label: 'Telugu', hint: 'Telugu in English letters' },
]

export const COUNTRIES = ['Pakistan', 'India', 'Bangladesh', 'Nepal', 'Other'] as const

export const CURRENCIES = ['PKR', 'INR', 'BDT', 'NPR', 'USD'] as const

export const DEFAULT_SETTINGS: PickerSettings = {
  language: 'auto',
  city: '',
  country: '',
  currency: '',
  neighborhood: '',
}

function speechCode(language: AppLanguage): string | undefined {
  if (language === 'auto') return undefined
  if (language === 'en') return 'en'
  if (language.startsWith('hi')) return 'hi'
  if (language.startsWith('ur')) return 'ur'
  if (language.startsWith('te')) return 'te'
  return language.slice(0, 2)
}

export function speechLocale(language: AppLanguage): string {
  const code = speechCode(language)
  if (code === 'hi') return 'hi-IN'
  if (code === 'ur') return 'ur-IN'
  if (code === 'te') return 'te-IN'
  if (code === 'en') return 'en-IN'
  return 'en-IN'
}

export function readSettings(): PickerSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { ...DEFAULT_SETTINGS }
    const parsed = JSON.parse(raw) as Partial<PickerSettings>
    return {
      language: LANGUAGES.some((item) => item.id === parsed.language)
        ? (parsed.language as AppLanguage)
        : 'auto',
      city: typeof parsed.city === 'string' ? parsed.city : '',
      country: typeof parsed.country === 'string' ? parsed.country : '',
      currency: typeof parsed.currency === 'string' ? parsed.currency : '',
      neighborhood: typeof parsed.neighborhood === 'string' ? parsed.neighborhood : '',
    }
  } catch {
    return { ...DEFAULT_SETTINGS }
  }
}

export function writeSettings(next: PickerSettings): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
  } catch {
    /* private mode */
  }
}

export function preferredSpeechCode(settings: PickerSettings): string | undefined {
  return speechCode(settings.language)
}

export function placeLabel(settings: PickerSettings): string {
  return [settings.city.trim(), settings.country.trim()].filter(Boolean).join(', ')
}

export function marketLabel(settings: PickerSettings): string | null {
  const place = placeLabel(settings)
  const bits = [place, settings.currency.trim().toUpperCase()].filter(Boolean)
  return bits.length ? bits.join(' · ') : null
}
