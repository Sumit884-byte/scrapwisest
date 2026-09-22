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
    <div className="flex justify-start">
      <div className="flex items-center gap-1.5 rounded-2xl rounded-tl-md border border-slate-200 bg-white px-4 py-3 shadow-sm">
        <span className="h-2 w-2 animate-bounce rounded-full bg-slate-300 [animation-delay:0ms]" />
        <span className="h-2 w-2 animate-bounce rounded-full bg-slate-300 [animation-delay:150ms]" />
        <span className="h-2 w-2 animate-bounce rounded-full bg-slate-300 [animation-delay:300ms]" />
      </div>
    </div>
  )
}

export function MessageList({ messages, isSending, onRetry, onQuickAction, onFollowUp }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, isSending])

  return (
    <div className="flex-1 overflow-y-auto px-3 py-4 sm:px-6 lg:px-8">
      {messages.length === 0 ? (
        <div className="mx-auto flex h-full w-full max-w-3xl flex-col justify-center gap-7 px-1 sm:gap-8">
          <div className="grid gap-6 sm:grid-cols-[1fr_auto] sm:items-end">
            <div className="max-w-xl space-y-3">
              <p className="eyebrow">A better number before the deal</p>
              <h2 className="hero-title">Know the rate.<br /><span>Keep your share.</span></h2>
              <p className="hero-copy max-w-md text-[14px] leading-relaxed text-[#687364] sm:text-[15px]">
                Check a local scrap price or log what you sold. Speak naturally in English, Urdu, Roman Urdu, Hindi, Hinglish, or Telugu.
              </p>
            </div>
            <div className="start-card hidden rounded-2xl border border-[#d8d8c8] bg-[#f7f5ed] px-4 py-3 text-left sm:block">
              <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-[#8b6b3e]">Start here</p>
              <p className="mt-1 text-[13px] font-semibold text-[#263324]">Ask for a rate</p>
              <p className="text-[12px] text-[#788071]">before you negotiate</p>
            </div>
          </div>
          <div>
            <div className="mb-2.5 flex items-center justify-between">
              <p className="section-label">Quick checks</p>
              <p className="hidden text-[11px] text-[#8a9184] sm:block">Tap one or type your own</p>
            </div>
            <QuickActions onPick={onQuickAction} disabled={isSending} />
          </div>
        </div>
      ) : (
        <div className="mx-auto flex w-full max-w-2xl flex-col gap-3 lg:max-w-3xl">
          {messages.map((message) => (
            <MessageBubble key={message.id} message={message} onRetry={onRetry} onFollowUp={onFollowUp} />
          ))}
          {isSending && <TypingIndicator />}
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  )
}
