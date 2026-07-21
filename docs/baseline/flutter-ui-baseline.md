# Flutter UI Baseline

Generated at: 2026-07-21T20:40:13+09:00

Baseline commit SHA: `26ab08fbba17fbf6000b939705f348a0b4fde904`

This document records the current Flutter UI structure without changing any
widgets, strings, navigation, or API calls.

## App Shell

Source: `lib/app.dart`

The app uses `MaterialApp`, dark theme, a single `DashboardController`, and an
`IndexedStack` with bottom `NavigationBar` destinations:

- Home
- Watchlist
- Analysis
- Trading
- Logs
- Settings
- KIS Automation

The `DashboardController` in `lib/features/dashboard/dashboard_controller.dart`
owns screen state, loading/error flags, selected broker/market context, Agent
Chat state, automation state, and order ticket state.

All backend calls flow through `lib/core/network/api_client.dart`.

## Home

Source: `lib/features/dashboard/dashboard_screen.dart`

Purpose:

- compact operational overview
- Agent Chat access
- safety status
- portfolio summary
- recent trades/activity
- expandable advanced details

Major cards:

- `AgentChatPanel`
- compact safety status bar
- compact portfolio summary card
- recent trades card
- operational readiness card
- strategy profile, risk, dry-run auto buy, live auto buy, live auto exit cards
- automation runtime monitor
- agent operations and review queue cards

Key actions:

- open manual order tab
- open logs
- open settings
- refresh dashboard
- run/refresh strategy and automation panels through controller methods

Connected endpoints include:

- `POST /agent/chat/send`
- `GET /agent/chat/live-orders/readiness`
- `GET /ops/settings`
- `GET /scheduler/status`
- `GET /portfolio/summary`
- `GET /kis/account/balance`
- `GET /kis/account/positions`
- `GET /kis/account/open-orders`
- `GET /runs/recent`
- `GET /orders/recent`
- `GET /signals/recent`

Safety language visible to users includes dry-run state, kill switch state,
real-order state, market state, live buy armed state, live sell armed state, and
manual confirmation warnings.

## Watchlist

Source: `lib/features/dashboard/watchlist_screen.dart`

Purpose:

- show selected market watchlist context
- preview/analyze candidates
- route selected candidate into manual Trading review

Connected endpoints include:

- `GET /market-profiles/{market}/watchlist`
- `POST /trading/run-watchlist-once`
- `GET /trading/watchlist/latest`
- `POST /kis/watchlist/preview`
- `GET /kis/watchlist/kosdaq-top50/preview`
- `POST /kis/watchlist/kosdaq-top50/update`

Actions that must remain guarded:

- watchlist review can prepare manual context only
- no watchlist click should submit a broker order

## Analysis

Source: `lib/features/analysis/analysis_screen.dart`

Purpose:

- run market and candidate analysis
- show scores, GPT risk context, final candidate details
- let operator move to Trading for manual review

Connected endpoints include:

- `POST /market-analysis/run`
- `POST /market-analysis/watchlist`
- `POST /market-analysis/refresh-context`
- `GET /market-analysis`

Actions that must remain guarded:

- analysis results are advisory
- live order submit remains outside the Analysis screen

## Trading

Source: `lib/features/dashboard/manual_order_screen.dart`

Purpose:

- manual order review and KIS validation flow
- KIS order history, sync, and cancel controls
- manual live submit only after explicit operator confirmation and backend gates

Major controls:

- broker/market context controls
- symbol/side/quantity ticket inputs
- KIS validation button
- manual submit button gated by confirmation
- KIS order sync/cancel actions

Connected endpoints include:

- `GET /kis/manual-order/status`
- `POST /kis/orders/validate`
- `POST /kis/orders/manual-submit`
- `GET /kis/orders`
- `GET /kis/orders/summary`
- `GET /kis/orders/{order_id}`
- `POST /kis/orders/{order_id}/sync`
- `POST /kis/orders/sync-open`
- `POST /kis/orders/{order_id}/cancel`
- `POST /kis/positions/{symbol}/prepare-manual-sell`

Actions that must remain guarded:

- validation does not submit
- submit requires `confirm_live=true`, confirmation text, non-dry-run runtime,
  kill switch off, KIS real-order setting enabled, market gates, limits, and
  recent validation
- cancel/sync operate only through explicit KIS order endpoints

## Logs / History

Source: `lib/features/logs/logs_screen.dart`

Purpose:

- operations summaries
- run/order/signal timelines
- automation readiness panels
- production readiness, watchdog, soak, release, orchestrator, and review panels

Major panels:

- `OperatorAlertsPanel`
- `DailyOpsSummaryPanel`
- `ProductionReadinessPanel`
- `AutomationModeStatusPanel`
- `AutomationReleaseStatusPanel`
- `AutomationSoakTestPanel`
- `BrokerSyncWatchdogPanel`
- `PortfolioOrchestratorPanel`
- `AutoBuyOperationsPanel`
- `AutoBuyLivePhase1Panel`
- `AutoSellLivePhase1Panel`
- `PositionManagementDryRunPanel`
- `PositionExitReviewPanel`
- `PositionLifecyclePanel`
- `AutoBuySchedulerPanel`
- `AutoBuyPromotionQueuePanel`

Connected endpoints include:

