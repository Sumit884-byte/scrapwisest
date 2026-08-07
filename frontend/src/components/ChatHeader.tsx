export type BackendStatus = 'checking' | 'online' | 'offline'

interface Props {
  backendStatus: BackendStatus
}

const DOT_STYLES: Record<BackendStatus, string> = {
  checking: 'animate-pulse bg-slate-300',
  online: 'bg-emerald-500',
  offline: 'bg-red-500',
}

const STATUS_LABELS: Record<BackendStatus, string> = {
  checking: 'Connecting…',
  online: 'Online',
  offline: 'Offline',
}

export function ChatHeader({ backendStatus }: Props) {
  return (
    <header className="border-b border-slate-200 bg-white/85 backdrop-blur">
      <div className="mx-auto flex max-w-2xl items-center justify-between px-4 py-3">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-800 text-base" aria-hidden="true">
            ♻️
          </div>
          <div>
            <h1 className="text-base font-semibold leading-tight text-slate-900">ScrapSense</h1>
            <p className="text-[11px] leading-tight text-slate-500">
              Scrap prices, made fair · ری سائیکلنگ کی قیمتیں
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1.5" title={`Backend ${backendStatus}`}>
          <span className={`h-2 w-2 rounded-full ${DOT_STYLES[backendStatus]}`} />
          <span className="text-[11px] font-medium text-slate-500">{STATUS_LABELS[backendStatus]}</span>
        </div>
      </div>
    </header>
  )
}
