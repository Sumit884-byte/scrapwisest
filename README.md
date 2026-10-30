# Scrapwisest

A scrap-price copilot waste pickers would actually use.

Ask a rate or log a sale in your language. Set country and city. The number on the card is that market's currency. Karachi rupees stay Karachi rupees — there is no FX.

Built for the **Best Apps and Agents** track: a real picker workflow on **Nemotron via Nebius Token Factory**, with Ultra reserved for hard judgment and Nano/Super on the everyday calls. MIT licensed.

---

## Why this exists

Dealers already know the market. Pickers usually don't. Their only price reference is often the same person they are negotiating with. Research on informal recycling markets has found pickers paid as little as **59.5% of materials' true value**.

The product is not "point a camera at scrap." It is: **walk into the next sale with a number**.

Two things a picker does every day:

1. **Ask a price** — *plastic ka rate kya hai*
2. **Log a sale** — *maine 2 kilo plastic becha, 300 rupay mile, income colony ke qareeb*

The agent routes those itself. Price math and cheap fraud checks stay in code. LLMs only run where judgment is required.

---

## How the number is chosen

A quote is scoped to **country + currency**. Neighborhood reports win first, then city, then country, all in that same currency. Trusted, fresh reports only.

Seeds and sanity bands exist only for **Pakistan / PKR**. Another country does not inherit those numbers, and a blank place does not silently become Pakistan. No reports and no seed → **no estimate**. We never invent a sale.

When `TAVILY_API_KEY` is set, low-confidence or seed estimates may attach public listings that already quote the **same currency per kg** in a sane band. Social posts are dropped. Listings never overwrite the quote.

---

## What works now

| Flow | What happens |
| --- | --- |
| Price question | Super calls `estimate_price` (neighborhood → city → country → market seed, or unavailable). One short reply in the picker's language. |
| Sale report | Nano extracts material / kg / money / place. Rules validate it. Isolation Forest can flag weird price+quantity. **Ultra** only runs if those cheaper tiers already flagged the report. |
| Follow-up | If a field is missing, Super asks **one** specific question. Conversation stays on the picker id. |
| Photo | Groq vision grades the pile (PET vs HDPE, aluminum vs steel, or refuse a selfie). Optional local CNN if you install the ML extras. A volume guess is not a logged sale. |
| Speech | English STT can stay on-device with NVIDIA Parakeet TDT 0.6B. Indian languages can use Sarvam. TTS is Sarvam or Edge. |

`GET /health` reports models, vision, Tavily, and voice providers. History and forecast endpoints exist as observational extras; they do not invent a current yard sale.

---

## Nemotron routing (Token Factory)

The track brief is the architecture: **Ultra when you need serious reasoning. Nano or Super for the fast, everyday calls.**

| Call | Model | Why |
| --- | --- | --- |
| Extract a messy sale message | **Nemotron 3 Nano** `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | High volume, structured, cheap |
| Picker chat, tools, memory | **Nemotron 3 Super** `nvidia/nemotron-3-super-120b-a12b` | Everyday copilot loop |
| "Is this flagged sale real or junk?" | **Nemotron 3 Ultra** `nvidia/Nemotron-3-Ultra-550b-a55b` | Real judgment, rare |

All three go through Nebius Token Factory (OpenAI-compatible). Nano is on `eu-north1`; Super and Ultra on `us-central1`. `LLM_PROVIDER=xkiro` is a free fallback when you have no Token Factory key.

```text
Picker message

      │
      ▼

Super (everyday) ── price question ──► estimate_price (no LLM)
      │                               └── optional Tavily listings (same currency /kg)
      └── sale report ──► Nano extract ──► rules ──► Isolation Forest
                                                      │
                                              flagged? ── yes ──► Ultra judge
                                                      │
                                                     no ──► store + confirm
```

---

## Quick start

You need a [Token Factory](https://tokenfactory.nebius.com) API key (or an xKiro key).

```bash
cp .env.example backend/.env
# put NEBIUS_API_KEY (or XKIRO_API_KEY) in backend/.env
# optional: TAVILY_API_KEY, GROQ_API_KEY, SARVAM_API_KEY

cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
env -u DATABASE_URL -u SARVAM_API_KEY uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

Unset `DATABASE_URL` and `SARVAM_API_KEY` in the process environment so `backend/.env` wins.

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). Set country and city in Place · Language, then:

- `What's the PET bottle rate in Karachi?`
- `maine 2 kilo PET becha, 300 rupay mile, income colony ke qareeb`
- Attach a scrap photo, or speak with the mic

Optional CNN (photo helper only): `pip install -r backend/requirements-ml.txt`

---

## Product notes

Sale reports that need confirmation stay pending until the picker confirms. Confirmed reports join the trusted price pool.

Location strings are normalized so `Income Colony`, `Income Colony, Multan`, and `income colony ke qareeb` can share history.

Nebius calls use bounded timeouts, retries, and daily spend guards. If the LLM is down, simple price questions can still use the deterministic estimator.

`POST /api/v1/reports` uses the same checks as chat. Flagged REST reports return `needs_confirmation=true` and are not trusted pricing.

Photos are temporary and deleted after classification. Chat text is restored from device-local storage. The header has Clear and a local dark-mode toggle.

---

## CI/CD

GitHub Actions (`.github/workflows/ci.yml`) runs on every push and pull request to `main`:

1. **Backend** — `pytest` (price estimator, health, model routing). No API key required.
2. **Frontend** — `oxlint` + production build.
3. **CD** (push to `main` only) — publishes the `frontend-dist` artifact so a host can pick it up.

```bash
cd backend && pip install -r requirements-dev.txt && env -u DATABASE_URL PYTHONPATH=. pytest -q
cd frontend && npm ci && npm run lint && npm run build
```

---

## Deploy on Nebius (optional)

Neither is required for the track. Both are wired so you can ship the same MVP.

**Serverless Endpoint** — the picker UI + `/chat` in one container:

```bash
docker build -t scrapwisest:mvp .
nebius ai endpoint create \
  --name scrapwisest \
  --image <your-image> \
  --container-port 8000 \
  --env NEBIUS_API_KEY="$NEBIUS_API_KEY" \
  --public
```

**Serverless Job** — retrain the Isolation Forest from trusted reports. No LLM call.

```bash
python -m jobs.retrain_anomaly
```

---

## Repo map

```text
backend/app/agent/nemotron.py      # Token Factory client + Nano/Super/Ultra
backend/app/agent/main_agent.py    # Super copilot
backend/app/services/price_estimator.py
backend/app/services/web_market.py # same-currency listing filter
backend/app/services/parakeet_stt.py
frontend/                          # typeahead place + voice + photo chat
```

Older product notes live under [`docs/archive/`](docs/archive/).
