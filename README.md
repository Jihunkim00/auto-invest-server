# Auto Invest Server

A FastAPI-based automated investing backend that integrates with Alpaca and OpenAI services.

## Features

- FastAPI REST API
- Alpaca paper trading integration
- OpenAI-based signal and market analysis support
- Scheduler and runtime settings management
- SQLite local database support

## Prerequisites

- Python 3.12
- Windows / PowerShell (works on other platforms with Python support)
- Git (optional)

## Setup

1. Open PowerShell in the project root:
   ```powershell
   cd d:\auto-invest-server
   ```

2. Activate the virtual environment:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

3. Install dependencies if needed:
   ```powershell
   python -m pip install -r requirements.txt
   ```

4. Ensure environment values are set in `.env`.

## Environment

The app loads settings from `.env` using `pydantic-settings`.

Important variables:

- `APP_ENV` - application environment, e.g. `dev`
- `APP_NAME` - application display name
- `APP_DEBUG` - enable debug mode
- `HOST` / `PORT` - server host and port
- `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` - Alpaca API credentials
- `ALPACA_BASE_URL` - Alpaca base URL
- `DEFAULT_SYMBOL` - default trading symbol
- `DEFAULT_US_SYMBOL` - default US symbol, defaults to `AAPL`
- `DEFAULT_KR_SYMBOL` - default Korean symbol, defaults to `005930`
- `DATABASE_URL` - SQLite database connection string
- `LOG_DIR` - runtime log directory
- `CONFIG_DIR` - base config directory for YAML config defaults
- `WATCHLIST_US_PATH` / `WATCHLIST_KR_PATH` - market watchlist YAML paths
- `REFERENCE_SITES_CONFIG_PATH` - path to reference site YAML config
- `OPENAI_API_KEY` - OpenAI API key

Use `.env.example` as the safe-default template. Keep `DEFAULT_SYMBOL=AAPL`
for legacy Alpaca compatibility. Korean symbols must be strings so leading
zeroes are preserved.

## Run

Start the FastAPI server from the project root:

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

After startup, open:

- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/docs` for Swagger UI

## Project structure

- `app/main.py` - FastAPI app and router registration
- `app/config.py` - settings loader
- `app/db/` - database and ORM initialization
- `app/routes/` - API route definitions
- `app/services/` - business logic and service layer
- `config/reference_sites.yaml` - reference site configuration

## Database

The local SQLite database file is `auto_invest.db` by default.

Database initialization is handled on startup by `app.db.init_db.init_db()`.

## KIS safety lifecycle

- Operations readiness: `/ops/production-readiness` is read-only and reports
  dry-run/live state, kill switch, KIS real-order state, scheduler real-order
  state, scheduler buy/sell flags, live auto settings, today's order and broker
  submit counts, safety violations, KR watchlist validity, DB writability, docs
  presence, and recommended next actions.
- Readiness: `/kis/auto/readiness` and `/kis/auto/preflight-once` report gate state only.
- Exit preflight: `/kis/live-exit/preflight-once` evaluates held-position exits without submitting and keeps manual confirmation required.
- Manual live sell: `/kis/orders/manual-submit` and `/kis/orders/submit-manual` remain the explicit live order paths and require `confirm_live`.
- Shadow exit: `/kis/exit-shadow/run-once` records dry-run sell decisions only.
- Shadow review: `/kis/exit-shadow/review` aggregates historical shadow decision quality read-only.
- Review queue: `/kis/exit-shadow/review-queue` plus mark-reviewed/dismiss endpoints only update local operator state.
- Limited auto sell: `/kis/limited-auto-sell/run-once` is disabled by default, SELL-only, stop-loss-only by default, audited, capped, and blocked unless every runtime, position, queue-review, duplicate-order, market/session, notional, and daily-limit gate passes. KIS auto buy and scheduler real orders remain disabled.
- Buy shadow: `/kis/buy-shadow/run-once` prepares a future buy-side decision as dry-run/shadow only, with no KIS buy submit, no manual submit, and live auto buy still disabled.
- Limited auto buy: `/kis/limited-auto-buy/run-once` is disabled by default, BUY-only, audited, capped, and blocked unless live auto buy plus all score, confidence, cash, position, duplicate-order, market/session, notional, daily-limit, and optional shadow-review gates pass.
- Scheduler live automation: `/kis/scheduler/run-live-once` is disabled by default and can only orchestrate the guarded limited auto sell/buy services when scheduler live, real-order, side-specific, dry-run, kill-switch, and daily-order gates are explicitly enabled.

## Testing

Run tests with:

```powershell
python -m pytest
```

## Operations docs

- `docs/OPERATIONS.md` - operator guide, safety model, flows, and emergency procedure.
- `docs/PRODUCTION_CHECKLIST.md` - production and live-order checklist.
- `docs/CLOUD_DEPLOYMENT.md` - cloud/VPS runtime configuration and deployment prep.

## Notes

- The app currently uses a scheduler service on startup.
- The default symbol is configured via `DEFAULT_SYMBOL`.
- Keep API keys and secrets out of source control.
