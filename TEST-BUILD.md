# Test build

Production Vite UI, served by FastAPI from `backend/static/`.

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# NEBIUS_API_KEY (or XKIRO_API_KEY) in backend/.env
env -u DATABASE_URL -u SARVAM_API_KEY uvicorn main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 — same origin as `/chat` and `/health`. No Vite proxy.

Zip (local, gitignored): `docs/demo/scrapwisest-test-build.zip` — the `index.html` + `assets/` from this build.

This is a local/test build, not a public host.
