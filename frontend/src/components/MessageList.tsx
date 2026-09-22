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
    <div className="flex min-h-full flex-col justify-center px-1 py-8">
      <div className="w-full">
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_220px] lg:items-start">
          <div>
            <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-[#A0522D] dark-label">
              A better number before the deal
            </p>
            <h1 className="mt-3 text-[34px] font-extrabold leading-[1.06] tracking-[-0.03em] sm:text-[44px] lg:text-[52px]">
              <span className="text-[var(--color-text)]">Know the rate.</span>
              <br />
              <span className="hero-highlight text-[#5E8C3A]">Keep your share.</span>
            </h1>
            <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-[var(--color-text-muted)]">
              Check a local scrap price or log what you sold. Speak naturally in English, Urdu,
              Roman Urdu, Hindi, Hinglish, or Telugu.
            </p>
          </div>

          <div className="start-here-card rounded-2xl px-5 py-4 shadow-[var(--shadow-sm)] lg:mt-11 lg:w-[220px]">
            <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-[#A0522D] dark-label">
              Start here
            </p>
            <p className="mt-1.5 text-[16px] font-bold leading-snug text-[var(--color-text)]">
              Ask for a rate
            </p>
            <p className="text-[13px] text-[var(--color-text-muted)]">before you negotiate</p>
          </div>
        </div>

        <div className="mt-9">
          <div className="mb-3 flex items-baseline justify-between gap-3">
            <h2 className="text-[11px] font-bold uppercase tracking-[0.16em] text-[#A0522D] dark-label">
              Quick checks
            </h2>
            <span className="text-[12px] text-[var(--color-text-muted)]">
              Tap one or type your own
            </span>
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
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-[720px] px-4 sm:px-6 lg:px-8">
          <EmptyState onPick={onQuickAction} disabled={isSending} />
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto px-3 py-4 sm:px-6 lg:px-8">
      <div className="mx-auto flex w-full max-w-[720px] flex-col gap-3.5">
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} onRetry={onRetry} onFollowUp={onFollowUp} />
        ))}
        {isSending && <TypingIndicator />}
      </div>
      <div ref={bottomRef} />
    </div>
  )
}