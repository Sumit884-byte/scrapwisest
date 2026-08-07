import { useCallback, useEffect, useMemo, useState } from 'react'
import { postChat, pingHealth } from './lib/api'
import { getOrCreatePickerId, uuid } from './lib/picker'
import type { ChatMessage } from './lib/types'
import { ChatHeader } from './components/ChatHeader'
import type { BackendStatus } from './components/ChatHeader'
import { MessageList } from './components/MessageList'
import { Composer } from './components/Composer'

export default function App() {
  // Resolved once for this device — never regenerated. Drives conversation
  // continuity and the agent's long-term memory on the backend.
  const pickerId = useMemo(() => getOrCreatePickerId(), [])
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isSending, setIsSending] = useState(false)
  const [backendStatus, setBackendStatus] = useState<BackendStatus>('checking')

  useEffect(() => {
    let cancelled = false
    void pingHealth().then((ok) => {
      if (!cancelled) setBackendStatus(ok ? 'online' : 'offline')
    })
    return () => {
      cancelled = true
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
          ...prev.map((m) => (m.id === id ? { ...m, status: 'sent' } : m)),
          {
            id: uuid(),
            role: 'assistant',
            text: res.reply,
            timestamp: Date.now(),
            status: 'sent',
          },
        ])
      } catch {
        setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, status: 'error' } : m)))
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
        prev.map((m) => (m.id === message.id ? { ...m, status: 'sending' } : m)),
      )

      try {
        const res = await postChat({
          text: message.text,
          image: message.image?.file ?? null,
          pickerId,
        })
        setMessages((prev) => [
          ...prev.map((m) => (m.id === message.id ? { ...m, status: 'sent' } : m)),
          {
            id: uuid(),
            role: 'assistant',
            text: res.reply,
            timestamp: Date.now(),
            status: 'sent',
          },
        ])
      } catch {
        setMessages((prev) =>
          prev.map((m) => (m.id === message.id ? { ...m, status: 'error' } : m)),
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

  return (
    <div className="flex h-dvh flex-col bg-slate-100">
      <ChatHeader backendStatus={backendStatus} />
      <MessageList
        messages={messages}
        isSending={isSending}
        onRetry={handleRetry}
        onQuickAction={handleQuickAction}
      />
      <Composer disabled={isSending} onSend={handleSend} />
    </div>
  )
}
