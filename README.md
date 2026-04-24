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
- `DATABASE_URL` - SQLite database connection string
- `REFERENCE_SITES_CONFIG_PATH` - path to reference site YAML config
- `OPENAI_API_KEY` - OpenAI API key

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

## Testing

Run tests with:

```powershell
python -m pytest
```

## Notes

- The app currently uses a scheduler service on startup.
- The default symbol is configured via `DEFAULT_SYMBOL`.
- Keep API keys and secrets out of source control.
