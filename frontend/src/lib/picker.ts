/**
 * Stable per-picker identity.
 *
 * The backend requires `picker_id` on every /chat request. It drives both
 * conversation continuity (checkpointer keyed by thread) and long-term
 * memory (namespaced per picker), so it must be generated once and reused
 * forever — never regenerated per session or per message.
 */

const STORAGE_KEY = 'scrapsense_picker_id'

export function uuid(): string {
  const c = globalThis.crypto
  if (c && typeof c.randomUUID === 'function') return c.randomUUID()
  // Non-secure context (plain HTTP, not localhost) or older browser:
  // randomUUID isn't available — fall back to a time+random id.
  return `${Date.now()}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`
}

export function getOrCreatePickerId(): string {
  try {
    const existing = localStorage.getItem(STORAGE_KEY)
    if (existing) return existing

    const fresh = uuid()
    localStorage.setItem(STORAGE_KEY, fresh)
    return fresh
  } catch {
    // Storage unavailable (private mode / sandboxed iframe): fall back to an
    // in-memory id for this session. Memory won't persist across sessions,
    // but chat still works.
    return uuid()
  }
}
