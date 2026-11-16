# All-account automatic KIS order reconciliation

This change provides code and isolated tests only. It does not run maintenance
against the operational database, submit trades, cancel broker orders, backfill
orders, reset reservations, or replay scheduler slots.

## Changed files

- `app/services/kis_automatic_order_reconciliation_service.py`: shared evidence
  validation, bounded reads, account leases, atomic updates and audit records.
- `app/db/models.py`: durable reconciliation lease/status table.
- `app/services/automation_scheduler_service.py`: all-account maintenance and
  admin pre-entry/post-submit integration.
- `app/services/automation_profile_buy_scheduler_service.py`: guarded admin
  scheduler integration and post-submit sync adapter.
- `app/services/user_auto_trading_scheduler_service.py`: owned pre-entry check.
- `app/services/user_trading_execution_service.py`: read-only post-submit check.
- `app/services/user_risk_state_service.py`: preserve partial terminal fills in
  daily trade accounting.
- `app/routes/kis.py`, `app/routes/user_trading.py`: authenticated status GETs.
- `app/services/automation_today_decision_service.py`: current account status in
  the existing today feed.
- `lib/models/automation_today_decisions.dart`: optional reconciliation status.
- `lib/features/dashboard/widgets/kis_order_reconciliation_status.dart` and
  `home_latest_ai_decision_card.dart`: current sync health and readable reasons.
- `app/tests/test_kis_automatic_order_reconciliation.py`: Fake KIS regressions.
- `app/tests/integration/test_pr138_order14_reconciliation.py`: retain stale-plan
  rejection when automatic sync advances the order's audit metadata, then
  revalidate the manual plan against the current row.
- `test/kis_order_reconciliation_status_test.dart`: Flutter model/widget tests.

Changes already present in the today-decision service, model/card and their
existing tests when this task started were preserved.

## Structure and scope

`KisAutomaticOrderReconciliationService` discovers unresolved KIS orders and
reconciles each account independently. It reuses `kis_order_account_scope`,
`KisOrderSyncService` field mapping, `kis_order_mapper`, and the existing
header-preserving execution history readers on admin and user clients.
`AutomaticKisOrderSyncService` supplies the existing post-submit sync interface.

Admin orders keep NULL ownership. The scope resolver verifies the sole admin
and allows profiles owned by that admin's ID (including ID 1) or legacy NULL.
Regular accounts use their exact owner ID and encrypted KIS credentials; there
is no environment-credential fallback. Client credentials, account/product,
environment, owner metadata, and profile ownership must agree. Explicit order
environment/account metadata, when present, must agree as well. Missing or
mismatched credentials fail closed and produce fixed diagnostic codes.

`KisOrderReconciliationState` is a new table created by normal application
schema initialization; no existing order rows need a migration/backfill. Its
atomic lease prevents overlapping reconciliation workers for an account,
including separate server processes. Order updates also compare the original
status, quantities, identifiers, ownership, submission time and sync timestamp.
Changed or expired-lease rows are not overwritten. Updates and their
`TradeRunLog` audit records commit in the same transaction.

## Required evidence

All pages of the exact KST order day must complete successfully. Requests read
all execution states, both directions and all exchanges. Continuation headers,
cursors, page shapes, account fields and bounded read budgets are verified by
the existing history reader. Missing/repeated cursors, unknown flags, page caps,
timeouts and later-page errors invalidate the entire day's evidence.

A match must uniquely verify order number, date, symbol, direction and requested
quantity. Quantities must be finite nonnegative whole shares; known cumulative
fills cannot decrease. Fills require a positive finite average price. Current
holdings and absence from an open-order list never establish a terminal order.

- Full fill with zero remaining: FILLED.
- Explicit cancellation, rejection of the remainder, or expiration with zero
  remaining: CANCELED, REJECTED or EXPIRED; partial fills remain recorded.
- Verified active remainder: PENDING or PARTIALLY_FILLED.
- Missing order number/record, ambiguous identity, conflicting quantities,
  unsupported date range, incomplete reads or API errors: keep the existing
  unresolved status and record review/retry metadata.

