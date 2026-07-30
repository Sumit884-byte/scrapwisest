import { useState } from "react";
import { queryPrice } from "../api";
import { MATERIALS, LOCATIONS, materialLabel } from "../data";
import { Spinner, Tag } from "./Icons";

export default function PriceCheck() {
  const [material, setMaterial] = useState(MATERIALS[0].id);
  const [location, setLocation] = useState(LOCATIONS[0]);
  const [estimate, setEstimate] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const check = async () => {
    setLoading(true); setEstimate(null); setError(null);
    try {
      const res = await queryPrice(material, location);
      if (res.error) setError(res.error);
      else setEstimate(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const confPct = estimate ? Math.round(estimate.confidence * 100) : 0;
  const confColor = confPct >= 70 ? "bg-brand-500" : confPct >= 40 ? "bg-amber-400" : "bg-slate-300";
  const tierLabel = {
    "local+city": "Local + city reports",
    local: "Local reports",
    city: "City-wide reports",
    seed: "Baseline estimate",
  };

  return (
    <div className="space-y-5">
      <p className="text-sm text-slate-500">
        Check the fair price <span className="font-medium text-slate-700">before</span> you sell.
      </p>

      {/* Material grid */}
      <div>
        <p className="text-xs font-medium text-slate-400 mb-2 uppercase tracking-wide">Material</p>
        <div className="grid grid-cols-4 gap-2">
          {MATERIALS.map((m) => (
            <button key={m.id} onClick={() => setMaterial(m.id)}
              className={`flex flex-col items-center gap-1 py-3 rounded-2xl border text-center transition-all
                ${material === m.id
                  ? "bg-brand-500 border-brand-500 text-white shadow-md scale-[1.03]"
                  : "bg-white border-slate-200 text-slate-600 hover:border-brand-300"}`}>
              <span className="text-2xl">{m.icon}</span>
              <span className="text-[10px] leading-tight font-medium">{m.en}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Location */}
      <div>
        <p className="text-xs font-medium text-slate-400 mb-2 uppercase tracking-wide">Location</p>
        <select value={location} onChange={(e) => setLocation(e.target.value)}
          className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-brand-400">
          {LOCATIONS.map((l) => <option key={l} value={l}>{l}</option>)}
        </select>
      </div>

      <button onClick={check} disabled={loading}
        className="w-full py-3 rounded-2xl bg-brand-500 text-white font-semibold text-sm
          hover:bg-brand-600 active:scale-[0.98] transition-all disabled:opacity-40
          flex items-center justify-center gap-2">
        {loading ? <><Spinner className="w-4 h-4" /> Checking…</> : <><Tag className="w-4 h-4" /> Check Fair Price</>}
      </button>

      {estimate && (
        <div className="animate-rise rounded-3xl bg-gradient-to-br from-brand-600 to-brand-800 text-white p-6 shadow-lg">
          <div className="flex items-baseline gap-2">
            <span className="text-5xl font-bold tracking-tight">{estimate.estimated_price_per_kg}</span>
            <span className="text-brand-100 font-medium">PKR / kg</span>
          </div>
          <div className="mt-1 flex items-center gap-2 text-brand-100 text-sm">
            <span>{materialLabel(estimate.material_type).icon} {materialLabel(estimate.material_type).en}</span>
            <span className="opacity-60">·</span>
            <span>{estimate.location}</span>
          </div>

          {/* Confidence */}
          <div className="mt-5">
            <div className="flex justify-between text-xs text-brand-100 mb-1">
              <span>Confidence · {tierLabel[estimate.tier_used] ?? estimate.tier_used}</span>
              <span>{confPct}%</span>
            </div>
            <div className="h-2 rounded-full bg-brand-900/40 overflow-hidden">
              <div className={`h-full ${confColor} transition-all duration-500`} style={{ width: `${confPct}%` }} />
            </div>
            <p className="mt-2 text-[11px] text-brand-200">
              Based on {estimate.local_report_count} local · {estimate.city_report_count} city reports
            </p>
          </div>
        </div>
      )}

      {error && (
        <div className="animate-rise rounded-2xl p-4 bg-red-50 border border-red-200 text-red-700 text-sm">
          {error}
        </div>
      )}
    </div>
  );
}