- `GET /runs/recent`
- `GET /orders/recent`
- `GET /signals/recent`
- `GET /logs/summary`
- `GET /ops/daily-summary`
- `GET /ops/alerts`
- `GET /ops/production-readiness`
- `GET /automation/mode/status`
- `GET /automation/release/status`
- `GET /automation/soak/status`
- `GET /broker-sync/watchdog/status`
- `GET /automation/portfolio/latest`

Safety language visible to users includes readiness-only, live auto disabled,
no broker submit, manual approval required, blocked, dry-run, and guarded labels.

## Agent Chat

Primary widgets:

- `AgentChatPanel`
- `AgentChatFullPanel`
- `AgentChatLiveOrderConfirmationCard`
- `AgentChatLiveOrderReadinessCard`
- `AgentChatLiveOrderStatusCard`
- strategy action/result cards

Connected endpoints include:

- `POST /agent/chat/send`
- `POST /agent/chat/conversations`
- `GET /agent/chat/conversations`
- `GET /agent/chat/conversations/{conversation_key}`
- `GET /agent/chat/conversations/{conversation_key}/messages`
- `POST /agent/chat/conversations/{conversation_key}/messages`
- `POST /agent/chat/live-orders/{action_id}/confirm`
- `POST /agent/chat/live-orders/{action_id}/cancel`
- `POST /agent/chat/live-orders/{action_id}/sync`
- `GET /agent/chat/live-orders/readiness`
- `GET /agent/operations/summary`
- `GET /agent/operations/review-queue`

Actions that must remain guarded:

- Agent Chat may prepare or explain but must not bypass backend order gates
- live order confirmation must remain explicit and bounded by backend TTL
- no UI-only acknowledgement can submit without server validation

## Settings

Source: `lib/features/settings/settings_screen.dart`

Purpose:

- global safety and operation mode controls
- automation mode panel
- automation release panel
- Alpaca/US trading status
- KIS/KR trading scheduler controls
- schedule controls
- risk limits
- exit rules
- advanced diagnostics flags

Connected endpoints include:

- `GET /ops/settings`
- `PUT /ops/settings`
- `POST /ops/settings/apply-preset`
- `GET /scheduler/status`
- `GET /automation/mode/status`
- `POST /automation/mode/set`
- `POST /automation/mode/off`
- `GET /automation/release/status`
- `POST /automation/release/preflight`
- `POST /automation/release/arm`
- `POST /automation/release/disarm`
- `POST /automation/release/run-cycle-once`

Actions that must remain guarded:

- dangerous operation modes require confirmation
- release arm/run controls do not change core dry-run, kill switch, KIS real-order,
  or scheduler defaults by themselves
- US no-new-entry setting is read-only/derived in current code

## KIS Automation / Advanced Test Lab

Source: `lib/features/dashboard/test_lab_screen.dart`

Purpose:

- KIS dry-run automation, scheduler checks, readiness, live-exit preflight,
  shadow decisions, limited auto buy/sell, guarded buy/sell, and related review
  workflows

Connected endpoints include:

- `GET /kis/scheduler/status`
- `GET /kis/scheduler/readiness`
- `POST /kis/scheduler/run-dry-run-orchestration-once`
- `POST /kis/scheduler/run-dry-run-auto-once`
- `POST /kis/live-exit/preflight-once`
- `POST /kis/exit-shadow/run-once`
- `GET /kis/exit-shadow/review`
- `GET /kis/exit-shadow/review-queue`
- `POST /kis/limited-auto-buy/preflight-once`
- `POST /kis/limited-auto-buy/run-once`
- `GET /kis/limited-auto-buy/status`
- `POST /kis/limited-auto-sell/preflight-once`
- `POST /kis/limited-auto-sell/run-once`
- `GET /kis/limited-auto-sell/status`
- `POST /kis/scheduler/run-live-once`
- `POST /kis/scheduler/run-guarded-buy-once`
- `POST /kis/scheduler/run-guarded-sell-once`

Actions that must remain guarded:

- dry-run and preflight actions do not submit
- live/guarded actions remain blocked by runtime, readiness, market, and limit gates
- sell/exit evaluation is separate from buy entry cutoff logic

## Portfolio

Source: `lib/features/dashboard/portfolio_screen.dart`

Current top-level navigation does not include `PortfolioScreen` directly in
`lib/app.dart`; portfolio state is surfaced through Home, Logs panels, and
controller state.

Connected endpoints include:

- `GET /portfolio/summary`
- `GET /kis/account/balance`
- `GET /kis/account/positions`
- `GET /kis/account/open-orders`
- `GET /automation/portfolio/latest`
- `POST /automation/portfolio/run-once`

Actions that must remain guarded:

- portfolio orchestrator is disabled by default
- orchestrator is positions-first
- orchestrator may select at most one action per run
- controlled live mode requires the existing runtime live gates

## Existing Widget Test Coverage

Current Flutter tests include baseline coverage for:

- app navigation and i18n
- dashboard controller and dashboard screen
- settings screen
- logs screen and history migration
- Agent Chat panels, models, live-order cards, guardrail UI
- automation mode/release panels
- KIS scheduler, limited auto buy/sell, and live phase cards
- portfolio orchestrator panel
- production readiness and broker sync watchdog panels

If screenshot or golden generation is unavailable in a local environment, this
document and widget tests serve as the UI structure baseline.

