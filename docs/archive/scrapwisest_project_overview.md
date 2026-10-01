# Scrapwisest — Project Overview

A price-transparency tool for waste pickers, built as an agentic AI system with a deliberate mix of LLM reasoning and deterministic code.

---

## 1. The Problem

### 1.1 Original framing (v1) — and why it didn't hold up

The first version of this idea was: point a phone camera at a piece of scrap, a CNN identifies the material, and the app returns what it's worth.

That idea broke down on one question: **who is this for?** A scrap dealer already knows exactly what materials are worth — that knowledge is literally their job and their income advantage. Building a material-identification tool for someone who's already the expert doesn't solve anything.

### 1.2 The real problem (v2)

The person genuinely at an information disadvantage isn't the dealer — it's the **picker** selling *to* the dealer. Experience teaches a picker to recognize plastic vs. metal, but it doesn't tell them what the price *should be right now*, and their only usual price reference is the same dealer they're negotiating with. That's not independent knowledge — it's just whatever that dealer has been willing to pay.

**This is a documented, real problem, not a hypothetical one.** Research on informal recycling markets found:
- Waste pickers earn a small fraction of what dealers and collection-center managers earn (roughly $745–750/month for pickers vs. $1,550–2,300/month for dealers/managers)
- In exploitative cases, pickers have been paid as little as **59.5% of their materials' true value**
- Middlemen have controlled both pricing and information, sometimes rigging weighing systems on top of underpricing

The closest historical parallel: fishermen and farmers in various developing regions using simple phone-based price-checking to stop being lowballed by isolated middlemen — once they could see what others were being paid nearby, the price gap closed. Same mechanism, applied here.

---

## 2. The Solution

Pickers report what they sold and for how much, after each sale. The system:
1. Turns that raw report into clean data
2. Checks the report isn't fake or manipulated before trusting it
3. Aggregates trustworthy reports into a fair-price estimate
4. Lets any picker check that estimate *before* their next sale, so they walk in with a number instead of walking in blind

Material identification (the original v1 idea) survives only as a **secondary helper feature** — useful when a picker isn't sure what something is, but not the core product.

---

## 3. System Architecture

```
Picker app (camera + voice, simple UI)
        |
        v
   Orchestrator  ── decides which path to take
        |
   ┌────┴────┐
   |         |
"I sold   "what's this
 this"      worth?"
   |         |
   v         v
Report-    Classifier agent (secondary)
Intake       |
Agent        v
   |     Price-Estimator Agent
   v         ^
Anomaly       |
Agent         |
   |          |
   v          |
Data Store ───┘
   |
   v
Forecasting Model (future — not built yet, see §5)
```

Two request types, two paths, converging on a shared data store.

---

## 4. The Agents

| Agent | Job | Uses an LLM? |
|---|---|---|
| **Orchestrator** | Routes requests; periodically reasons about data gaps offline | Yes, for offline gap analysis |
| **Report-intake agent** | Turns a picker's raw message (text or transcribed voice) into structured, validated data. Flags anything it's unsure about instead of guessing. | Yes — one structured-extraction call per report |
| **Anomaly agent** | Decides whether a report is trustworthy before it affects any price estimate. Three tiers: | Only Tier 3 |
| — Tier 1: Deterministic | Is the price wildly off the recent median? Free, instant. | No |
| — Tier 2: ML | Does price + quantity *together* look weird, even if price alone seems fine? (Isolation Forest) Free once trained. | No |
| — Tier 3: LLM | Only for reports Tier 1 or 2 already flagged — legitimate outlier or bad data? | Yes |
| **Price-estimator agent** | Fallback chain: local reports → city-wide reports → manually-collected seed price, blended by how much real data exists. Pure math. | No |
| **Classifier agent (secondary)** | Identifies material from a photo when a picker is unsure. Wraps a trained CNN. | No |

### Why not full LLM autonomy?

Considered and deliberately rejected. Every deterministic step above (anomaly Tiers 1–2, the price estimator, the classifier) is either arithmetic or a trained model doing a forward pass — asking an LLM to do that instead makes it slower, costlier, and dependent on a live connection, for zero accuracy benefit. Given the target user has unreliable connectivity and no money to spend on API calls on their behalf, an "LLM does everything" architecture doesn't just cost more — it stops working in the field for the exact person it's meant to help.

