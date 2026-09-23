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

export const COUNTRIES = ['Pakistan', 'India', 'Bangladesh', 'Nepal', 'United States', 'Other'] as const

export const COUNTRY_SUGGESTIONS = [
  'Pakistan',
  'India',
  'Bangladesh',
  'Nepal',
  'United States',
  'Sri Lanka',
  'Afghanistan',
  'United Arab Emirates',
  'United Kingdom',
] as const

export const CITY_SUGGESTIONS: { city: string; country: string }[] = [
  { city: 'Karachi', country: 'Pakistan' },
  { city: 'Lahore', country: 'Pakistan' },
  { city: 'Multan', country: 'Pakistan' },
  { city: 'Islamabad', country: 'Pakistan' },
  { city: 'Faisalabad', country: 'Pakistan' },
  { city: 'Peshawar', country: 'Pakistan' },
  { city: 'Rawalpindi', country: 'Pakistan' },
  { city: 'Quetta', country: 'Pakistan' },
  { city: 'Hyderabad', country: 'Pakistan' },
  { city: 'Sialkot', country: 'Pakistan' },
  { city: 'Delhi', country: 'India' },
  { city: 'Mumbai', country: 'India' },
  { city: 'Kolkata', country: 'India' },
  { city: 'Chennai', country: 'India' },
  { city: 'Hyderabad', country: 'India' },
  { city: 'Bengaluru', country: 'India' },
  { city: 'Ahmedabad', country: 'India' },
  { city: 'Pune', country: 'India' },
  { city: 'Jaipur', country: 'India' },
  { city: 'Lucknow', country: 'India' },
  { city: 'Kanpur', country: 'India' },
  { city: 'Patna', country: 'India' },
  { city: 'Dhaka', country: 'Bangladesh' },
  { city: 'Chittagong', country: 'Bangladesh' },
  { city: 'Khulna', country: 'Bangladesh' },
  { city: 'Rajshahi', country: 'Bangladesh' },
  { city: 'Sylhet', country: 'Bangladesh' },
  { city: 'Kathmandu', country: 'Nepal' },
  { city: 'Pokhara', country: 'Nepal' },
  { city: 'Lalitpur', country: 'Nepal' },
  { city: 'Chicago', country: 'United States' },
  { city: 'New York', country: 'United States' },
  { city: 'Houston', country: 'United States' },
  { city: 'Los Angeles', country: 'United States' },
]

export const CURRENCIES = ['PKR', 'INR', 'USD', 'BDT', 'NPR'] as const

export function filterSuggestions(query: string, options: string[]): string[] {
  const needle = query.trim().toLowerCase()
  if (!needle) return options.slice(0, 8)
  const starts = options.filter((item) => item.toLowerCase().startsWith(needle))
  const contains = options.filter(
    (item) => !item.toLowerCase().startsWith(needle) && item.toLowerCase().includes(needle),
  )
  return [...starts, ...contains].slice(0, 8)
}

export function citySuggestionOptions(
  query: string,
  country: string,
): { city: string; country: string }[] {
  const wantedCountry = country.trim().toLowerCase()
  const pool = CITY_SUGGESTIONS.filter((item) =>
    wantedCountry ? item.country.toLowerCase() === wantedCountry : true,
  )
  const ranked = filterSuggestions(query, [...new Set(pool.map((item) => item.city))])
  return ranked.flatMap((city) => pool.filter((item) => item.city === city)).slice(0, 8)
}

export const DEFAULT_SETTINGS: PickerSettings = {
  language: 'auto',
  city: '',
  country: '',
  currency: '',
  neighborhood: '',
}

export function currencyForCountry(country: string): string {
  const key = country.trim().toLowerCase().replace(/\./g, '')
  if (key === 'pakistan') return 'PKR'
  if (key === 'india' || key === 'bharat' || key === 'hindustan') return 'INR'
  if (key === 'bangladesh') return 'BDT'
  if (key === 'nepal') return 'NPR'
  if (
    key === 'united states' ||
    key === 'united states of america' ||
    key === 'usa' ||
    key === 'us' ||
    key === 'america'
  ) {
    return 'USD'
  }
  return ''
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
          const country = typeof parsed.country === 'string' ? parsed.country : ''
          const storedCurrency = typeof parsed.currency === 'string' ? parsed.currency : ''
          return {
            language: LANGUAGES.some((item) => item.id === parsed.language)
              ? (parsed.language as AppLanguage)
              : 'auto',
            city: typeof parsed.city === 'string' ? parsed.city : '',
            country,
            currency: storedCurrency || currencyForCountry(country),
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
