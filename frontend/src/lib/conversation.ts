import type { ChatMessage } from './types'

const STORAGE_KEY = 'scrapwisest.conversation'

/**
 * Persist only serializable transcript data. Uploaded File objects and object
 * URLs are intentionally omitted; they are temporary request/preview data.
 */
function serializableMessage(message: ChatMessage): ChatMessage {
  const { image: _image, ...rest } = message
  return rest
}

export function readConversation(): ChatMessage[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter((item): item is ChatMessage => {
      if (!item || typeof item !== 'object') return false
      const value = item as Partial<ChatMessage>
      return (
        typeof value.id === 'string' &&
        (value.role === 'user' || value.role === 'assistant') &&
        typeof value.text === 'string' &&
        typeof value.timestamp === 'number' &&
        (value.status === 'sending' || value.status === 'sent' || value.status === 'error')
      )
    })
  } catch {
    return []
  }
}

export function writeConversation(messages: ChatMessage[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(messages.map(serializableMessage)))
  } catch {
    // Private mode, storage quota, or disabled storage should not break chat.
  }
}

export function clearConversation(): void {
  try {
    localStorage.removeItem(STORAGE_KEY)
  } catch {
    // Ignore unavailable storage.
  }
}
