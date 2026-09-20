export function ChatHeader() {
  return (
    <header className="border-b border-slate-200 bg-white/85 backdrop-blur">
      <div className="mx-auto flex w-full max-w-2xl items-center px-3 py-3 sm:px-6 lg:max-w-4xl lg:px-8">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-800 text-base" aria-hidden="true">
            ♻️
          </div>
          <div>
            <h1 className="text-base font-semibold leading-tight text-slate-900">Scrapwisest</h1>
            <p className="text-[11px] leading-tight text-slate-500">
              Your scrap-price copilot
            </p>
          </div>
        </div>
      </div>
    </header>
  )
}
