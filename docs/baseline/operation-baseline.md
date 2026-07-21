# Operation Baseline

Generated at: 2026-07-21T20:40:13+09:00

Baseline source branch: `main`

PR working branch: `pr101-operation-baseline-snapshot`

Baseline commit SHA: `26ab08fbba17fbf6000b939705f348a0b4fde904`

This baseline freezes the current operating shape of the auto-invest system for
later Operation Mode, Flutter UI, and Agent Chat refactors. It is a read-only
snapshot. It does not change trading strategy, risk logic, scheduler behavior,
broker submit paths, DB migrations, or Flutter UI behavior.

## Stack

Backend:

- Python FastAPI application in `app/main.py`
- SQLAlchemy models in `app/db/models.py`
- SQLite-compatible initialization and lightweight migrations in `app/db/init_db.py`
- Pydantic settings in `app/config.py`

Flutter:

- Flutter app in `lib/app.dart`
- Material navigation using `IndexedStack`
- Shared state in `DashboardController`
- Backend calls through `lib/core/network/api_client.dart`

## Brokers And Markets

- Default provider: Alpaca
- Supported providers in current code: Alpaca and KIS
- Supported markets in current UI/API surface: US and KR
- KIS manual submit path: `app/services/kis_manual_order_service.py`
- Agent Chat live order path: `app/services/agent_chat_live_order_service.py`
- Alpaca broker path: `app/brokers/alpaca_broker.py`

## Runtime Defaults

The current runtime defaults are conservative:

- `dry_run`: `true`
- `kill_switch`: `false`
- `scheduler_enabled`: `false`
- `automation_mode`: `off`
- `kis_scheduler_enabled`: `false`
- `kis_scheduler_dry_run`: `true`
- `kis_scheduler_allow_real_orders`: `false`
- `kis_scheduler_buy_enabled`: `false`
- `kis_scheduler_sell_enabled`: `false`
- `agent_chat_live_order_enabled`: `false`
- `agent_chat_live_order_requires_confirm`: `true`
- `agent_chat_live_order_confirm_ttl_seconds`: `120`
- `automation_release_enabled`: `false`
- `automation_release_mode`: `controlled_phase1`
- `automation_release_max_actions_per_cycle`: `1`
- `automation_release_max_daily_auto_actions`: `2`
- `automation_release_max_daily_auto_buys`: `1`
- `automation_release_max_daily_auto_sells`: `1`
- `portfolio_orchestrator_enabled`: `false`
- `portfolio_orchestrator_max_actions_per_run`: `1`
- `broker_sync_watchdog_block_automation_on_unsafe`: `true`

See `operation-baseline.json` for the structured snapshot.

## Scheduler

The global scheduler status endpoint is `GET /scheduler/status`. It combines
runtime settings with market session configuration from `config/market_sessions.yaml`.

Current scheduler guardrails:

- US scheduler is derived from global scheduler state and US market session config.
- KR/KIS scheduler additionally depends on KIS runtime flags.
- KR new buy entries use `kr_no_new_entry_after`, currently `14:50` KST.
- Strategy auto-buy scheduler uses `strategy_auto_buy_scheduler_no_new_entry_after`,
  currently `15:00` KST.
- Default KIS scheduler state is disabled and dry-run only.

## Portfolio Orchestrator

The portfolio orchestrator endpoint is `GET /automation/portfolio/latest` and
the run endpoint is `POST /automation/portfolio/run-once`.

Current structure:

- Disabled by default.
- Positions-first by default.
- At most one selected action per run.
- Live orders require the separate orchestrator live-order flag and existing
  runtime live gates.
- Broker sync watchdog and production readiness are checked before controlled
  live execution.

## Order Submit Conditions

KIS manual order submit requires:

- KR market and 6-digit KR symbol
- `dry_run=false` in request and runtime settings
- `confirm_live=true`
- kill switch off
- KIS integration and real-order capability enabled in app settings
- KR trading profile enabled
- market open, and buy entry window still allowed for buys
- recent successful KIS validation within the existing TTL
- quantity and notional caps
- daily KIS trade limit available
- exact manual confirmation phrase

