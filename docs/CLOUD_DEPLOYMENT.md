# Cloud Deployment Prep

This guide prepares `auto-invest-server` for a future VPS or cloud server
without changing trading behavior. Start small, keep the backend private, and
verify runtime gates before enabling any live automation.

## Recommended Architecture

- Small VPS first: 1-2 vCPU, 1-2 GB RAM is enough for the FastAPI backend and
  SQLite while usage is light.
- Backend: run FastAPI with `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
- Database: use SQLite initially with an absolute `DATABASE_URL`, then migrate
  to Postgres later if concurrency, backups, or retention needs grow.
- Dashboard: the Flutter dashboard can remain local and connect over VPN, or be
  deployed separately later.
- Networking: keep the API private behind a VPN or reverse proxy with auth.

## Environment Variables

Use `.env` on the server or provider-managed secrets. Never commit `.env`.

Core runtime:

```env
APP_ENV=prod
APP_DEBUG=false
APP_VERSION=
DATABASE_URL=sqlite:////opt/auto-invest-server/data/auto_invest.db
LOG_DIR=/opt/auto-invest-server/logs
CONFIG_DIR=/opt/auto-invest-server/config
WATCHLIST_US_PATH=/opt/auto-invest-server/config/watchlist_us.yaml
WATCHLIST_KR_PATH=/opt/auto-invest-server/config/watchlist_kr.yaml
```

Alpaca credentials:

```env
ALPACA_API_KEY=
ALPACA_SECRET_KEY=
ALPACA_BASE_URL=https://paper-api.alpaca.markets
```

KIS credentials and gates:

```env
KIS_ENABLED=false
KIS_ENV=paper
KIS_APP_KEY=
KIS_APP_SECRET=
KIS_ACCOUNT_NO=
KIS_ACCOUNT_PRODUCT_CODE=01
KIS_BASE_URL=
KIS_WS_URL=
KIS_ACCESS_TOKEN=
KIS_APPROVAL_KEY=
KIS_REAL_ORDER_ENABLED=false
KIS_TOKEN_CACHE_PATH=
```

Scheduler defaults must remain safe:

```env
DRY_RUN=true
KIS_SCHEDULER_ENABLED=false
KIS_SCHEDULER_DRY_RUN=true
KIS_SCHEDULER_LIVE_ENABLED=false
KIS_SCHEDULER_ALLOW_REAL_ORDERS=false
KIS_SCHEDULER_CONFIGURED_ALLOW_REAL_ORDERS=false
KIS_SCHEDULER_SELL_ENABLED=false
KIS_SCHEDULER_BUY_ENABLED=false
KIS_SCHEDULER_ALLOW_LIMITED_AUTO_SELL=false
KIS_SCHEDULER_ALLOW_LIMITED_AUTO_BUY=false
```

## Safe Startup Checklist

1. Set `DRY_RUN=true`.
2. Keep KIS live automation off by default.
3. Keep `KIS_REAL_ORDER_ENABLED=false` unless intentionally preparing a guarded
   live test.
4. Set the runtime kill switch through `/ops/settings` as desired. For maximum
   safety use `kill_switch=true`; for dry-run rehearsal `kill_switch=false` is
   acceptable because live order gates remain off.
5. Start the backend.
6. Verify `GET /health` returns `status: ok`.
7. Verify `GET /ready` returns `db_connected: true` and no secrets.
8. Verify `GET /scheduler/status` shows the expected US/KR effective scheduler
   state and block reasons.

## Scheduler Timezones

- US scheduler slots use `America/New_York`.
- KR scheduler slots use `Asia/Seoul`.
- Cloud server host timezone does not change slot interpretation.

## Security

- Never commit `.env`, broker keys, access tokens, or account numbers.
- Do not expose the API directly to the public internet.
- Prefer Tailscale, WireGuard, or another VPN for the first deployment.
- If a public endpoint is later required, put it behind a reverse proxy with
  HTTPS and authentication.
- Use a host firewall that only opens SSH and the private/VPN-facing API port.
- Rotate broker credentials if they were ever printed, shared, or committed.

## Future Production Path

- Run under `systemd` with automatic restart and structured logs.
- Add Docker once the runtime paths and data volume layout are stable.
- Move from SQLite to Postgres when concurrent writes, retention, or managed
  backups become important.
- Put the API behind Nginx/Caddy with HTTPS and authentication.
- Add uptime checks, log alerts, disk-space alerts, and scheduler run alerts.
