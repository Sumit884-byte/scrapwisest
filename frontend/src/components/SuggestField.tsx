import { useEffect, useId, useRef, useState } from 'react'

export interface SuggestOption {
  value: string
  label: string
  hint?: string
}

interface Props {
  value: string
  onChange: (value: string) => void
  onPick?: (option: SuggestOption) => void
  options: SuggestOption[]
  placeholder: string
  labelId?: string
}

export function SuggestField({ value, onChange, onPick, options, placeholder, labelId }: Props) {
  const listId = useId()
  const rootRef = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)

  useEffect(() => {
    setActive(0)
  }, [value, options.length])

  useEffect(() => {
    const onDoc = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  const choose = (option: SuggestOption) => {
    if (onPick) onPick(option)
    else onChange(option.value)
    setOpen(false)
  }

  return (
    <div ref={rootRef} className="relative mb-4">
      <input
        value={value}
        aria-labelledby={labelId}
        aria-autocomplete="list"
        aria-expanded={open && options.length > 0}
        aria-controls={listId}
        placeholder={placeholder}
        autoComplete="off"
        onFocus={() => setOpen(true)}
        onChange={(event) => {
          onChange(event.target.value)
          setOpen(true)
        }}
        onKeyDown={(event) => {
          if (!open || options.length === 0) return
          if (event.key === 'ArrowDown') {
            event.preventDefault()
            setActive((index) => (index + 1) % options.length)
          } else if (event.key === 'ArrowUp') {
            event.preventDefault()
            setActive((index) => (index - 1 + options.length) % options.length)
          } else if (event.key === 'Enter') {
            event.preventDefault()
            choose(options[active])
          } else if (event.key === 'Escape') {
            setOpen(false)
          }
        }}
        className="w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3.5 py-3 text-[15px] text-[var(--color-text)] placeholder:text-[var(--color-text-muted)] transition focus:border-[var(--color-accent)] focus:outline-none focus:ring-4 focus:ring-[var(--color-focus-ring)]"
      />
      {open && options.length > 0 && (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-20 mt-1 max-h-48 w-full overflow-y-auto rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-1 shadow-[var(--shadow-lg)]"
        >
          {options.map((option, index) => {
            const selected = index === active
            return (
              <li key={`${option.value}-${option.hint ?? ''}`}>
                <button
                  type="button"
                  role="option"
                  aria-selected={selected}
                  onMouseEnter={() => setActive(index)}
                  onClick={() => choose(option)}
                  className={`flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2 text-left text-[14px] ${
                    selected
                      ? 'bg-[var(--color-accent-soft)] text-[var(--color-accent-dark)]'
                      : 'text-[var(--color-text)]'
                  }`}
                >
                  <span className="font-semibold">{option.label}</span>
                  {option.hint && (
                    <span className="truncate text-[11px] text-[var(--color-text-muted)]">{option.hint}</span>
                  )}
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
