import type { RegionStatus } from '../lib/useRegion'

interface Props {
  regionLabel: string | null
  regionStatus: RegionStatus
  onRequestRegion: () => void
  placeLabel: string | null
  onOpenSettings: () => void
  darkMode: boolean
  onToggleDarkMode: () => void
  canClearConversation: boolean
  onClearConversation: () => void
}

export function ChatHeader({
  regionLabel,
  regionStatus,
  onRequestRegion,
  placeLabel,
  onOpenSettings,
  darkMode,
  onToggleDarkMode,
  canClearConversation,
  onClearConversation,
}: Props) {
  return (
    <header className="border-b border-[#d9d5ca] bg-[#fbfaf6]">
      <div className="mx-auto flex w-full max-w-5xl items-center justify-between gap-3 px-4 py-3.5 sm:px-7 lg:px-10">
        <div className="flex min-w-0 items-center gap-3">
          <div className="brand-mark" aria-hidden="true"><span>SW</span></div>
          <div className="min-w-0">
            <h1 className="text-[17px] font-bold tracking-[-0.02em] text-[#162235]">Scrapwisest</h1>
            <p className="text-[11px] font-medium tracking-wide text-[#71806f]">FAIR RATES. CLEAR DEALS.</p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={onToggleDarkMode}
            className="theme-toggle"
            aria-label={darkMode ? 'Switch to light mode' : 'Switch to dark mode'}
            title={darkMode ? 'Light mode' : 'Dark mode'}
          >
            {darkMode ? (
              <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.65 17.65l1.42 1.42M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.65 6.35l1.42-1.42" /></svg>
            ) : (
              <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M20.5 15.2A8.5 8.5 0 0 1 8.8 3.5 8.5 8.5 0 1 0 20.5 15.2Z" /></svg>
            )}
          </button>
          {canClearConversation && (
            <button
              type="button"
              onClick={onClearConversation}
              className="hidden rounded-full border border-[#d8d8c8] bg-white px-2.5 py-1 text-[11px] font-semibold text-[#65705f] hover:bg-[#f7f5ed] sm:inline"
            >
              Clear chat
            </button>
          )}
          <button
            type="button"
            onClick={onOpenSettings}
            className="rounded-full border border-[#d8d8c8] bg-white px-2.5 py-1 text-[11px] font-semibold text-[#65705f] hover:bg-[#f7f5ed]"
          >
            {placeLabel ? placeLabel : 'Language · City'}
          </button>
          {regionStatus === 'ready' && regionLabel ? (
            <p className="hidden text-right text-[11px] font-semibold text-[#65705f] sm:block">
              Nearby · {regionLabel}
            </p>
          ) : regionStatus !== 'denied' ? (
            <button
              type="button"
              onClick={onRequestRegion}
              disabled={regionStatus === 'asking'}
              className="hidden shrink-0 rounded-full border border-[#d8d8c8] bg-white px-2.5 py-1 text-[11px] font-semibold text-[#65705f] hover:bg-[#f7f5ed] disabled:opacity-50 sm:inline"
            >
              {regionStatus === 'asking' ? 'Locating…' : 'Faster nearby'}
            </button>
          ) : null}
        </div>
      </div>
    </header>
  )
}
