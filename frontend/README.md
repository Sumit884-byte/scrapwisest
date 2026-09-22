# Scrapwisest Frontend

Chat client for the Scrapwisest FastAPI backend — a price-transparency assistant for waste pickers. Message in English, Hindi, or Hinglish, attach a photo of a material, or dictate with the mic.

## Stack

- Vite + React 19 + TypeScript
- Tailwind CSS v4 (via `@tailwindcss/vite`)

## Run

```bash
npm install
npm run dev        # http://localhost:5173
```

The Vite dev server proxies `/chat`, `/health`, `/transcribe`, and `/speak` to the FastAPI backend at `http://localhost:8000` (see `vite.config.ts`). Start the backend first:

```bash
# from the repo root
uvicorn backend.main:app --port 8000
```

For a non-local backend, set `VITE_API_BASE` to the backend origin before building/running.

## Scripts

| Command        | Description                        |
| -------------- | ---------------------------------- |
| `npm run dev`  | Start the dev server with HMR      |
| `npm run build`| Type-check (`tsc -b`) + production build |
| `npm run preview` | Preview the production build   |
| `npm run lint` | Run Oxlint                         |