The automatic path supports order days strictly inside the recent three-month
history window. Older/boundary days stay unresolved with
`history_date_out_of_supported_range`; they are not silently interpreted using
the recent-history endpoint. KIS documents separate recent/older transaction
IDs and continuation handling in its [official inquiry example](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_daily_ccld/inquire_daily_ccld.py).

Submission and fill timestamps are preserved. Historical fills are counted on
their original day. A partial fill that ends CANCELED/REJECTED still consumes
the user's daily trade allowance. Reconciliation does not reset execution
claims, reservations or position lifecycles; existing position management and
its current-account evidence remain authoritative. Terminalizing an order
alone cannot reset its original slot's idempotency claim.

## Execution and limits

The canonical scheduler's existing maintenance lane starts on its first dispatch
after server startup and continues outside market hours, including before open.
It uses the same service as both account types' pre-entry slot checks. Existing
post-submit synchronization also uses this orchestration; a newly acknowledged
order can receive its first read during the account interval, but cannot bypass
the account lease. Reconciliation never invokes an entry callback.

Each account pass examines at most 20 orders, caching complete history per day,
with at most 12 broker requests, a 20-second read budget, and a minimum one-second
request interval. The lease lasts 90 seconds and is checked again before each
write. Background discovery considers up to 20 accounts, oldest check first,
and stops starting accounts after 30 seconds. Deferred accounts remain eligible
in following maintenance passes. Successful account passes wait 60 seconds;
failures wait 30, 120, then 600 seconds. After three failed passes the background
lane stops retrying that account for the KST day. A subsequent regular slot can
recheck after the account interval. All unresolved-order trading guards remain.

## Read-only API and UI

- `GET /kis/orders/reconciliation-status`: authenticated admin, legacy scope.
- `GET /users/me/trading/order-reconciliation`: authenticated regular user only.
- Existing today-decision responses include `order_reconciliation` for KIS.

Responses expose the last check in KST, checked/finalized/unresolved/manual-review
counts, next attempt and a fixed failure reason. Flutter shows current sync
health separately from historical slot outcomes, translates failure messages,
and removes current warnings once unresolved orders clear. Status reads make
no broker requests and do not create state rows. Logs and responses exclude
credentials, tokens and raw account identifiers.

The write-capable `reconcile_account`/`reconcile_all` methods are not dry-run
interfaces. For operational previews, use an explicitly read-only database
connection and the existing GET readers with the pure `verified_mapping`
function. Authentication must use memory-only token storage. Never start or
restart the server merely to inspect these hooks against an operating database.

## Incident orders #19 and #20

The reported November 4 and November 9 dates fall within the supported window
on November 16, 2026. Either order can finalize automatically only if its own
account returns the unique, complete and explicit evidence described above.
Zero holdings, zero reported fills and absence from current open orders are
insufficient. A missing broker number or missing historical terminal record
keeps the order unresolved and the trading HOLD intact. This implementation
does not assert or change their operational status.

## Validation completed

- Complete backend collection: 3,063 tests, executed exactly once across eight
  independent pytest workers with isolated test databases. All workers exited
  successfully: **3,060 passed, 3 skipped**. Skips are existing opt-in tests for
  the operating clone/backup, which was not provided or accessed for this task.
- Final focused run: **135 passed**, including the two mandatory scheduler and
  full-lifecycle replay modules (58 tests), the new automatic reconciliation
  regressions (55), and the existing approved-repair regressions (22).
- Full Flutter suite: **843 passed**.
- Flutter static analysis on the four changed/new model, widget and test files:
  no issues.
- `python -m compileall app`: passed.
- `git diff --check`: passed.

Backend tests retain the existing external KIS transport prohibition, and new
reconciliation tests use FakeKisClient with isolated databases. No actual order
or cancellation request, operating database modification/backfill, watchlist
file change, push or PR creation was performed. Local commits are handled only
under separate, explicit user authorization.
