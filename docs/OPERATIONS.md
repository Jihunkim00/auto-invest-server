# Operations Guide

## System overview

The system has a Flutter dashboard, a FastAPI backend, and a local SQLite log database. Alpaca paper trading remains available for US-market legacy flows. KIS connects to a Korean broker account for KR portfolio, order, watchlist, and guarded automation flows.

Manual deposits and withdrawals happen outside this system in the broker account. The server executes orders after backend gates pass. Flutter is only the dashboard and control surface; the backend remains the source of truth.

## KIS safety model

Live KIS behavior is controlled by layered gates:

- `DRY_RUN=true` blocks live order execution.
- `KILL_SWITCH=true` blocks automation and live submit paths.
- `KIS_ENABLED=false` keeps KIS integration disabled by default.
- `KIS_REAL_ORDER_ENABLED=false` blocks real KIS orders by default.
- `KIS_LIVE_AUTO_SELL_ENABLED=false` and `KIS_LIVE_AUTO_BUY_ENABLED=false` keep live automation disabled.
- `KIS_SCHEDULER_ALLOW_REAL_ORDERS=false` keeps scheduler real orders disabled.
- `KIS_SCHEDULER_SELL_ENABLED=false` and `KIS_SCHEDULER_BUY_ENABLED=false` keep scheduler execution disabled.
- `KIS_LIMITED_AUTO_STOP_LOSS_ENABLED=false`, `KIS_LIMITED_AUTO_TAKE_PROFIT_ENABLED=false`, and `KIS_LIMITED_AUTO_BUY_ENABLED=false` keep limited execution gates closed.
- Daily limits, duplicate order checks, cash buffers, and notional caps must pass before any guarded live path can place an order.

Scheduler buy must run sell review first. Sell-ready state blocks scheduler buy. Scheduler buy and sell remain default OFF.

## Operator flows

- Watchlist: review configured US or KR symbols and candidates.
- Watchlist Analyze & Buy: run watchlist analysis and review final candidate output.
- Single Symbol Analyze & Buy: analyze one symbol and use the guarded manual path only after validation.
- Position Management: inspect KR positions and prepare manual sell actions.
- Scheduled Position Management: review scheduler readiness, dry-run orchestration, and position-management state.
- Scheduler guarded sell: sell-only guarded execution, default OFF, through existing limited auto sell gates.
- Scheduler guarded buy: buy-only guarded execution, default OFF, after sell-priority review, through existing limited auto buy gates.

## Operations readiness endpoint

Use `GET /ops/production-readiness` to answer whether the system is safe to run right now. The endpoint is read-only. It reports dry-run/live mode, kill switch state, KIS real-order state, scheduler real-order state, scheduler buy/sell flags, live auto buy/sell flags, today order counts, broker submit counts, safety violations, KR watchlist validity, DB writability, docs/config presence, and recommended next actions.

It must not create orders or submit to a broker.

## Emergency procedure

1. Enable `KILL_SWITCH=true`.
2. Disable scheduler.
3. Disable KIS real orders.
4. Disable live auto buy and live auto sell.
5. Check the KIS broker account directly.
6. Liquidate or cancel manually through the broker if needed.
7. Inspect order logs, run logs, and recent readiness reports.
8. Restart the backend only after root cause is known.

## Environment notes

Keep `DEFAULT_SYMBOL=AAPL` for legacy Alpaca compatibility. Use `DEFAULT_US_SYMBOL=AAPL` for US defaults and `DEFAULT_KR_SYMBOL=005930` for KR defaults. Korean symbols must be strings so leading zeroes are preserved.

Never commit real secrets. `.env.example` contains placeholder values only.
