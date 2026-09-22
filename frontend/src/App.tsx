import { useCallback, useMemo, useState } from 'react'
import { postChat } from './lib/api'
import { getOrCreatePickerId, uuid } from './lib/picker'
import { placeLabel, speechLocale } from './lib/settings'
import type { ChatMessage } from './lib/types'
import { ChatHeader } from './components/ChatHeader'
import { MessageList } from './components/MessageList'
import { Composer } from './components/Composer'
import { SettingsPanel } from './components/SettingsPanel'
import { useRegion } from './lib/useRegion'
import { useSettings } from './lib/useSettings'

export default function App() {
  // Resolved once for this device — never regenerated. Drives conversation
  // continuity and the agent's long-term memory on the backend.
  const pickerId = useMemo(() => getOrCreatePickerId(), [])
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isSending, setIsSending] = useState(false)
  const { region, status: regionStatus, request: requestRegion } = useRegion()
  const { settings, update: updateSettings } = useSettings()
  const [settingsOpen, setSettingsOpen] = useState(false)

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
        const res = await postChat({
          text,
          image,
          pickerId,
          region: region?.id,
          language: settings.language,
          city: settings.city,
          country: settings.country,
        })
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
    [isSending, pickerId, region?.id, settings],
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
          region: region?.id,
          language: settings.language,
          city: settings.city,
          country: settings.country,
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
    [isSending, pickerId, region?.id, settings],
  )

  const handleQuickAction = useCallback(
    (text: string) => {
      void handleSend(text, null)
    },
    [handleSend],
  )

  return (
    <div className="flex h-dvh flex-col bg-slate-100">
      <ChatHeader
        regionLabel={region?.label ?? null}
        regionStatus={regionStatus}
        onRequestRegion={() => {
          void requestRegion()
        }}
        placeLabel={placeLabel(settings) || null}
        onOpenSettings={() => setSettingsOpen(true)}
      />
      <MessageList
        messages={messages}
        isSending={isSending}
        onRetry={handleRetry}
        onQuickAction={handleQuickAction}
        onFollowUp={(text) => void handleSend(text, null)}
      />
      <Composer
        disabled={isSending}
        onSend={handleSend}
        speechLocale={speechLocale(settings.language)}
      />
      <SettingsPanel
        open={settingsOpen}
        settings={settings}
        onChange={updateSettings}
        onClose={() => setSettingsOpen(false)}
      />
    </div>
  )
}
