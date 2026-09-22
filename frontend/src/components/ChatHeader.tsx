interface Props {
  darkMode: boolean
  connectionStatus: 'checking' | 'connected' | 'offline'
  hasMessages: boolean
  onClearConversation: () => void
  onToggleTheme: () => void
}

function ThemeIcon({ darkMode }: { darkMode: boolean }) {
  if (darkMode) {
    return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>
  }
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M20.5 15.3A8.5 8.5 0 0 1 8.7 3.5 8.5 8.5 0 1 0 20.5 15.3Z" /></svg>
}

function ClearIcon() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 14h10l1-14M9 7V4h6v3" /></svg>
}

export function ChatHeader({ darkMode, connectionStatus, hasMessages, onClearConversation, onToggleTheme }: Props) {
  const statusLabel = connectionStatus === 'connected'
    ? 'Connected to local market data'
    : connectionStatus === 'offline'
      ? 'Offline — reconnect to send'
      : 'Checking connection…'
  return (
    <header className="border-b border-[#d9d5ca] bg-[#fbfaf6]">
      <div className="mx-auto flex w-full max-w-5xl items-center justify-between px-4 py-3.5 sm:px-7 lg:px-10">
        <div className="flex items-center gap-3">
          <div className="brand-mark" aria-hidden="true"><span>SW</span></div>
          <div>
            <h1 className="text-[17px] font-bold tracking-[-0.02em] text-[#162235]">Scrapwisest</h1>
            <p className="text-[11px] font-medium tracking-wide text-[#71806f]">FAIR RATES. CLEAR DEALS.</p>
          </div>
        </div>
        <div className="flex items-center gap-2 sm:gap-4">
          <div className={`connection-status connection-${connectionStatus} hidden items-center gap-2 text-[11px] font-semibold sm:flex`}>
          <span className="status-dot" />
          <span>{statusLabel}</span>
          </div>
          <button
            type="button"
            onClick={onToggleTheme}
            className="theme-toggle"
            aria-label={darkMode ? 'Switch to light mode' : 'Switch to dark mode'}
            title={darkMode ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            <ThemeIcon darkMode={darkMode} />
          </button>
          <button
            type="button"
            onClick={onClearConversation}
            disabled={!hasMessages}
            className="theme-toggle"
            aria-label="Clear conversation on this device"
            title="Clear conversation on this device"
          >
            <ClearIcon />
          </button>
        </div>
      </div>
    </header>
  )
}
