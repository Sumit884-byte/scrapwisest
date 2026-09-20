import { useEffect, useRef } from 'react'
import type { ChatMessage } from '../lib/types'
import { MessageBubble } from './MessageBubble'
import { QuickActions } from './QuickActions'

interface Props {
  messages: ChatMessage[]
  isSending: boolean
  onRetry: (message: ChatMessage) => void
  onQuickAction: (text: string) => void
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

export function MessageList({ messages, isSending, onRetry, onQuickAction }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, isSending])

  return (
    <div className="flex-1 overflow-y-auto px-3 py-4 sm:px-6 lg:px-8">
      {messages.length === 0 ? (
        <div className="mx-auto flex h-full w-full max-w-md flex-col items-center justify-center gap-5 text-center sm:max-w-2xl sm:gap-6 lg:max-w-4xl">
          <div className="max-w-lg space-y-2 px-2">
            <h2 className="text-lg font-semibold text-slate-800 sm:text-xl">Ask before you sell.</h2>
            <p className="text-sm leading-relaxed text-slate-500">
              Your scrap-price copilot. Check a rate or log a sale — in English, Hindi, or Hinglish.
            </p>
          </div>
          <QuickActions onPick={onQuickAction} disabled={isSending} />
        </div>
      ) : (
        <div className="mx-auto flex w-full max-w-2xl flex-col gap-3 lg:max-w-3xl">
          {messages.map((message) => (
            <MessageBubble key={message.id} message={message} onRetry={onRetry} />
          ))}
          {isSending && <TypingIndicator />}
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  )
}
