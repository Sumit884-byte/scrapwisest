import { useCallback, useEffect, useMemo, useState } from 'react'
import { postChat } from './lib/api'
import { getOrCreatePickerId, uuid } from './lib/picker'
import type { ChatMessage } from './lib/types'
import { ChatHeader } from './components/ChatHeader'
import { MessageList } from './components/MessageList'
import { Composer } from './components/Composer'

export default function App() {
  // Resolved once for this device — never regenerated. Drives conversation
  // continuity and the agent's long-term memory on the backend.
  const pickerId = useMemo(() => getOrCreatePickerId(), [])
  const [darkMode, setDarkMode] = useState(() => {
    try {
      return localStorage.getItem('scrapsense_theme') === 'dark'
    } catch {
      return false
    }
  })
  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    try {
      const saved = localStorage.getItem(`scrapsense_messages_${pickerId}`)
      if (!saved) return []
      const parsed = JSON.parse(saved) as ChatMessage[]
      return Array.isArray(parsed)
        ? parsed.filter((message) => message && (message.role === 'user' || message.role === 'assistant'))
        : []
    } catch {
      return []
    }
  })
  const [isSending, setIsSending] = useState(false)
  const [connectionStatus, setConnectionStatus] = useState<'checking' | 'connected' | 'offline'>('checking')

  useEffect(() => {
    try {
      localStorage.setItem('scrapsense_theme', darkMode ? 'dark' : 'light')
    } catch {
      // Theme preference is optional when browser storage is unavailable.
    }
  }, [darkMode])

  useEffect(() => {
    try {
      // Uploaded File objects and object URLs are intentionally omitted. Only
      // the readable conversation transcript is restored on this device.
      const safeMessages = messages.map(({ image: _image, ...message }) => message)
      localStorage.setItem(`scrapsense_messages_${pickerId}`, JSON.stringify(safeMessages))
    } catch {
      // Conversation persistence is optional when browser storage is unavailable.
    }
  }, [messages, pickerId])

  useEffect(() => {
    let cancelled = false
    let timer: number | undefined

    const checkBackend = async () => {
      if (!navigator.onLine) {
        setConnectionStatus('offline')
        return
      }

      try {
        const controller = new AbortController()
        const timeout = window.setTimeout(() => controller.abort(), 5000)
        const response = await fetch('/health', { signal: controller.signal })
        window.clearTimeout(timeout)
        if (!cancelled) setConnectionStatus(response.ok ? 'connected' : 'offline')
      } catch {
        if (!cancelled) setConnectionStatus('offline')
      }
    }

    const handleOnline = () => void checkBackend()
    const handleOffline = () => setConnectionStatus('offline')
    void checkBackend()
    timer = window.setInterval(() => void checkBackend(), 30000)
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)

    return () => {
      cancelled = true
      if (timer) window.clearInterval(timer)
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [])

  /** Send a user message (with optional photo) and append the assistant reply. */
  const handleSend = useCallback(
    async (text: string, image: File | null) => {
      if (isSending) return
      setIsSending(true)

      const id = uuid()
      const userMessage: ChatMessage = {
        id,
        role: 'user',
        text,
        image: image ? { file: image, previewUrl: URL.createObjectURL(image) } : undefined,
        timestamp: Date.now(),
        status: 'sending',
      }
      setMessages((prev) => [...prev, userMessage])

      try {
        const res = await postChat({ text, image, pickerId })
        setMessages((prev) => [
          ...prev.map((m) => (m.id === id ? { ...m, status: 'sent' as const } : m)),
          {
            id: uuid(),
            role: 'assistant',
            text: res.reply,
            priceData: res.price_data ?? undefined,
            reportData: res.report_data ?? undefined,
            timestamp: Date.now(),
            status: 'sent',
          },
        ])
      } catch (err) {
        const error = err instanceof Error ? err.message : 'Not sent'
        setMessages((prev) =>
          prev.map((m) => (m.id === id ? { ...m, status: 'error' as const, error } : m)),
        )
      } finally {
        setIsSending(false)
      }
    },
    [isSending, pickerId],
  )

  /** Resend a failed user message with the same text + photo it carried. */
  const handleRetry = useCallback(
    async (message: ChatMessage) => {
      if (isSending) return
      setIsSending(true)
      setMessages((prev) =>
        prev.map((m) => (m.id === message.id ? { ...m, status: 'sending' as const } : m)),
      )

      try {
        const res = await postChat({
          text: message.text,
          image: message.image?.file ?? null,
          pickerId,
        })
        setMessages((prev) => [
          ...prev.map((m) => (m.id === message.id ? { ...m, status: 'sent' as const } : m)),
          {
            id: uuid(),
            role: 'assistant',
            text: res.reply,
            priceData: res.price_data ?? undefined,
            reportData: res.report_data ?? undefined,
            timestamp: Date.now(),
            status: 'sent',
          },
        ])
      } catch (err) {
        const error = err instanceof Error ? err.message : 'Not sent'
        setMessages((prev) =>
          prev.map((m) => (m.id === message.id ? { ...m, status: 'error' as const, error } : m)),
        )
      } finally {
        setIsSending(false)
      }
    },
    [isSending, pickerId],
  )

  const handleQuickAction = useCallback(
    (text: string) => {
      void handleSend(text, null)
    },
    [handleSend],
  )

  const handleClearConversation = useCallback(() => {
    if (messages.length > 0 && !window.confirm('Clear this device\'s conversation?')) return
    setMessages([])
    try {
      localStorage.removeItem(`scrapsense_messages_${pickerId}`)
    } catch {
      // Local storage is optional.
    }
  }, [messages.length, pickerId])

  return (
    <div className={`app-shell flex h-dvh flex-col bg-slate-100 ${darkMode ? 'theme-dark' : ''}`}>
      <ChatHeader
        darkMode={darkMode}
        connectionStatus={connectionStatus}
        hasMessages={messages.length > 0}
        onClearConversation={handleClearConversation}
        onToggleTheme={() => setDarkMode((value) => !value)}
      />
      <MessageList
        messages={messages}
        isSending={isSending}
        onRetry={handleRetry}
        onQuickAction={handleQuickAction}
        onFollowUp={(text) => void handleSend(text, null)}
      />
      <Composer disabled={isSending} onSend={handleSend} />
    </div>
  )
}
