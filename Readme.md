 # Gold Deal Finder

Gold Deal Finder scrapes gold listings, compares selling prices against a calculated benchmark, stores every scan locally, and exposes a dashboard for reviewing the latest scan with historical drill-down.

## What Changed

- Latest scan is the primary dashboard context.
- Historical scans are selectable without blending datasets.
- Manual scan triggering is available locally by default.
- Local runtime is standardized on `http://localhost:8000`.

## Local Setup

### Requirements

- Python 3.8+
- Network access for scraping and live gold pricing

### Install

```bash
python3 -m pip install -r requirements.txt
```

### Run The App

Recommended local path:

```bash
python3 run.py
```

Alternative direct server path:

```bash
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

### Local URLs

- App: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/api/v1/health`

## Runtime Notes

- Scan files are stored in `data/` as `scan_results_<timestamp>.json`.
- If `data/` is empty, sample scans are generated on startup so the dashboard has something to render.
- Manual scans use `POST /api/v1/scan`.
- `GET /api/v1/scan` is kept as a compatibility alias.

## Useful Environment Variables

- `APP_HOST`: server host, default `0.0.0.0`
- `APP_PORT`: server port, default `8000`
- `APP_RELOAD`: enable reload mode, default `true`
- `AUTO_OPEN_BROWSER`: auto-open the dashboard on startup, default `false`
- `SCAN_COOLDOWN_MINUTES`: backend scan throttle, default `0` for local use
- `HISTORICAL_SCAN_LIMIT_DEFAULT`: default number of scans searched by historical products API, default `5`
- `MAX_HISTORICAL_SCAN_LIMIT`: upper bound for multi-scan history queries, default `25`

## Dashboard Workflow

1. Open the dashboard and review the latest scan.
2. Use filters, sorting, shortlist, and export on the active scan only.
3. Switch to `Scan Archive` to open any previous scan.
4. Use `Return To Latest` to restore the current live context.
5. Trigger a new manual scan from the header when needed.

## Key API Endpoints

- `GET /api/v1/historical/scans`
- `GET /api/v1/historical/scan/{scan_id}`
- `GET /api/v1/historical/products`
- `POST /api/v1/scan`
- `GET /api/v1/products/latest`
- `GET /api/v1/stats/summary`
- `GET /api/v1/spot-price`

## Data Notes

- `.json` and `.json.gz` scan files are supported.
- Historical product queries accept `scan_limit` to bound multi-scan loading.
- The dashboard keeps favorites in local browser storage.
