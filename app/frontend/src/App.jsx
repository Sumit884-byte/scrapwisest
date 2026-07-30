import { useState } from "react";
import SubmitReport from "./components/SubmitReport";
import PriceCheck from "./components/PriceCheck";
import ReportsFeed from "./components/ReportsFeed";
import { Mic, Tag, List, Recycle } from "./components/Icons";

const TABS = [
  { id: "price",   label: "Check Price", ur: "قیمت دیکھیں", Icon: Tag },
  { id: "report",  label: "I Sold",      ur: "میں نے بیچا",  Icon: Mic },
  { id: "feed",    label: "Reports",     ur: "رپورٹس",       Icon: List },
];

export default function App() {
  const [tab, setTab] = useState("price");

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="bg-gradient-to-r from-brand-600 to-brand-700 text-white">
        <div className="max-w-md mx-auto px-5 pt-6 pb-8">
          <div className="flex items-center gap-2">
            <div className="w-9 h-9 rounded-xl bg-white/15 flex items-center justify-center">
              <Recycle className="w-5 h-5" />
            </div>
            <div>
              <h1 className="font-bold text-lg leading-none">ScrapSense</h1>
              <p className="text-brand-100 text-xs mt-0.5">Fair prices for every picker</p>
            </div>
          </div>
        </div>
      </header>

      {/* Content card overlapping header */}
      <main className="flex-1 max-w-md w-full mx-auto px-4 -mt-4">
        <div className="bg-white rounded-3xl shadow-xl border border-slate-100 p-5 min-h-[60vh]">
          {tab === "price" && <PriceCheck />}
          {tab === "report" && <SubmitReport />}
          {tab === "feed" && <ReportsFeed />}
        </div>
        <p className="text-center text-[11px] text-slate-400 mt-4 px-6 leading-relaxed">
          Prices are community estimates to help you negotiate — not a guaranteed rate.
        </p>
      </main>

      {/* Bottom tab bar */}
      <nav className="sticky bottom-0 bg-white/90 backdrop-blur border-t border-slate-100">
        <div className="max-w-md mx-auto flex">
          {TABS.map(({ id, label, ur, Icon }) => (
            <button key={id} onClick={() => setTab(id)}
              className={`flex-1 flex flex-col items-center gap-1 py-3 transition-colors
                ${tab === id ? "text-brand-600" : "text-slate-400"}`}>
              <Icon className="w-5 h-5" />
              <span className="text-[11px] font-medium">{label}</span>
            </button>
          ))}
        </div>
      </nav>
    </div>
  );
}
