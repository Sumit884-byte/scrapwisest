export function ChatHeader() {
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
        <div className="hidden items-center gap-2 text-[11px] font-semibold text-[#65705f] sm:flex">
          <span className="status-dot" />
          <span>Local market assistant</span>
        </div>
      </div>
    </header>
  )
}
