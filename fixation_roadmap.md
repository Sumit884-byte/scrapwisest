# ScrapSense Refactor Roadmap

## B. Resilience, Timeouts & Retries

Nebius Token Factory calls currently have no timeouts or circuit breakers. If an API call hangs or Nebius experiences high latency, the picker's connection will stay open indefinitely until it times out.

- Add `request_timeout=15.0` and `max_retries=2` to all `ChatOpenAI` client instantiations.
- Implement a graceful fallback: if the LLM is unresponsive, return a deterministic fallback response rather than a 500 error.

### C. Location Normalization Engine

Instead of checking `r.location.lower() == location.lower()`, build a location resolver:

- Canonicalize inputs (e.g. "Income Colony, Multan" -> City: "Multan", Area: "Income Colony").
- Handle fuzzy matching using `thefuzz` or trigram similarity in SQL to account for spelling differences in transliterated names (e.g., "Bosan Road" vs "Bosan Rd" vs "Bosan Rood").

---

## 5. What to ADD (To Make It a Real Production Product) 🚀

1. **Dedicated REST Endpoints (Not Just `/chat`)**
   - Direct price checks: `GET /api/v1/prices/estimate?material=plastic_pet&city=Multan&neighborhood=Income%20Colony` (Free, instant, doesn't waste LLM tokens).
   - Material directory: `GET /api/v1/materials` (Returns list of materials, current market baseline rates, local names in Urdu and English).
   - Report listing: `GET /api/v1/reports?picker_id=...&limit=20` (Allows pickers to view their sales history).

2. **Server-Sent Events (SSE) / Streaming for `/chat`**
   - Nemotron Super can take 2–5 seconds on deep reasoning. Streaming tokens via SSE (`text/event-stream`) dramatically improves perceived latency on mobile networks.

3. **Audit Logging & Telemetry**
   - Log latency, token usage, and anomaly scores per request with correlation IDs (`X-Request-ID`).

4. **Database Migrations (Alembic)**
   - Enable zero-downtime schema evolution as new fields (like buyer dealer notes or grade quality) are added.

5. **Comprehensive Test Suite**
   - Fixture-based tests with `pytest-asyncio`.
   - Mock LLM responses to test graph edge routing deterministically without spending API credits during CI.

---

## 6. Phased Refactoring Roadmap 🗺️

To execute this without breaking functionality, we can approach the refactor in four clean phases:

```text
Phase 1: Foundation & Cleanup
├── Remove committed DB binaries and unneeded files (.gitignore update)
├── Set up app/ directory structure and pydantic Settings
└── Fix critical CNN vs. MaterialType enum conflict & file path resolutions

Phase 2: Data Layer Modernization
├── Implement SQLAlchemy ORM models and SQLite/PostgreSQL engine with WAL mode
├── Build Alembic migration environment
└── Replace db_store.py with an async Repository pattern

Phase 3: Domain & Agent Refinement
├── Refactor Nemotron clients with proper pooling, retries, and timeouts
├── Update prompts with Pakistani scrap units (Maund, Pao) and new materials (Copper, Brass, Iron)
└── Clean up image processing with automated lifecycle cleanup

Phase 4: API Expansion & Production Hardening
├── Split API routes into /chat, /prices, /reports, /health
├── Add structured error handling and CORS security
└── Expand pytest coverage for full CI/CD pipeline
```

---

### How would you like to proceed?

We can start by executing Phase 1 (directory restructuring, removing dead files/binaries, and fixing the critical CNN-schema mismatch and path resolutions), or tackle specific areas you prioritize first. Let me know what you'd like to dive into!
