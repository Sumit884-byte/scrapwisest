// Thin wrapper over the FastAPI backend (proxied via /api in vite.config.js)

async function json(res) {
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `Request failed (${res.status})`);
  }
  return res.json();
}

export function submitReport(message, reportedBy) {
  return fetch("/api/report", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, reported_by: reportedBy }),
  }).then(json);
}

export function getReports() {
  return fetch("/api/reports").then(json);
}

export function queryPrice(material, location) {
  const q = new URLSearchParams({ material, location });
  return fetch(`/api/price?${q}`).then(json);
}