LLM reasoning is reserved for genuine judgment calls: parsing messy/ambiguous input, and adjudicating the ambiguous minority of flagged reports.

**A considered future upgrade, not yet built:** a reporter-trust agent that reasons about how much weight to give a report based on that picker's track record — a real judgment call, unlike the current "treat every report equally."

---

## 5. Models To Train

| Model | Purpose | Status |
|---|---|---|
| **CNN** (MobileNetV2 / EfficientNet-Lite) | Material classification from a photo (secondary feature) | Fine-tune on a public dataset (e.g. Kaggle garbage classification); export to TFLite/ONNX for offline use |
| **Isolation Forest** | Multivariate anomaly detection — catches price+quantity combinations that look wrong together even when price alone looks fine | **Ready to train** — 300+ labeled synthetic reports exist in `synthethic_report.json`; train now for demo, retrain on real data once available |
| **RNN/LSTM** (forecasting) | Would eventually replace the simple statistical price-estimator with real trend learning across time | **Not built.** With only a handful of early reports, an RNN would just memorize noise. The deterministic fallback chain is the correct MVP; this is a week 3–4 upgrade once there's real report volume |

---

## 6. Data Strategy

There's no existing dataset for "fair scrap prices by material and region" — it has to be built:
- **Week 1:** manually collect seed prices by visiting real scrap dealers/kabari points and photographing/interviewing — this seeds the price-estimator's fallback before any crowd reports exist
- **Ongoing:** picker-submitted reports accumulate the real dataset the anomaly ML tier and eventual forecasting model depend on
- **Cold-start problem to design around:** the app is only useful once enough pickers are reporting. Worth seeding the hackathon demo with a small set of realistic hardcoded reports rather than relying on live adoption during the build window

### Privacy notes
- Location stored at neighborhood/city level only — never precise GPS
- Reporter identity is an anonymized ID, never a real name or phone number in plaintext
- Any dealer-referencing data stays as anonymized aggregate signals only, never a named public callout — this protects the picker from retaliation risk, not just a legal formality

---

## 7. Tech Stack

- **Backend:** FastAPI, Python 3.11+
- **Orchestration:** LangGraph
- **ML:** PyTorch (CNN), scikit-learn (Isolation Forest)
- **Frontend:** plain HTML/JS, voice-first given the literacy/connectivity constraints
- **Data:** structured JSON/DB — seed prices, accumulated reports
- **LLM layer:** Nemotron on Nebius Token Factory — Nano (sale extraction), Super (picker copilot + tools), Ultra (anomaly judgment only)

---

## 8. Build Timeline (1-month hackathon)

- **Week 1:** Manual seed-data collection (real pickers/dealers) + report-intake pipeline + simple baseline estimator
- **Week 2:** Anomaly agent (all three tiers) + orchestrator reasoning loop + first real price-estimator wired to real data
- **Week 3:** Secondary CNN classifier + offline export (TFLite/ONNX) + voice interface (Urdu) + begin real field testing with pickers
- **Week 4:** Iterate on field feedback, polish, demo video, documentation

---

## 9. What's Already Built (as of this document)

- ✅ `backend/agent/nemotron.py` — Token Factory routing: Nano / Super / Ultra
- ✅ `backend/agent/main_agent.py` — Super copilot (deep agent) + per-picker memory
- ✅ `backend/agent/subagents/report_intaker.py` — Nano extraction + three-tier anomaly; Ultra only when flagged
- ✅ `backend/agent/tools/price_estimator.py` — local → city → seed fallback (no LLM)
- ✅ `backend/jobs/retrain_anomaly.py` — Nebius Serverless Job entrypoint
- ✅ Voice + photo chat UI (`frontend/`)
- ⬜ CNN classifier weights in the default deploy (optional via `requirements-ml.txt`)
- ⬜ Forecasting model / reporter-trust agent (post-MVP)

---

## 10. Known Issues / Bugs

- **`PRICE_PER_KG_BANDS` for `metal_aluminum` is wrong** (`agents/report_intake.py:36`): band is set to `(150, 500)` PKR/kg but the synthetic data (and real market rates) show aluminum trading at ~920–1,200 PKR/kg. Every aluminum report will be incorrectly flagged `needs_confirmation`. Fix: update the upper bound to at least `1,500`.

---
