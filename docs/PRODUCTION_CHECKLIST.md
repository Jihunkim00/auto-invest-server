# Production Checklist

## Pre-flight checks

- Verify the database is writable.
- Verify the KR watchlist has exactly 50 symbols.
- Verify KR watchlist symbols include `005930` and `035420`.
- Verify KIS credentials are present in `.env`, not in source control.
- Verify dry-run mode first with `DRY_RUN=true`.
- Verify kill switch behavior.
- Verify scheduler status and next slot.
- Verify daily order limits.
- Verify logs, run history, and order history.
- Verify there are no stale or unresolved open orders.
- Verify the broker account directly before live operation.
- Review `GET /ops/production-readiness`.

## Live-order checklist

- Never enable all live flags at once.
- Start with dry-run.
- Move to sell-only first.
- Keep scheduler buy disabled initially.
- Use small notional.
- Keep daily order limits low.
- Confirm broker submit logs.
- Confirm the order appears in the broker account.
- Disable immediately if any mismatch appears.

## Recommended live rollout

1. Keep `DRY_RUN=true` and run scheduler dry-run orchestration.
2. Review guarded sell and guarded buy audits.
3. Confirm KIS credentials and broker account manually.
4. Set daily order limits to the smallest practical value.
5. Enable live sell gates only after dry-run evidence is clean.
6. Keep scheduler buy disabled until sell behavior is verified.
7. Enable scheduler buy only with explicit operator approval and small notional.

## Emergency procedure

1. Enable `KILL_SWITCH=true`.
2. Disable scheduler.
3. Set `KIS_REAL_ORDER_ENABLED=false`.
4. Set live auto buy and live auto sell flags to false.
5. Check the broker account directly.
6. Cancel or liquidate manually through the broker if needed.
7. Inspect logs, orders, and runs.
8. Restart the backend only after root cause is known.

## Environment variables

Safe defaults:

- `DEFAULT_SYMBOL=AAPL`
- `DEFAULT_US_SYMBOL=AAPL`
- `DEFAULT_KR_SYMBOL=005930`
- `DRY_RUN=true`
- `KILL_SWITCH=false`
- `KIS_ENABLED=false`
- `KIS_REAL_ORDER_ENABLED=false`
- `KIS_LIVE_AUTO_SELL_ENABLED=false`
- `KIS_LIVE_AUTO_BUY_ENABLED=false`
- `KIS_SCHEDULER_ALLOW_REAL_ORDERS=false`
- `KIS_SCHEDULER_SELL_ENABLED=false`
- `KIS_SCHEDULER_BUY_ENABLED=false`

Korean symbols must be strings to preserve leading zeroes.
