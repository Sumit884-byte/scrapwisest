import type { ChatMessage } from '../lib/types'

interface Props {
  message: ChatMessage
  onRetry: (message: ChatMessage) => void
}

/** One chat bubble. User messages are dark and right-aligned; assistant
 *  replies are white cards on the left. A failed user message shows a small
 *  "Not sent / Retry" affordance. */
export function MessageBubble({ message, onRetry }: Props) {
  const isUser = message.role === 'user'
  const time = new Date(message.timestamp).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  })

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-tr-md bg-slate-800 px-3.5 py-2.5 text-slate-50 shadow-sm">
          {message.image && (
            <img
              src={message.image.previewUrl}
              alt="Attached photo"
              className="mb-2 max-h-44 w-auto rounded-lg object-cover"
            />
          )}
          {message.text && (
            <p className="whitespace-pre-wrap break-words text-[15px] leading-snug">{message.text}</p>
          )}
          <p className="mt-1 text-right text-[10px] text-slate-400">{time}</p>
          {message.status === 'error' && (
            <div className="mt-1.5 flex items-center justify-end gap-2">
              <span className="text-[11px] font-medium text-red-300">Not sent</span>
              <button
                type="button"
                onClick={() => onRetry(message)}
                className="rounded-md bg-slate-600 px-2.5 py-1 text-[11px] font-semibold text-white transition hover:bg-slate-500"
              >
                Retry
              </button>
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] rounded-2xl rounded-tl-md border border-slate-200 bg-white px-3.5 py-2.5 text-slate-800 shadow-sm">
        <p className="whitespace-pre-wrap break-words text-[15px] leading-snug">{message.text}</p>
        <p className="mt-1 text-[10px] text-slate-400">{time}</p>
      </div>
    </div>
  )
}
