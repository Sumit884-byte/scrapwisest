# Scrapwisest

A scrap-price copilot waste pickers would actually use.

Message what you sold, or ask what something is worth, in English, Telugu, Roman Telugu, Urdu, or Roman Urdu. ScrapSense turns that messy field note into a trusted price — and remembers the neighborhood so the next check is faster.

Built for the **Best Apps and Agents** track: a real workflow, powered by **Nemotron on Nebius Token Factory**, with Ultra reserved for hard judgment and Nano/Super on the everyday calls.

---

## Why this exists

Dealers already know the market. Pickers usually don't. Their only price reference is often the same person they are negotiating with. Research on informal recycling markets has found pickers paid as little as **59.5% of materials' true value**.

The product is not "point a camera at scrap." It is: **walk into the next sale with a number**.

Two things a picker does every day:

1. **Ask a price** — *plastic ka rate kya hai*
2. **Log a sale** — *maine 2 kilo plastic becha, 300 rupay mile, income colony ke qareeb*

The agent routes those itself. Price math and cheap fraud checks stay in code. LLMs only run where judgment is required.

---

## MVP (what works now)

| Flow | What happens |
| --- | --- |
| Price question | Super calls `estimate_price` (local reports → city → seed prices). One short reply in the picker's language. |
| Sale report | Nano extracts material / kg / PKR / area. Rules validate it. Isolation Forest can flag weird price+quantity. **Ultra** only runs if those cheaper tiers already flagged the report. |
| Follow-up | If a field is missing, Super asks **one** specific question. Conversation stays on the picker id. |
| Photo | Optional helper. CNN if a model is present; otherwise the agent just asks what it is. No LLM spent on pixels. |

Out of scope for this MVP (and not needed to demo): forecasting, a reporter-trust score, a trained CNN in the default deploy.

---

## Nemotron routing (Token Factory)

The track brief is the architecture: **Ultra when you need serious reasoning. Nano or Super for the fast, everyday calls.** That keeps the chat responsive and the credits on the calls that matter.

| Call | Model | Why |
| --- | --- | --- |
| Extract a messy sale message | **Nemotron 3 Nano** `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | High volume, structured, cheap |
| Picker chat, tools, memory | **Nemotron 3 Super** `nvidia/nemotron-3-super-120b-a12b` | Everyday copilot loop |
| "Is this flagged sale real or junk?" | **Nemotron 3 Ultra** `nvidia/Nemotron-3-Ultra-550b-a55b` | Real judgment, rare |

All three go through Nebius Token Factory (OpenAI-compatible). Nano is on `eu-north1`; Super and Ultra on `us-central1`. Override with environment variables if your project is pinned to one region.

```text
Picker message

      │
      ▼

Super (everyday) ── price question ──► estimate_price (no LLM)
      │
      └── sale report ──► Nano extract ──► rules ──► Isolation Forest
                                                      │
                                              flagged? ── yes ──► Ultra judge
                                                      │
                                                     no ──► store + confirm
```

---

## Quick start

You need a [Token Factory](https://tokenfactory.nebius.com) API key.

```bash
cp .env.example backend/.env
# put NEBIUS_API_KEY in backend/.env

cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --port 8000
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

Optional CNN (photo helper only):

```bash
pip install -r backend/requirements-ml.txt
```

### Try it

- `plastic ka rate kya hai`
- `maine 2 kilo plastic becha, 300 rupay mile, income colony ke qareeb`
- Attach a photo, or speak with the mic

`GET /health` returns the live Nano / Super / Ultra map.

### Load the demo market dataset

The repository includes a small, clearly labeled demo dataset so the price
estimator can demonstrate neighborhood and cross-neighborhood estimates before
real picker reports exist. It is not loaded automatically in production.

From the repository root, run:

```bash
python backend/scripts/load_demo_data.py
```

The loader is idempotent and marks inserted rows with the internal
`demo-seed` picker id. To start with a clean demo database, remove the local
`backend/reports.db` file first, then run the loader again.

For local frontend testing without a Nebius API key, set `DEMO_MODE=true` in
`backend/.env`. This bypasses the LLM and returns a clearly labeled
deterministic estimate from the demo dataset. It is only a UI preview mode and
does not demonstrate the Nemotron workflow required for the hackathon.

Sale reports that need confirmation are stored in a small pending-review table
until the picker confirms or corrects them. Confirmed reports are then added to
the trusted price pool and can influence future estimates.

When `TAVILY_API_KEY` is configured, low-confidence estimates also include
external market context and source links from Tavily. External web context is
shown separately from trusted picker reports and does not silently overwrite the
deterministic local estimate.

Location inputs are normalized deterministically so common variants such as
`Income Colony`, `Income Colony, Multan`, and `income colony ke qareeb` can
share the same local report history.

Nebius calls use bounded timeouts and configurable retries. If the LLM is
temporarily unavailable, simple price questions can fall back to the local
deterministic estimator instead of returning a server error.

Reports submitted through `POST /api/v1/reports` now use the same deterministic
and Isolation Forest checks as the chat workflow. Flagged REST reports are
returned with `needs_confirmation=true` and are not added to trusted pricing.

Uploaded photos are treated as temporary inputs and removed after image
classification, including when classification fails.

The visible text conversation is also restored from device-local storage after
a page refresh. Uploaded image files are not persisted in that transcript.

---

## CI/CD

GitHub Actions (`.github/workflows/ci.yml`) runs on every push and pull request to `main`:

1. **Backend** — `pytest` (price estimator, health, model routing). No API key required.
2. **Frontend** — `oxlint` + production build.
3. **CD** (push to `main` only) — publishes the `frontend-dist` artifact so a host can pick it up.

Run the same checks locally:

```bash
cd backend && pip install -r requirements-dev.txt && PYTHONPATH=. pytest -q
cd frontend && npm ci && npm run lint && npm run build
```

---

## Deploy on Nebius (optional)

Neither is required for the track. Both are wired so you can ship the same MVP.

**Serverless Endpoint** — the picker UI + `/chat` in one container:

```bash
docker build -t scrapsense:mvp .
# then, with the Nebius CLI and your project ids:
nebius ai endpoint create \
  --name scrapsense \
  --image <your-image> \
  --container-port 8000 \
  --env NEBIUS_API_KEY="$NEBIUS_API_KEY" \
  --public
```

**Serverless Job** — retrain the Isolation Forest from trusted reports after people start logging sales. No LLM call.

```bash
# from backend/, or inside the same image
python -m jobs.retrain_anomaly
```

```bash
nebius ai job create \
  --name scrapsense-retrain \
  --image <your-image> \
  --container-command "python -m jobs.retrain_anomaly"
```

---

## Repo map

```text
backend/agent/nemotron.py          # Token Factory client + Nano/Super/Ultra split
backend/agent/main_agent.py        # Super copilot (deep agent)
backend/agent/subagents/           # sale → extract → validate → anomaly
backend/agent/tools/               # price estimator (pure math)
backend/jobs/retrain_anomaly.py    # Serverless Job entrypoint
frontend/                          # voice + photo chat UI
```

Longer product notes: [`scrapSense_project_overview.md`](scrapSense_project_overview.md).
