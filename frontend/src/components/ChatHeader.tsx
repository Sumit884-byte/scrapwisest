import type { RegionStatus } from '../lib/useRegion'
import { Sun, Moon, Trash2, Settings, MapPin, Zap } from 'lucide-react'

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
    <header className="border-b border-[var(--color-border)] bg-[var(--color-surface)] sticky top-0 z-10">
      <div className="mx-auto flex w-full max-w-[1200px] items-center justify-between gap-3 px-4 py-3.5 sm:px-6 lg:px-8">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--color-primary)] text-[var(--color-accent)] font-bold text-[13px] tracking-tight shadow-[var(--shadow-sm)] ring-1 ring-inset ring-white/10" aria-hidden="true">
            SW
          </div>
          <div className="min-w-0">
            <h1 className="truncate text-[17px] font-bold tracking-[-0.02em] text-[var(--color-text)]">Scrapwisest</h1>
            <p className="truncate text-[10px] font-semibold tracking-[0.12em] uppercase text-[var(--color-text-muted)]">FAIR RATES. CLEAR DEALS.</p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <button
            type="button"
            onClick={onToggleDarkMode}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-bg)]"
            aria-label={darkMode ? 'Switch to light mode' : 'Switch to dark mode'}
            title={darkMode ? 'Light mode' : 'Dark mode'}
          >
            {darkMode ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
          </button>
          {canClearConversation && (
            <button
              type="button"
              onClick={onClearConversation}
              className="flex h-9 shrink-0 items-center gap-1.5 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-[11px] font-semibold text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-bg)] hidden sm:flex"
            >
              <Trash2 className="h-4 w-4" />
              Clear chat
            </button>
          )}
          <button
            type="button"
            onClick={onOpenSettings}
            className="flex h-9 max-w-[140px] shrink-0 items-center gap-1.5 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-[11px] font-semibold text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-bg)]"
          >
            <Settings className="h-4 w-4 shrink-0" />
            <span className="truncate">{placeLabel ? placeLabel : 'Language · City'}</span>
          </button>
          {regionStatus === 'ready' && regionLabel ? (
            <div className="hidden items-center gap-1.5 rounded-xl bg-[var(--color-accent-soft)] px-3 py-1.5 text-[11px] font-semibold text-[var(--color-accent-dark)] sm:flex">
              <MapPin className="h-3.5 w-3.5" />
              Nearby · {regionLabel}
            </div>
          ) : regionStatus !== 'denied' ? (
            <button
              type="button"
              onClick={onRequestRegion}
              disabled={regionStatus === 'asking'}
              className="flex h-9 shrink-0 items-center gap-1.5 rounded-xl border border-[var(--color-accent)] bg-[var(--color-accent-soft)] px-3 py-1.5 text-[11px] font-semibold text-[var(--color-accent-dark)] transition-colors hover:bg-[var(--color-accent)] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-bg)] disabled:opacity-50 disabled:cursor-not-allowed hidden sm:flex"
            >
              <Zap className="h-3.5 w-3.5" />
              {regionStatus === 'asking' ? 'Locating…' : 'Faster nearby'}
            </button>
          ) : null}
        </div>
      </div>
    </header>
  )
}