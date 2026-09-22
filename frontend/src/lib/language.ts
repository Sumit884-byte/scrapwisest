import { preferredSpeechCode, readSettings } from './settings'

const STORAGE_KEY = 'scrapwisest_spoken_lang'

export function setDetectedLang(lang: string): void {
  const code = lang.trim().toLowerCase().slice(0, 2) || 'en'
  try {
    sessionStorage.setItem(STORAGE_KEY, code)
  } catch {
    // Private mode or blocked storage — in-memory only this session.
  }
}

export function getDetectedLang(): string | undefined {
  const preferred = preferredSpeechCode(readSettings())
  if (preferred) return preferred
  try {
    return sessionStorage.getItem(STORAGE_KEY) ?? undefined
  } catch {
    return undefined
  }
}
