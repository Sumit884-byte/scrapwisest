import { useEffect, useState } from "react";
import { getReports } from "../api";
import { materialLabel } from "../data";
import { Spinner } from "./Icons";

export default function ReportsFeed() {
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    getReports()
      .then((data) => setReports(Array.isArray(data) ? data.slice().reverse() : []))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="flex justify-center py-10 text-slate-400"><Spinner className="w-6 h-6" /></div>;
  if (error) return <div className="rounded-2xl p-4 bg-red-50 border border-red-200 text-red-700 text-sm">{error}</div>;
  if (!reports.length) return <p className="text-center text-slate-400 py-10 text-sm">No reports yet.</p>;

  return (
    <div className="space-y-2">
      <p className="text-sm text-slate-500 mb-3">{reports.length} reports collected</p>
      {reports.map((r, i) => {
        const m = materialLabel(r.material_type);
        return (
          <div key={i} className="flex items-center gap-3 bg-white rounded-2xl border border-slate-100 px-4 py-3 shadow-sm">
            <span className="text-2xl">{m.icon}</span>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-slate-800 truncate">{m.en}</p>
              <p className="text-xs text-slate-400">{r.quantity_kg} kg · {r.location}</p>
            </div>
            <div className="text-right">
              <p className="text-sm font-semibold text-brand-700">{r.price_paid_pkr_per_kg}</p>
              <p className="text-[10px] text-slate-400">PKR/kg</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