Agent Chat live order confirm additionally requires:

- a prepared `AgentChatOrderAction`
- unexpired confirmation window
- matching confirmation phrase or scope hash
- Agent Chat live order flags enabled
- no duplicate open order for the same KIS symbol and side
- validation and target-aware risk gates passing before submit

## API Contracts

The structured API contract snapshot is `openapi-baseline.json`. The minimum
baseline endpoint groups are:

- Operations: `GET /ops/settings`, `GET /automation/mode/status`,
  `GET /automation/release/status`, `GET /scheduler/status`,
  `GET /kis/scheduler/status`
- Accounts and portfolio: `GET /kis/account/balance`,
  `GET /kis/account/positions`, `GET /kis/account/open-orders`,
  `GET /portfolio/summary`, `GET /automation/portfolio/latest`
- Analysis: `POST /market-analysis/run`, `POST /market-analysis/watchlist`,
  `POST /trading/run-watchlist-once`, `POST /kis/trading/run-once`
- Orders: `POST /kis/orders/validate`, `POST /kis/orders/manual-submit`,
  `POST /kis/orders/sync-open`,
  `POST /agent/chat/live-orders/{action_id}/confirm`,
  `POST /agent/chat/live-orders/{action_id}/cancel`
- Logs: `GET /runs/recent`, `GET /orders/recent`, `GET /signals/recent`,
  `GET /logs/summary`
- Agent Chat: `POST /agent/chat/send`, `GET /agent/chat/conversations`,
  `GET /agent/chat/conversations/{conversation_key}/messages`,
  `GET /agent/chat/live-orders/readiness`, `GET /agent/operations/summary`

## Database

The database schema snapshot is `database-schema.json`. It records 28
SQLAlchemy metadata tables, including runtime settings, orders, signals, run
logs, Agent Chat conversations/messages/order actions, agent plans/runs,
schedules, approval requests, and review queue state.

Columns that can contain operator text, request/response payloads, or credential
storage are marked with `possibly_sensitive`.

## Agent Chat Scope

Current Agent Chat scope includes:

- general send endpoint
- conversation creation, list, detail, messages, archive, and clear
- command parsing and agent plan creation/run flows
- operations summary and review queue
- live order readiness, recent actions, confirm, cancel, and sync
- strategy action confirm/cancel

Agent Chat must not bypass backend validation, confirmation, runtime gates, or
existing submit services.

## Safety Invariants

Future PRs must preserve these invariants unless the PR explicitly updates this
baseline:

- Runtime defaults remain live-disabled.
- No strategy/risk/scheduler submit behavior changes in baseline-only work.
- Manual KIS submit requires validation, explicit confirmation, and all runtime gates.
- Agent Chat prepare never submits an order.
- Agent Chat confirm cannot bypass confirmation, TTL, validation, duplicate-order,
  daily-limit, or runtime checks.
- `dry_run=true` blocks live submit.
- `kill_switch=true` blocks new live orders.
- Scheduler dry-run paths do not call broker submit.
- Strategy auto-buy scheduler remains dry-run/promotion-only unless explicitly changed.
- Automation release live cycle is blocked unless release, soak, watchdog,
  production readiness, automation mode, and operator acknowledgement gates pass.
- Baseline fixtures use synthetic symbols and values.

## Commands

Recommended verification commands:

```powershell
.venv\Scripts\python.exe -m pytest app/tests/test_operation_baseline_contract.py app/tests/test_operation_baseline_secret_scan.py app/tests/test_operation_baseline_openapi.py -q
python scripts/verify_operation_baseline.py
python -m compileall app scripts
flutter analyze
flutter test
git diff --check
```

If `.venv` is unavailable, use:

```bash
python -m pytest app/tests -q
python scripts/verify_operation_baseline.py
```
