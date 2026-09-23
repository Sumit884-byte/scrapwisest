import type { RegionStatus } from '../lib/useRegion'
import { Sun, Moon, Trash2, Settings, MapPin, Leaf } from 'lucide-react'

interface Props {
  regionLabel: string | null
  regionStatus: RegionStatus
  onRequestRegion: () => void
  placeLabel: string | null
  currency?: string | null
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
  currency,
  onOpenSettings,
  darkMode,
  onToggleDarkMode,
  canClearConversation,
  onClearConversation,
}: Props) {
  const market = [placeLabel, currency].filter(Boolean).join(' · ')

  return (
    <header className="sticky top-0 z-10 border-b border-[var(--color-border)] bg-[var(--color-bg)] shadow-[var(--shadow-sm)]">
      <div className="mx-auto flex w-full max-w-[880px] items-center justify-between gap-3 px-4 py-3 sm:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <div
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--color-accent-soft)] text-[var(--color-accent)]"
            aria-hidden="true"
          >
            <Leaf className="h-5 w-5" strokeWidth={2.2} />
          </div>
          <div className="min-w-0">
            <h1 className="truncate text-[18px] font-bold tracking-tight text-[var(--color-accent-dark)]">
              Scrapwisest
            </h1>
            <p className="flex items-center gap-1.5 truncate text-[11px] font-semibold text-[var(--color-text-muted)]">
              <span className="inline-block h-2 w-2 shrink-0 rounded-full bg-[var(--color-accent)]" />
              {market || 'Fair rates. Clear deals.'}
            </p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <button
            type="button"
            onClick={onToggleDarkMode}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-copper)]"
            aria-label={darkMode ? 'Switch to light mode' : 'Switch to dark mode'}
            title={darkMode ? 'Light mode' : 'Dark mode'}
          >
            {darkMode ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
          </button>
          {canClearConversation && (
            <button
              type="button"
              onClick={onClearConversation}
              className="hidden h-10 shrink-0 items-center gap-1.5 rounded-xl px-3 text-[11px] font-semibold text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text)] sm:flex"
            >
              <Trash2 className="h-4 w-4" />
              Clear
            </button>
          )}
          <button
            type="button"
            onClick={onOpenSettings}
            className="flex h-10 max-w-[160px] shrink-0 items-center gap-1.5 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3 text-[11px] font-bold text-[var(--color-text)] shadow-[var(--shadow-sm)]"
          >
            <Settings className="h-4 w-4 shrink-0 text-[var(--color-copper)]" />
            <span className="truncate">{placeLabel ? placeLabel : 'Place · Language'}</span>
          </button>
          {regionStatus === 'ready' && regionLabel ? (
            <div className="hidden items-center gap-1.5 rounded-xl bg-[var(--color-accent-soft)] px-3 py-2 text-[11px] font-semibold text-[var(--color-accent-dark)] sm:flex">
              <MapPin className="h-3.5 w-3.5" />
              {regionLabel}
            </div>
          ) : regionStatus !== 'denied' ? (
            <button
              type="button"
              onClick={onRequestRegion}
              disabled={regionStatus === 'asking'}
              className="hidden h-10 shrink-0 items-center gap-1.5 rounded-xl bg-[var(--color-accent-soft)] px-3 text-[11px] font-semibold text-[var(--color-accent-dark)] disabled:opacity-50 sm:flex"
            >
              {regionStatus === 'asking' ? 'Locating…' : 'Nearby'}
            </button>
          ) : null}
        </div>
      </div>
    </header>
  )
}
