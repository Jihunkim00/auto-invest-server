# PR102 Operation Mode Facade Delta

This PR adds a backend-only user-facing operation mode facade on top of the
PR101 operation baseline. The PR101 snapshot files remain unchanged.

## New API

- `GET /app/operation-mode`
- `PUT /app/operation-mode`

The facade exposes three user-facing modes:

- `paper`: dry-run/paper operation; live broker paths are disabled.
- `live`: live-ready operation only after acknowledgement and existing safety
  preflight pass.
- `paused`: automated execution is stopped while read-only/sync paths remain
  governed by existing services.

## New Schema

- `OperationModeChangeRequest`
- `OperationModeStatusResponse`
- `OperationModeChangeResponse`
- `OperationModeBlockingReason`

Responses include `requested_mode`, `effective_mode`, `safety_status`,
`mode_drift_detected`, `blocking_reasons`, and an allowlisted
`underlying_state`.

## New Database Shape

Runtime settings gained additive facade metadata columns:

- `operation_mode_requested`
- `operation_mode_changed_at`
- `operation_mode_changed_by`
- `operation_mode_reason`

The PR adds `operation_mode_audits` for mode transition attempts:

- `previous_mode`
- `requested_mode`
- `effective_mode`
- `status`
- `changed_by`
- `reason`
- `acknowledged`
- `provider`
- `market`
- `blocking_reasons_json`
- `warnings_json`
- `before_state_json`
- `after_state_json`
- `created_at`

Audit snapshots are allowlisted runtime/safety fields only. Secrets, tokens,
account values, and broker credentials are not stored.

## Safety Invariants

- Existing runtime defaults remain live-disabled.
- Existing `/ops/settings`, automation mode, automation release, scheduler,
  KIS/Alpaca order APIs, Agent Chat confirmation, risk, watchdog, soak, and
  readiness APIs remain intact.
- `live` requires `acknowledged=true`.
- `live` performs a target-state preflight through the existing automation
  release status path and rejects with HTTP 409 on blockers.
- `live` does not start a scheduler cycle or submit an order.
- `paper` disables live order/runtime flags and keeps the kill switch value.
- `paused` stops automated execution flags and keeps global `dry_run` and
  `kill_switch` values.
- Mode changes are committed with an audit record in one transaction.
- Blocked `live` attempts roll back runtime changes and record a blocked audit.
- Flutter files are not changed in this PR.

## Existing Contract

This is an additive backend contract. PR101 `operation-baseline.json`,
`database-schema.json`, and `openapi-baseline.json` are intentionally preserved
as the frozen baseline snapshot.
