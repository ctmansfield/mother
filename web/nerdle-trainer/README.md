# Nerdle Trainer (web)

Vite + React + Tailwind (Node 18 compatible).

## Dev (local)
npm --prefix web/nerdle-trainer install
npm --prefix web/nerdle-trainer run dev

## Dev (LAN)
npm --prefix web/nerdle-trainer run dev:lan
# if HMR needs explicit host:
VITE_PUBLIC_HOST=10.10.10.2 npm --prefix web/nerdle-trainer run dev:lan

### API
Proxy: /nerdle/* -> http://127.0.0.1:8082 (FastAPI on same box).
Or set Settings → API Base to http://10.10.10.2:8082/nerdle.
