# Database Schema Baseline

Generated at: 2026-07-21T20:40:13+09:00

Baseline commit SHA: `26ab08fbba17fbf6000b939705f348a0b4fde904`

Structured schema file: `database-schema.json`

This snapshot is generated from SQLAlchemy `Base.metadata` without running DB
migrations or changing the application database.

## Scope

The baseline records:

- table name
- column name
- SQLAlchemy type
- nullable flag
- default value when present
- primary-key flag
- column-level index flag
- column-level unique flag
- index definitions exposed by metadata
- foreign key metadata exposed by metadata
- `possibly_sensitive` flag for payload, operator-text, account, credential, or
  related storage columns

## Required Tables

Runtime and operation state:

- `runtime_settings`
- `orders`
- `signals`
- `trade_run_logs`
- `strategy_profiles`
- `strategy_profile_audits`
- `strategy_performance_snapshots`

Automation and strategy attempts:

- `strategy_auto_buy_promotions`
- `strategy_live_auto_buy_attempts`
- `strategy_live_auto_exit_attempts`
- `kis_order_validations`
- `kis_shadow_exit_review_queue_state`

Agent Chat and agent operations:

- `agent_chat_conversations`
- `agent_chat_messages`
- `agent_chat_order_actions`
- `agent_chat_strategy_actions`
- `agent_chat_live_order_settings_audits`
- `agent_command_logs`
- `agent_plans`
- `agent_plan_runs`
- `agent_schedule_jobs`
- `agent_review_queue_state`

Auth and broker support:

- `auth_approval_requests`
- `auth_approval_tokens`
- `broker_auth_tokens`

Market and reference data:

- `market_analysis`
- `reference_site_cache`
- `company_events`

## Key Table Notes

`runtime_settings` stores the current global, scheduler, Agent Chat, KIS,
orchestrator, soak, release, and watchdog flags. Its defaults are part of
`operation-baseline.json`.

`orders` records Alpaca/KIS order lifecycle data, including submit status,
broker identifiers, payload audit fields, sync status, and timestamps.

`signals` records analysis outcomes, GPT/quant score fields, risk flags, gate
metadata, and related order references.

`trade_run_logs` records manual, scheduler, strategy, portfolio orchestrator,
and Agent workflow runs.

`agent_chat_order_actions` records chat-confirmed live order actions, including
provider, market, symbol, side, quantity, confirmation phrase, scope hash,
status, validation/risk/request/response payloads, and linked order IDs.

`agent_plans`, `auth_approval_requests`, `auth_approval_tokens`, and
`agent_plan_runs` record the plan/review/auth/run path for agent operations.

## Sensitive Column Rule

Columns are marked `possibly_sensitive` when their names indicate that values
may include credentials, account identifiers, user messages, request payloads,
response payloads, error text, or raw broker/service content. The baseline
records column names and metadata only; it does not store production row values.

Examples of sensitive categories:

- broker auth storage
- auth approval records
- request and response payload columns
- message text and error text columns
- account or broker identifier fields

## No Migration Change

This PR does not change `app/db/init_db.py`, SQLAlchemy models, migration
defaults, or existing DB columns. If a future PR changes table/column shape, it
must update `database-schema.json`, this document, and the baseline verification
tests in the same PR.

