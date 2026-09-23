import { useEffect, useRef } from 'react'
import type { ChatMessage } from '../lib/types'
import { MessageBubble } from './MessageBubble'
import { QuickActions } from './QuickActions'

interface Props {
  messages: ChatMessage[]
  isSending: boolean
  onRetry: (message: ChatMessage) => void
  onQuickAction: (text: string) => void
  onFollowUp: (text: string) => void
}

function TypingIndicator() {
  return (
    <div className="flex justify-start message-enter">
      <div className="flex items-center gap-1.5 rounded-[18px] rounded-tl-[6px] border border-[var(--color-card-border)] bg-[var(--color-surface)] px-4 py-3 shadow-[var(--shadow-sm)]">
        <span className="h-2 w-2 animate-bounce rounded-full bg-[var(--color-accent)] [animation-delay:0ms]" />
        <span className="h-2 w-2 animate-bounce rounded-full bg-[var(--color-accent)] [animation-delay:150ms]" />
        <span className="h-2 w-2 animate-bounce rounded-full bg-[var(--color-accent)] [animation-delay:300ms]" />
      </div>
    </div>
  )
}

function EmptyState({ onPick, disabled }: { onPick: (text: string) => void; disabled: boolean }) {
  return (
    <div className="flex min-h-full flex-col justify-center px-1 py-6">
      <div className="w-full">
        <p className="inline-flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1 text-[11px] font-semibold text-[var(--color-text-muted)] shadow-[var(--shadow-sm)]">
          Hindi, Urdu, Telugu & voice ready
        </p>
        <h1 className="mt-4 text-[32px] font-bold leading-[1.08] tracking-tight sm:text-[42px]">
          <span className="text-[var(--color-accent-dark)]">Know the rate.</span>
          <br />
          <span className="hero-highlight">Keep your share.</span>
        </h1>
        <p className="mt-3 max-w-xl text-[15px] leading-relaxed text-[var(--color-text-muted)]">
          Check a local scrap price or log what you sold. Speak in your language or tap below.
        </p>

        <div className="mt-7">
          <div className="mb-3 flex items-baseline justify-between gap-3">
            <h2 className="text-[11px] font-bold uppercase tracking-[0.14em] text-[var(--color-copper)]">
              Tap to ask
            </h2>
            <span className="text-[12px] text-[var(--color-text-muted)]">or type your own</span>
          </div>
          <QuickActions onPick={onPick} disabled={disabled} />
        </div>
      </div>
    </div>
  )
}

export function MessageList({ messages, isSending, onRetry, onQuickAction, onFollowUp }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, isSending])

  if (messages.length === 0) {
    return (
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-[720px] px-4 sm:px-6">
          <EmptyState onPick={onQuickAction} disabled={isSending} />
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto flex w-full max-w-[720px] flex-col gap-3.5 px-4 py-4 sm:px-6">
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} onRetry={onRetry} onFollowUp={onFollowUp} />
        ))}
        {isSending && <TypingIndicator />}
      </div>
      <div ref={bottomRef} />
    </div>
  )
}