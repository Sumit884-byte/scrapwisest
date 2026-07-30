import { useState } from "react";
import { useSpeech } from "../useSpeech";
import { submitReport } from "../api";
import { MATERIALS, LOCATIONS } from "../data";
import { Mic, Check, Alert, Spinner } from "./Icons";

export default function SubmitReport() {
  const [message, setMessage] = useState("");
  const [reportedBy] = useState(() => `picker_${Math.floor(Math.random() * 900 + 100)}`);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const { supported, listening, transcript, start, stop, setTranscript } = useSpeech("ur-PK");

  // Sync voice transcript into message box
  const handleMic = () => {
    if (listening) { stop(); setMessage(transcript || message); }
    else { start(); }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!message.trim()) return;
    setLoading(true); setResult(null); setError(null);
    try {
      const res = await submitReport(message, reportedBy);
      setResult(res);
      if (res.accepted) { setMessage(""); setTranscript(""); }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const displayMessage = listening ? transcript : message;

  return (
    <div className="space-y-5">
      <p className="text-sm text-slate-500">
        Tell us what you sold — in English, Urdu, or Roman Urdu.
      </p>

      {/* Quick-fill chips */}
      <div>
        <p className="text-xs font-medium text-slate-400 mb-2 uppercase tracking-wide">Quick fill</p>
        <div className="flex flex-wrap gap-2">
          {MATERIALS.slice(0, 5).map((m) => (
            <button key={m.id} type="button"
              onClick={() => setMessage(`sold 3 kg ${m.en.toLowerCase()} for 400 rupees near Cantt`)}
              className="text-xs px-3 py-1.5 rounded-full bg-brand-50 text-brand-700 border border-brand-200 hover:bg-brand-100 transition-colors">
              {m.icon} {m.en}
            </button>
          ))}
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="relative">
          <textarea
            rows={3}
            value={displayMessage}
            onChange={(e) => { setMessage(e.target.value); }}
            placeholder="e.g. sold 3 kilo plastic bottle for 420 rupees near cantt"
            className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 pr-14 text-sm shadow-sm resize-none focus:outline-none focus:ring-2 focus:ring-brand-400 placeholder:text-slate-300"
          />
          {supported && (
            <button type="button" onClick={handleMic}
              className={`absolute right-3 bottom-3 w-9 h-9 rounded-full flex items-center justify-center transition-all
                ${listening
                  ? "bg-brand-500 text-white animate-mic"
                  : "bg-slate-100 text-slate-500 hover:bg-brand-50 hover:text-brand-600"}`}>
              <Mic className="w-4 h-4" />
            </button>
          )}
        </div>

        <button type="submit" disabled={loading || !message.trim()}
          className="w-full py-3 rounded-2xl bg-brand-500 text-white font-semibold text-sm
            hover:bg-brand-600 active:scale-[0.98] transition-all disabled:opacity-40 disabled:cursor-not-allowed
            flex items-center justify-center gap-2">
          {loading ? <><Spinner className="w-4 h-4" /> Submitting…</> : "Submit Report"}
        </button>
      </form>

      {/* Result card */}
      {result && (
        <div className={`animate-rise rounded-2xl p-4 border text-sm space-y-1
          ${result.accepted
            ? "bg-brand-50 border-brand-200 text-brand-800"
            : result.needs_confirmation
              ? "bg-amber-50 border-amber-200 text-amber-800"
              : "bg-red-50 border-red-200 text-red-800"}`}>
          <div className="flex items-center gap-2 font-semibold">
            {result.accepted
              ? <><Check className="w-4 h-4" /> Report accepted</>
              : <><Alert className="w-4 h-4" /> {result.needs_confirmation ? "Needs confirmation" : "Flagged as anomaly"}</>}
          </div>
          {result.accepted && result.report && (
            <p>{result.report.material_type} · {result.report.quantity_kg} kg · {result.report.price_paid_pkr_per_kg} PKR/kg · {result.report.location}</p>
          )}
          {result.needs_confirmation && <p>{result.confirmation_reason}</p>}
          {result.anomaly_verdict && <p>{result.anomaly_verdict.reason}</p>}
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
