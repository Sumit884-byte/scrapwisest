import { useEffect, useRef } from 'react'
import type { ChatMessage } from '../lib/types'
import { MessageBubble } from './MessageBubble'
import { Sparkles } from 'lucide-react'

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
  const suggestions = [
    "What's the PET rate?",
    'I sold 5kg copper',
    'Find rates near me',
    'Log a sale',
  ]

  return (
    <div className="flex h-full flex-col items-center justify-center px-4 py-8">
      <div className="w-full max-w-md text-center">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-[var(--color-primary)] text-[var(--color-accent)] font-bold text-xl shadow-[var(--shadow-lg)] mb-5">
          SW
        </div>
        <h2 className="text-[26px] font-bold tracking-tight text-[var(--color-text)]">Scrapwisest</h2>
        <p className="mt-1.5 text-[14px] font-medium text-[var(--color-text-muted)]">Know the rate. Make the deal.</p>
        <p className="mt-5 text-[15px] leading-relaxed text-[var(--color-text-muted)]">
          Ask about a scrap price, or tell me what you sold.
        </p>

        <div className="mt-7">
          <p className="flex items-center justify-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--color-text-muted)] mb-3">
            <Sparkles className="h-3.5 w-3.5 text-[var(--color-accent)]" />
            Try asking
          </p>
          <div className="flex flex-col gap-2">
            {suggestions.map((text) => (
              <button
                key={text}
                type="button"
                disabled={disabled}
                onClick={() => onPick(text)}
                className="group flex items-center justify-between rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3 text-left text-[14px] font-medium text-[var(--color-text)] shadow-[var(--shadow-sm)] transition-all hover:-translate-y-0.5 hover:border-[var(--color-accent)] hover:shadow-[var(--shadow-md)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-bg-chat)] disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:translate-y-0"
              >
                <span>{text}</span>
                <span className="text-[var(--color-text-muted)] transition-colors group-hover:text-[var(--color-accent)]">→</span>
              </button>
            ))}
          </div>
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