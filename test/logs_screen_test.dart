import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/core/utils/timestamp_formatter.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/logs/logs_screen.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_safety_status.dart';
import 'package:auto_invest_dashboard/models/kis_scheduler_simulation.dart';
import 'package:auto_invest_dashboard/models/log_items.dart';
import 'package:auto_invest_dashboard/models/strategy_auto_buy_operations.dart';

import 'auto_buy_operations_model_test.dart';

void main() {
  testWidgets('Logs screen shows backend activity source and safety labels',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 5200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller =
        DashboardController(_FakeLogsApiClient(), autoload: false);

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: LogsScreen(controller: controller)),
    ));
    await tester.pumpAndSettle();

    expect(find.text('ALPACA PAPER'), findsOneWidget);
    expect(find.text('KIS PREVIEW'), findsOneWidget);
    expect(find.text('KIS DRY-RUN AUTO'), findsOneWidget);
    expect(find.text('PREVIEW ONLY'), findsOneWidget);
    expect(find.text('SIMULATED'), findsOneWidget);
    expect(find.text('NO BROKER SUBMIT'), findsWidgets);
    expect(find.text('Activity Timeline'), findsOneWidget);
    expect(find.text('preview_only=true'), findsNothing);
    await _expandAdvancedDetails(tester);
    expect(find.text('preview_only=true'), findsNothing);
    expect(find.text('Preview only'), findsOneWidget);
    expect(find.text('Real order submitted'), findsWidgets);
    expect(find.text('Broker submit'), findsWidgets);
    expect(find.text('Manual submit'), findsOneWidget);
    expect(find.text('05-08 00:00 (KST 09:00)'), findsOneWidget);

    await tester.tap(find.text('Orders').last);
    await tester.pumpAndSettle();
    await _expandAdvancedDetails(tester);

    expect(find.text('\u20A99,801'), findsOneWidget);
    expect(find.text('\u20A972,000'), findsOneWidget);
    expect(find.text(r'$123.45'), findsOneWidget);
    expect(find.text(r'$9,801.00'), findsNothing);
    expect(find.text(r'$72,000.00'), findsNothing);
    expect(find.text('KIS MANUAL LIVE'), findsOneWidget);
    expect(find.text('KIS DRY-RUN AUTO'), findsOneWidget);
    expect(find.text('REAL ORDER SUBMITTED'), findsOneWidget);
    expect(find.text('MANUAL ONLY'), findsOneWidget);
    expect(find.text('SIMULATED'), findsOneWidget);
    expect(find.text('NO BROKER SUBMIT'), findsWidgets);
    expect(find.text('Real order submitted'), findsWidgets);
    expect(find.text('Broker submit'), findsWidgets);
    expect(find.text('Manual submit'), findsWidgets);
    expect(find.text('05-08 00:03 (KST 09:03)'), findsOneWidget);
    expect(find.text('05-08 00:04 (KST 09:04)'), findsOneWidget);

    await tester.tap(find.text('Signals').last);
    await tester.pumpAndSettle();
    await _expandAdvancedDetails(tester);

    expect(find.text('05-08 00:05 (KST 09:05)'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('Logs screen renders KIS watchlist operator summary read-only',
      (tester) async {
    final controller = DashboardController(
      _FakeLogsApiClient(
        orders: const [],
        signals: const [],
        runs: [
          TradingLogItem.fromJson({
            'id': 18,
            'run_key': 'kis-preview-summary',
            'provider': 'kis',
            'market': 'KR',
            'symbol': 'WATCHLIST',
            'trigger_source': 'manual_kis_preview',
            'mode': 'kis_watchlist_preview',
            'action': 'hold',
            'result': 'preview_only',
            'reason': 'kr_trading_disabled',
            'gate_level': 2,
            'created_at': '2026-05-08T00:01:00',
            'dry_run': true,
            'preview_only': true,
            'real_order_submitted': false,
            'broker_submit_called': false,
            'manual_submit_called': false,
            'operator_summary': {
              'mode': 'kis_watchlist_gpt_operator_summary',
              'preview_only': true,
              'trading_enabled': false,
              'real_order_submitted': false,
              'broker_submit_called': false,
              'manual_submit_called': false,
              'completed_gpt_count': 5,
              'failed_count': 1,
              'not_run_count': 44,
              'top_gpt_candidates': [
                {
                  'rank': 1,
                  'symbol': '005930',
                  'name': 'Samsung Electronics',
                  'final_buy_score': 64,
                  'main_risk_flags': ['preview_only'],
                  'why_hold':
                      'KIS watchlist preview is advisory-only and KR trading is disabled.',
                  'why_not_buy': ['preview_only', 'kr_trading_disabled'],
                  'next_manual_action_hint':
                      'Open Trading, run KIS Analyze & Buy, validate manually, then confirm live only if all safety gates pass.',
                },
              ],
              'best_candidate': {
                'rank': 1,
                'symbol': '005930',
                'name': 'Samsung Electronics',
                'final_buy_score': 64,
                'main_risk_flags': ['preview_only'],
                'why_hold':
                    'KIS watchlist preview is advisory-only and KR trading is disabled.',
                'why_not_buy': ['preview_only', 'kr_trading_disabled'],
                'next_manual_action_hint':
                    'Open Trading, run KIS Analyze & Buy, validate manually, then confirm live only if all safety gates pass.',
              },
              'top_risk_flags': ['preview_only', 'kr_trading_disabled'],
              'top_gating_notes': ['No real KIS order submitted.'],
              'conservative_decision_summary':
                  '005930 is the current preview leader; this is advisory-only.',
              'next_manual_action_hint':
                  'review_top_gpt_candidates_in_trading_tab',
            },
          }),
        ],
      ),
      autoload: false,
    );

    await _pumpLogs(tester, controller);

    expect(find.text('KIS Watchlist Operator Summary'), findsOneWidget);
    expect(find.text('KIS WATCHLIST PREVIEW'), findsWidgets);
    expect(find.text('OPERATOR REVIEW'), findsWidgets);
    expect(find.text('PREVIEW ONLY'), findsWidgets);
    expect(find.text('NO ORDER SUBMIT'), findsWidgets);
    expect(find.text('GPT TOP 5'), findsWidgets);
    expect(find.text('GPT PARTIAL'), findsOneWidget);
    expect(find.text('Completed GPT'), findsOneWidget);
    expect(find.text('Failed GPT'), findsOneWidget);
    expect(find.text('Not Run'), findsOneWidget);
    expect(find.text('005930 Samsung Electronics | Score 64'), findsOneWidget);
    expect(find.text('Conservative Decision'), findsOneWidget);
    expect(find.text('Why Hold'), findsOneWidget);
    expect(find.text('Why Not Buy'), findsOneWidget);
    expect(find.text('Next Manual Action'), findsOneWidget);
    expect(
      find.textContaining(
          'validate manually, then confirm live only if all safety gates pass'),
      findsWidgets,
    );
    expect(find.text('Submit Live Order'), findsNothing);

    controller.dispose();
  });

  testWidgets('Logs screen renders Single Symbol Analyze & Buy runs readably',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 2600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = DashboardController(
      _FakeLogsApiClient(
        orders: const [],
        signals: const [],
        runs: [
          TradingLogItem.fromJson({
            'id': 25,
            'run_key': 'kis-single-005930',
            'provider': 'kis',
            'market': 'KR',
            'symbol': '005930',
            'trigger_source': 'manual_kis_single_symbol',
            'mode': 'kis_single_symbol_analyze_buy',
            'source': 'kis_single_symbol_analyze_buy',
            'action': 'hold',
            'result': 'blocked',
            'reason': 'buy_entry_not_allowed_now',
            'final_buy_score': 37,
            'effective_min_entry_score': 65,
            'broker_submit_called': false,
            'manual_submit_called': false,
            'real_order_submitted': false,
            'gating_notes': ['after_no_new_entry_time'],
            'created_at': '2026-05-08T00:06:00',
          }),
        ],
      ),
      autoload: false,
    );

    await _pumpLogs(tester, controller);

    expect(
      find.text('Single Symbol Analyze & Buy \u00B7 005930'),
      findsOneWidget,
    );
    expect(find.text('Blocked \u00B7 No order created'), findsOneWidget);
    expect(find.text('Reason: New buy entries are blocked after 15:00'),
        findsOneWidget);
    expect(find.text('Buy Score: 37 / Required 65'), findsOneWidget);
    expect(find.text('Broker submit: No'), findsOneWidget);
    expect(find.textContaining('broker_submit_called=false'), findsNothing);
    expect(find.textContaining('buy_entry_not_allowed_now'), findsNothing);

    controller.dispose();
  });

  testWidgets('Logs screen shows KIS live order audit details', (tester) async {
    final controller = DashboardController(
      _FakeLogsApiClient(
        runs: const [],
        signals: const [],
        orders: [
          OrderLogItem.fromJson({
            'id': 41,
            'order_id': 41,
            'provider': 'kis',
            'broker': 'kis',
            'market': 'KR',
            'mode': 'manual_live_order',
            'trigger_source': 'manual',
            'symbol': '005930',
            'side': 'buy',
            'action': 'buy',
            'result': 'SUBMITTED',
            'reason': 'Live KIS order submitted.',
            'qty': 1,
            'notional': 72000,
            'internal_status': 'SUBMITTED',
            'broker_order_status': 'submitted',
            'kis_odno': '0001234567',
            'created_at': '2026-05-08T00:03:00',
            'updated_at': '2026-05-08T00:04:00',
            'real_order_submitted': true,
            'broker_submit_called': true,
            'manual_submit_called': true,
            'audit_metadata': {
              'source_context': 'direct_manual_ticket',
              'order_source': 'manual_live_order',
              'operator_action_source': 'manual_ticket_submit',
              'symbol': '005930',
              'company_name': 'Samsung Electronics',
              'side': 'buy',
              'qty': 1,
              'estimated_price': 72000,
              'estimated_notional': 72000,
              'available_cash': 100000,
              'current_operation_mode': 'kis_sell_only',
              'dry_run': false,
              'kill_switch': false,
              'kis_enabled': true,
              'kis_real_order_enabled': true,
              'market_open': true,
              'entry_allowed_now': true,
              'daily_live_order_remaining': 2,
              'warning_level': 'dangerous_mixed',
              'validation_age_seconds': 42,
              'validation_stale': false,
              'confirmation_dialog_shown': true,
              'user_confirmed_live_order': true,
              'broker_submit_called': true,
              'real_order_submitted': true,
              'manual_submit_called': true,
              'risk_flags': ['manual_live_order'],
              'gating_notes': ['validated_recently'],
            },
          }),
        ],
      ),
      autoload: false,
    );

    await _pumpLogs(tester, controller);
    await tester.tap(find.text('Orders').last);
    await tester.pumpAndSettle();

    expect(find.text('Live Order Audit'), findsOneWidget);
    expect(find.text('direct_manual_ticket'), findsOneWidget);
    expect(find.text('OPERATOR CONFIRMED'), findsWidgets);
    expect(find.text('dangerous_mixed'), findsOneWidget);
    expect(find.text('42s'), findsOneWidget);
    expect(find.text('\u20A972,000'), findsOneWidget);
    expect(find.text('Samsung Electronics'), findsNothing);
    expect(find.text('005930 (Samsung Electronics)'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('Logs screen badges blocked audit with no broker submit',
      (tester) async {
    final controller = DashboardController(
      _FakeLogsApiClient(
        runs: const [],
        signals: const [],
        orders: [
          OrderLogItem.fromJson({
            'id': 42,
            'order_id': 42,
            'provider': 'kis',
            'broker': 'kis',
            'market': 'KR',
            'mode': 'manual_live_order',
            'trigger_source': 'manual',
            'symbol': '005930',
            'side': 'buy',
            'action': 'buy',
            'result': 'REJECTED_BY_SAFETY_GATE',
            'reason': 'Validation expired.',
            'qty': 1,
            'notional': 72000,
            'internal_status': 'REJECTED_BY_SAFETY_GATE',
            'created_at': '2026-05-08T00:03:00',
            'updated_at': '2026-05-08T00:04:00',
            'real_order_submitted': false,
            'broker_submit_called': false,
            'manual_submit_called': false,
            'audit_metadata': {
              'source_context': 'watchlist_analyze_in_trading',
              'symbol': '005930',
              'side': 'buy',
              'qty': 1,
              'estimated_notional': 72000,
              'dry_run': false,
              'kill_switch': false,
              'kis_enabled': true,
              'kis_real_order_enabled': true,
              'market_open': true,
              'entry_allowed_now': true,
              'daily_live_order_remaining': 0,
              'warning_level': 'normal',
              'validation_age_seconds': 125,
              'validation_stale': true,
              'confirmation_dialog_shown': true,
              'user_confirmed_live_order': true,
              'broker_submit_called': false,
              'real_order_submitted': false,
              'manual_submit_called': true,
              'gating_notes': ['validation_stale'],
            },
          }),
        ],
      ),
      autoload: false,
    );

    await _pumpLogs(tester, controller);
    await tester.tap(find.text('Orders').last);
    await tester.pumpAndSettle();

    expect(find.text('Live Order Audit'), findsOneWidget);
    expect(find.text('NO BROKER SUBMIT'), findsWidgets);
    expect(find.text('VALIDATION STALE'), findsWidgets);
    expect(find.text('BLOCKED'), findsWidgets);
    expect(find.text('Broker submit'), findsOneWidget);
    expect(find.text('No'), findsWidgets);

    controller.dispose();
  });

  testWidgets('Logs screen hides live audit section when audit is absent',
      (tester) async {
    final controller = DashboardController(
      _FakeLogsApiClient(
        runs: const [],
        signals: const [],
        orders: [
          _manualLiveOrder(
            orderId: 43,
            createdAt: '2026-05-08T00:03:00',
          ),
        ],
      ),
      autoload: false,
    );

    await _pumpLogs(tester, controller);
    await tester.tap(find.text('Orders').last);
    await tester.pumpAndSettle();

    expect(find.text('KIS MANUAL LIVE'), findsOneWidget);
    expect(find.text('Live Order Audit'), findsNothing);
    expect(find.text('OPERATOR CONFIRMED'), findsNothing);

    controller.dispose();
  });

  testWidgets('Logs screen shows exit preflight manual sell audit fields',
      (tester) async {
    final controller = DashboardController(
      _FakeLogsApiClient(
        runs: const [],
        signals: const [],
        orders: [
          OrderLogItem.fromJson({
            'id': 21,
            'order_id': 21,
            'provider': 'kis',
            'broker': 'kis',
            'market': 'KR',
            'mode': 'manual_live',
            'source': 'kis_live_exit_preflight',
            'source_type': 'manual_confirm_exit',
            'exit_trigger': 'stop_loss',
            'exit_trigger_source': 'cost_basis_pl_pct',
            'symbol': '005930',
            'side': 'sell',
            'action': 'sell',
            'result': 'PARTIALLY_FILLED',
            'reason': 'manual exit submit',
            'qty': 2,
            'filled_quantity': 1,
            'remaining_quantity': 1,
            'average_fill_price': 72000,
            'internal_status': 'PARTIALLY_FILLED',
            'broker_order_status': 'partial',
            'kis_odno': '0001234567',
            'created_at': '2026-05-08T00:03:00',
            'updated_at': '2026-05-08T00:04:00',
            'last_synced_at': '2026-05-08T00:05:00',
            'real_order_submitted': true,
            'broker_submit_called': true,
            'manual_submit_called': true,
            'manual_confirm_required': true,
            'auto_sell_enabled': false,
            'scheduler_real_order_enabled': false,
          }),
          OrderLogItem.fromJson({
            'id': 22,
            'order_id': 22,
            'provider': 'kis',
            'broker': 'kis',
            'market': 'KR',
            'mode': 'kis_live_exit_preflight',
            'trigger_source': 'manual_kis_live_exit_preflight',
            'source': 'kis_live_exit_preflight',
            'source_type': 'manual_confirm_exit',
            'exit_trigger': 'manual_review',
            'symbol': '005930',
            'side': 'sell',
            'action': 'sell',
            'result': 'PREFLIGHT_ONLY',
            'reason': 'manual confirmation required',
            'qty': 2,
            'internal_status': 'PREFLIGHT_ONLY',
            'created_at': '2026-05-08T00:01:00',
            'updated_at': '2026-05-08T00:01:00',
            'real_order_submitted': false,
            'broker_submit_called': false,
            'manual_submit_called': false,
            'manual_confirm_required': true,
            'auto_sell_enabled': false,
            'scheduler_real_order_enabled': false,
          }),
        ],
      ),
      autoload: false,
    );

    await _pumpLogs(tester, controller);
    await tester.tap(find.text('Orders').last);
    await tester.pumpAndSettle();
    await _expandAdvancedDetails(tester);

    expect(find.text('005930 - SELL'), findsWidgets);
    expect(find.text('KIS MANUAL LIVE'), findsOneWidget);
    expect(find.text('KIS EXIT PREFLIGHT'), findsOneWidget);
    expect(find.text('EXIT PREFLIGHT'), findsWidgets);
    expect(find.text('MANUAL SUBMIT'), findsOneWidget);
    expect(find.text('NO AUTO SELL'), findsWidgets);
    expect(find.text('SCHEDULER REAL ORDERS DISABLED'), findsWidgets);
    expect(find.text('PREFLIGHT ONLY'), findsWidgets);
    expect(find.text('NO BROKER SUBMIT'), findsWidgets);
    expect(find.text('MANUAL CONFIRMATION REQUIRED'), findsWidgets);
    expect(find.text('stop_loss'), findsOneWidget);
    expect(find.text('manual_review'), findsOneWidget);
    expect(find.text('0001234567'), findsOneWidget);
    expect(find.text('\u20A972,000'), findsOneWidget);
    expect(find.text('05-08 00:05 (KST 09:05)'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('Logs screen shows shadow exit dry-run decision fields',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 2600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = DashboardController(
      _FakeLogsApiClient(
        runs: [
          TradingLogItem.fromJson({
            'id': 31,
            'run_key': 'kis-exit-shadow',
            'provider': 'kis',
            'market': 'KR',
            'symbol': '005930',
            'trigger_source': 'shadow_exit',
            'mode': 'shadow_exit_dry_run',
            'source': 'kis_exit_shadow_decision',
            'source_type': 'dry_run_sell_simulation',
            'action': 'sell',
            'result': 'would_sell',
            'reason': 'would_sell_stop_loss',
            'gate_level': 2,
            'created_at': '2026-05-15T00:01:00',
            'dry_run': true,
            'simulated': true,
            'real_order_submitted': false,
            'broker_submit_called': false,
            'manual_submit_called': false,
            'real_order_submit_allowed': false,
            'manual_confirm_required': true,
            'auto_sell_enabled': false,
            'scheduler_real_order_enabled': false,
            'exit_trigger': 'stop_loss',
            'exit_trigger_source': 'cost_basis_pl_pct',
            'suggested_quantity': 2,
            'cost_basis': 144000,
            'current_value': 141120,
            'current_price': 70560,
            'unrealized_pl': -2880,
            'unrealized_pl_pct': -0.02,
          }),
        ],
        orders: const [],
        signals: const [],
      ),
      autoload: false,
    );

    await _pumpLogs(tester, controller);
    await _expandAdvancedDetails(tester);

    expect(find.text('KIS SHADOW EXIT'), findsOneWidget);
    expect(find.text('SHADOW EXIT'), findsOneWidget);
    expect(find.text('DRY RUN SELL SIMULATION'), findsOneWidget);
    expect(find.text('WOULD SELL'), findsOneWidget);
    expect(find.text('NO BROKER SUBMIT'), findsWidgets);
    expect(find.text('NO MANUAL SUBMIT'), findsOneWidget);
    expect(find.text('Trigger'), findsOneWidget);
    expect(find.text('stop_loss'), findsOneWidget);
    expect(find.text('Trigger src'), findsOneWidget);
    expect(find.text('cost_basis_pl_pct'), findsOneWidget);
    expect(find.text('Unrealized P/L %'), findsOneWidget);
    expect(find.text('-2.00%'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('Logs screen displays GPT context when present', (tester) async {
    final controller = DashboardController(
      _FakeLogsApiClient(
        runs: [
          TradingLogItem.fromJson({
            'id': 1,
            'run_key': 'manual_1',
            'symbol': 'AAPL',
            'trigger_source': 'manual',
            'mode': 'entry_scan',
            'action': 'hold',
            'result': 'skipped',
            'reason': 'signal action is HOLD; execution skipped',
            'created_at': '2026-05-08T00:00:00Z',
            'gate_level': 2,
            'gpt_context': {
              'market_risk_regime': 'risk_off',
              'event_risk_level': 'high',
              'entry_penalty': 6,
              'hard_block_new_buy': true,
              'risk_flags': ['fx_pressure'],
              'gating_notes': ['entry penalty observed'],
              'reason': 'External risk is elevated.',
            },
          }),
        ],
        orders: const [],
        signals: const [],
      ),
      autoload: false,
    );

    await _pumpLogs(tester, controller);
    await _expandAdvancedDetails(tester);

    expect(find.text('Event Risk high'), findsOneWidget);
    expect(find.text('Entry penalty'), findsOneWidget);
    expect(find.text('6'), findsWidgets);
    expect(find.text('New Buy Blocked'), findsOneWidget);
    expect(find.text('External risk is elevated.'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('KIS simulation summary displays latest scheduler dry-run result',
      (tester) async {
    final createdAt = _todayUtcTimestamp(kstHour: 14, minute: 35);
    final controller = DashboardController(
      _FakeLogsApiClient(
        runs: [
          _schedulerRun(
            action: 'buy',
            result: 'simulated_order_created',
            reason: 'final_score_below_min_entry cleared for dry run',
            symbol: '005930',
            orderId: 44,
            signalId: 43,
            createdAt: createdAt,
          ),
        ],
        orders: [
          _schedulerOrder(
            orderId: 44,
            side: 'buy',
            notional: 9801,
            createdAt: createdAt,
          ),
          _manualLiveOrder(orderId: 45, createdAt: createdAt),
        ],
        signals: [_schedulerSignal(id: 43, createdAt: createdAt)],
      ),
      autoload: false,
    );

    await _pumpLogs(tester, controller);

    expect(find.text('KIS Simulation Operations Summary'), findsOneWidget);
    expect(find.text('SIMULATION ONLY'), findsOneWidget);
    expect(find.text('NO BROKER SUBMIT'), findsWidgets);
    expect(find.text('NOT LIVE AUTOMATION'), findsOneWidget);
    expect(find.text(formatTimestampWithKst(createdAt)), findsWidgets);
    expect(find.text('simulated_order_created'), findsWidgets);
    expect(find.text('005930'), findsWidgets);
    expect(find.text('43'), findsWidgets);
    expect(find.text('44'), findsWidgets);
    expect(find.text('\u20A99,801'), findsOneWidget);
    expect(find.text(r'$9,801.00'), findsNothing);
    await _expandAdvancedDetails(tester);
    expect(find.text('Real order submitted'), findsWidgets);
    expect(find.text('Broker submit'), findsWidgets);
    expect(find.text('Manual submit'), findsWidgets);
    expect(find.text('real_orders_allowed=false'), findsWidgets);
    expect(find.text('Live scheduler: Disabled'), findsOneWidget);
    expect(
      find.text(
          'Manual live records are separate from scheduler simulation records.'),
      findsOneWidget,
    );

    controller.dispose();
  });

  testWidgets('KIS simulation summary shows simulated sell risk reasons',
      (tester) async {
    final stopLossTime = _todayUtcTimestamp(kstHour: 15, minute: 10);
    final takeProfitTime = _todayUtcTimestamp(kstHour: 15, minute: 20);
    final controller = DashboardController(
      _FakeLogsApiClient(
        runs: [
          _schedulerRun(
            action: 'sell',
            result: 'simulated_order_created',
            reason: 'take_profit_triggered',
            symbol: '005930',
            orderId: 52,
            signalId: 51,
            createdAt: takeProfitTime,
            riskFlags: const ['take_profit_triggered'],
          ),
          _schedulerRun(
            action: 'sell',
            result: 'simulated_order_created',
            reason: 'stop_loss_triggered',
            symbol: '000660',
            orderId: 50,
            signalId: 49,
            createdAt: stopLossTime,
            riskFlags: const ['stop_loss_triggered'],
          ),
        ],
        orders: [
          _schedulerOrder(
            orderId: 52,
            side: 'sell',
            notional: 72000,
            createdAt: takeProfitTime,
          ),
        ],
      ),
      autoload: false,
    );

    await _pumpLogs(tester, controller);

    expect(find.text('Sim sells'), findsOneWidget);
    expect(find.text('take_profit_triggered x1'), findsOneWidget);
    expect(find.text('stop_loss_triggered x1'), findsOneWidget);
    expect(find.text('\u20A972,000'), findsOneWidget);
    expect(find.text(formatTimestampWithKst(takeProfitTime)), findsWidgets);

    controller.dispose();
  });

  testWidgets('KIS simulation summary empty state displays with no KIS logs',
      (tester) async {
    final controller = DashboardController(
      _FakeLogsApiClient(
        runs: [
          TradingLogItem.fromJson({
            'id': 20,
            'run_key': 'alpaca-only',
            'provider': 'alpaca',
            'market': 'US',
            'symbol': 'AAPL',
            'trigger_source': 'manual',
            'mode': 'watchlist',
            'action': 'hold',
            'result': 'skipped',
            'reason': 'hold_signal',
            'gate_level': 2,
            'created_at': _todayUtcTimestamp(kstHour: 9),
          }),
        ],
        orders: const [],
        signals: const [],
      ),
      autoload: false,
    );

    await _pumpLogs(tester, controller);

    expect(
      find.text('No KIS scheduler simulation logs for today.'),
      findsOneWidget,
    );

    controller.dispose();
  });

  testWidgets('KIS simulation summary error state shows retry', (tester) async {
    final api = _FakeLogsApiClient(throwFetch: true);
    final controller = DashboardController(api, autoload: false);

    await _pumpLogs(tester, controller);

    expect(find.textContaining('KIS simulation summary unavailable'),
        findsOneWidget);
    expect(find.text('Retry'), findsWidgets);

    api
      ..throwFetch = false
      ..runs = [
        _schedulerRun(
          action: 'hold',
          result: 'skipped',
          reason: 'near_close_no_new_entry',
          createdAt: _todayUtcTimestamp(kstHour: 15),
        ),
      ];

    await tester.tap(find.text('Retry').first);
    await tester.pumpAndSettle();

    expect(api.fetchRecentRunsCalls, greaterThanOrEqualTo(2));
    expect(find.text('near_close_no_new_entry x1'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('KIS live automation readiness card renders blocked state',
      (tester) async {
    final createdAt = _todayUtcTimestamp(kstHour: 10, minute: 15);
    final controller = DashboardController(
      _FakeLogsApiClient(
        manualSafetyStatus: _manualSafety(
          runtimeDryRun: true,
          killSwitch: false,
          kisEnabled: true,
          kisRealOrderEnabled: true,
        ),
        schedulerStatus: const KisSchedulerSimulationStatus(
          provider: 'kis',
          market: 'KR',
          enabled: false,
          dryRun: true,
          schedulerDryRun: true,
          allowRealOrders: false,
          configuredAllowRealOrders: false,
          realOrdersAllowed: false,
          realOrderSchedulerEnabled: false,
          realOrderSubmitted: false,
          brokerSubmitCalled: false,
          manualSubmitCalled: false,
          runtimeDryRun: true,
          killSwitch: false,
        ),
        runs: [
          _schedulerRun(
            action: 'hold',
            result: 'skipped',
            reason: 'near_close_no_new_entry',
            createdAt: createdAt,
          ),
        ],
        orders: const [],
        signals: const [],
      ),
      autoload: false,
    );

    await _pumpLogs(tester, controller);

    expect(find.text('KIS Live Automation Readiness'), findsOneWidget);
    expect(find.text('LIVE AUTO ORDER: NOT ENABLED'), findsOneWidget);
    expect(find.text('READINESS ONLY'), findsOneWidget);
    expect(find.text('LIVE AUTO DISABLED'), findsOneWidget);
    expect(find.text('NO BROKER SUBMIT'), findsWidgets);
    expect(find.text('MANUAL APPROVAL REQUIRED'), findsOneWidget);
    expect(find.text('BLOCKED: dry_run=false readiness'), findsWidgets);
    expect(find.text('dry_run is ON'), findsWidgets);
    expect(find.text('real_orders_allowed=false'), findsWidgets);
    expect(find.text('live_scheduler_orders_enabled=false'), findsOneWidget);
    expect(find.text('recent simulation missing'), findsNothing);
    expect(find.text('Real order submitted: No'), findsWidgets);
    expect(find.text('Broker submit: No'), findsWidgets);
    expect(find.text('Manual submit: No'), findsWidgets);
    expect(find.textContaining('broker_submit_called=false'), findsNothing);
    expect(
        find.textContaining('latest simulation has no broker id / no kis_odno'),
        findsOneWidget);
    expect(
      find.text(
          'Manual live orders are excluded from scheduler automation readiness.'),
      findsOneWidget,
    );
    expect(find.text('Enable live KIS scheduler orders'), findsNothing);
    expect(find.text('Enable KIS live scheduler'), findsNothing);

    controller.dispose();
  });

  testWidgets('KIS readiness treats missing safety fields as not ready',
      (tester) async {
    final createdAt = _todayUtcTimestamp(kstHour: 11);
    final controller = DashboardController(
      _FakeLogsApiClient(
        manualSafetyStatus: KisManualOrderSafetyStatus.fromJson(const {}),
        schedulerStatus: KisSchedulerSimulationStatus.fromJson(const {
          'provider': 'kis',
          'market': 'KR',
          'real_orders_allowed': false,
          'safety': {
            'live_scheduler_orders_enabled': false,
            'real_order_submitted': false,
            'broker_submit_called': false,
            'manual_submit_called': false,
          },
        }),
        runs: [
          _schedulerRun(
            action: 'buy',
            result: 'simulated_order_created',
            reason: 'dry_run_risk_approved',
            orderId: 80,
            signalId: 79,
            createdAt: createdAt,
          ),
        ],
        orders: [
          _schedulerOrder(
            orderId: 80,
            side: 'buy',
            notional: 50000,
            createdAt: createdAt,
          ),
        ],
      ),
      autoload: false,
    );

    await _pumpLogs(tester, controller);

    expect(find.text('dry_run is unknown'), findsWidgets);
    expect(find.text('kill_switch unknown'), findsWidgets);
    expect(find.text('kis_enabled unknown'), findsWidgets);
    expect(find.text('kis_real_order_enabled unknown'), findsWidgets);
    expect(find.text('READY CHECKS'), findsOneWidget);
    expect(find.textContaining('/14 passed'), findsOneWidget);
    expect(find.text('LIVE AUTO ORDER: NOT ENABLED'), findsOneWidget);

    controller.dispose();
  });
}

Future<void> _pumpLogs(
  WidgetTester tester,
  DashboardController controller,
) async {
  tester.view.physicalSize = const Size(1200, 5200);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);

  await tester.pumpWidget(MaterialApp(
    theme: ThemeData.dark(),
    home: Scaffold(body: LogsScreen(controller: controller)),
  ));
  await tester.pumpAndSettle();
}

Future<void> _expandAdvancedDetails(WidgetTester tester) async {
  final details = find.text('Advanced Details');
  final count = details.evaluate().length;
  for (var index = 0; index < count; index += 1) {
    await tester.ensureVisible(details.at(index));
    await tester.tap(details.at(index));
    await tester.pumpAndSettle();
  }
}

String _todayUtcTimestamp({required int kstHour, int minute = 0}) {
  final kstNow = DateTime.now().toUtc().add(const Duration(hours: 9));
  final kstTime = DateTime.utc(
    kstNow.year,
    kstNow.month,
    kstNow.day,
    kstHour,
    minute,
  );
  return kstTime.subtract(const Duration(hours: 9)).toIso8601String();
}

KisManualOrderSafetyStatus _manualSafety({
  required bool runtimeDryRun,
  required bool killSwitch,
  required bool kisEnabled,
  required bool kisRealOrderEnabled,
}) {
  return KisManualOrderSafetyStatus(
    runtimeDryRun: runtimeDryRun,
    killSwitch: killSwitch,
    kisEnabled: kisEnabled,
    kisRealOrderEnabled: kisRealOrderEnabled,
    marketOpen: true,
    entryAllowedNow: true,
    noNewEntryAfter: '15:00',
  );
}

TradingLogItem _schedulerRun({
  required String action,
  required String result,
  required String reason,
  String symbol = '005930',
  int? orderId,
  int? signalId,
  required String createdAt,
  List<String> riskFlags = const [],
}) {
  return TradingLogItem.fromJson({
    'id': orderId ?? 40,
    'run_key': 'scheduler-$createdAt',
    'provider': 'kis',
    'market': 'KR',
    'symbol': symbol,
    'trigger_source': 'scheduler_kis_dry_run_auto',
    'mode': 'kis_scheduler_dry_run_auto',
    'action': action,
    'result': result,
    'reason': reason,
    if (orderId != null) 'order_id': orderId,
    if (signalId != null) 'signal_id': signalId,
    'gate_level': 2,
    'created_at': createdAt,
    'dry_run': true,
    'simulated': true,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'risk_flags': riskFlags,
  });
}

OrderLogItem _schedulerOrder({
  required int orderId,
  required String side,
  required num notional,
  required String createdAt,
}) {
  return OrderLogItem.fromJson({
    'id': orderId,
    'order_id': orderId,
    'provider': 'kis',
    'broker': 'kis',
    'market': 'KR',
    'mode': 'kis_scheduler_dry_run_auto',
    'trigger_source': 'scheduler_kis_dry_run_auto',
    'symbol': '005930',
    'side': side,
    'action': side,
    'result': 'DRY_RUN_SIMULATED',
    'reason': 'KIS scheduler simulated order.',
    'qty': 1,
    'notional': notional,
    'internal_status': 'DRY_RUN_SIMULATED',
    'created_at': createdAt,
    'updated_at': createdAt,
    'dry_run': true,
    'simulated': true,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
  });
}

OrderLogItem _manualLiveOrder({
  required int orderId,
  required String createdAt,
}) {
  return OrderLogItem.fromJson({
    'id': orderId,
    'order_id': orderId,
    'provider': 'kis',
    'broker': 'kis',
    'market': 'KR',
    'mode': 'manual_live_order',
    'trigger_source': 'manual',
    'symbol': '005930',
    'side': 'buy',
    'action': 'buy',
    'result': 'SUBMITTED',
    'reason': 'Live KIS order submitted.',
    'qty': 1,
    'notional': 72000,
    'internal_status': 'SUBMITTED',
    'broker_order_status': 'submitted',
    'kis_odno': '0001234567',
    'created_at': createdAt,
    'updated_at': createdAt,
    'real_order_submitted': true,
    'broker_submit_called': true,
    'manual_submit_called': true,
  });
}

SignalLogItem _schedulerSignal({
  required int id,
  required String createdAt,
}) {
  return SignalLogItem.fromJson({
    'id': id,
    'provider': 'kis',
    'market': 'KR',
    'symbol': '005930',
    'action': 'buy',
    'result': 'simulated',
    'signal_status': 'simulated',
    'buy_score': 72,
    'sell_score': 12,
    'confidence': 0.88,
    'reason': 'dry_run_signal',
    'trigger_source': 'scheduler_kis_dry_run_auto',
    'created_at': createdAt,
    'dry_run': true,
    'simulated': true,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
  });
}

class _FakeLogsApiClient extends ApiClient {
  _FakeLogsApiClient({
    this.runs,
    this.orders,
    this.signals,
    this.throwFetch = false,
    KisSchedulerSimulationStatus? schedulerStatus,
    KisManualOrderSafetyStatus? manualSafetyStatus,
  })  : schedulerStatus =
            schedulerStatus ?? KisSchedulerSimulationStatus.safeDefault(),
        manualSafetyStatus = manualSafetyStatus ??
            _manualSafety(
              runtimeDryRun: true,
              killSwitch: false,
              kisEnabled: true,
              kisRealOrderEnabled: true,
            );

  List<TradingLogItem>? runs;
  List<OrderLogItem>? orders;
  List<SignalLogItem>? signals;
  bool throwFetch;
  KisSchedulerSimulationStatus schedulerStatus;
  KisManualOrderSafetyStatus manualSafetyStatus;
  int fetchRecentRunsCalls = 0;

  @override
  Future<List<TradingLogItem>> fetchRecentRuns({int limit = 20}) async {
    fetchRecentRunsCalls += 1;
    if (throwFetch) {
      throw const ApiRequestException('logs failed');
    }
    final override = runs;
    if (override != null) return override;
    return [
      TradingLogItem.fromJson({
        'id': 1,
        'run_key': 'alpaca-run',
        'provider': 'alpaca',
        'market': 'US',
        'symbol': 'AAPL',
        'trigger_source': 'manual',
        'mode': 'watchlist',
        'action': 'hold',
        'result': 'skipped',
        'reason': 'hold_signal',
        'gate_level': 2,
        'created_at': '2026-05-08T00:00:00',
      }),
      TradingLogItem.fromJson({
        'id': 2,
        'run_key': 'kis-preview',
        'provider': 'kis',
        'market': 'KR',
        'symbol': 'WATCHLIST',
        'trigger_source': 'manual_kis_preview',
        'mode': 'kis_watchlist_preview',
        'action': 'hold',
        'result': 'preview_only',
        'reason': 'kr_trading_disabled',
        'gate_level': 2,
        'created_at': '2026-05-08T00:01:00',
        'dry_run': true,
        'preview_only': true,
        'real_order_submitted': false,
        'broker_submit_called': false,
      }),
      TradingLogItem.fromJson({
        'id': 3,
        'run_key': 'kis-dry-run',
        'provider': 'kis',
        'market': 'KR',
        'symbol': '005930',
        'trigger_source': 'manual_kis_dry_run_auto',
        'mode': 'kis_dry_run_auto',
        'action': 'buy',
        'result': 'simulated_order_created',
        'reason': 'dry_run_risk_approved',
        'order_id': 77,
        'signal_id': 76,
        'gate_level': 2,
        'created_at': '2026-05-08T00:02:00',
        'dry_run': true,
        'simulated': true,
        'real_order_submitted': false,
        'broker_submit_called': false,
        'manual_submit_called': false,
      }),
    ];
  }

  @override
  Future<List<OrderLogItem>> fetchRecentOrders({int limit = 20}) async {
    if (throwFetch) {
      throw const ApiRequestException('logs failed');
    }
    final override = orders;
    if (override != null) return override;
    return [
      OrderLogItem.fromJson({
        'id': 8,
        'order_id': 8,
        'provider': 'kis',
        'broker': 'kis',
        'market': 'KR',
        'mode': 'manual_live_order',
        'trigger_source': 'manual',
        'symbol': '005930',
        'side': 'buy',
        'action': 'buy',
        'result': 'SUBMITTED',
        'reason': 'Live KIS order submitted.',
        'qty': 1,
        'notional': 72000,
        'internal_status': 'SUBMITTED',
        'broker_order_status': 'submitted',
        'kis_odno': '0001234567',
        'created_at': '2026-05-08T00:03:00',
        'updated_at': '2026-05-08T00:04:00',
        'real_order_submitted': true,
        'broker_submit_called': true,
        'manual_submit_called': true,
      }),
      OrderLogItem.fromJson({
        'id': 9,
        'order_id': 9,
        'provider': 'kis',
        'broker': 'kis',
        'market': 'KR',
        'mode': 'kis_dry_run_auto',
        'trigger_source': 'manual_kis_dry_run_auto',
        'symbol': '005930',
        'side': 'buy',
        'action': 'buy',
        'result': 'DRY_RUN_SIMULATED',
        'reason': 'KIS dry-run auto simulated order.',
        'qty': 1,
        'notional': 9801,
        'internal_status': 'DRY_RUN_SIMULATED',
        'created_at': '2026-05-08T00:06:00',
        'updated_at': '2026-05-08T00:06:00',
        'dry_run': true,
        'simulated': true,
        'real_order_submitted': false,
        'broker_submit_called': false,
        'manual_submit_called': false,
      }),
      OrderLogItem.fromJson({
        'id': 10,
        'order_id': 10,
        'provider': 'alpaca',
        'broker': 'alpaca',
        'market': 'US',
        'currency': 'USD',
        'mode': 'manual_order',
        'trigger_source': 'manual',
        'symbol': 'AAPL',
        'side': 'buy',
        'action': 'buy',
        'result': 'filled',
        'reason': 'Alpaca paper order.',
        'qty': 1,
        'notional': 123.45,
        'internal_status': 'filled',
        'broker_order_status': 'filled',
        'broker_order_id': 'alpaca-123',
        'created_at': '2026-05-08T00:07:00',
        'updated_at': '2026-05-08T00:08:00',
      }),
      OrderLogItem.fromJson({
        'id': 11,
        'order_id': 11,
        'provider': 'alpaca',
        'broker': 'alpaca',
        'market': 'US',
        'symbol': 'MSFT',
        'side': 'buy',
        'action': 'buy',
        'result': 'submitted',
        'reason': 'Null notional should not crash.',
        'qty': 1,
        'notional': null,
        'internal_status': 'submitted',
        'created_at': '2026-05-08T00:09:00',
        'updated_at': '2026-05-08T00:09:00',
      }),
    ];
  }

  @override
  Future<List<SignalLogItem>> fetchRecentSignals({int limit = 20}) async {
    if (throwFetch) {
      throw const ApiRequestException('logs failed');
    }
    final override = signals;
    if (override != null) return override;
    return [
      SignalLogItem.fromJson({
        'id': 9,
        'provider': 'kis',
        'market': 'KR',
        'symbol': '005930',
        'action': 'buy',
        'result': 'simulated',
        'signal_status': 'simulated',
        'buy_score': 72,
        'sell_score': 12,
        'confidence': 0.88,
        'reason': 'dry_run_signal',
        'trigger_source': 'manual_kis_dry_run_auto',
        'created_at': '2026-05-08T00:05:00',
        'dry_run': true,
        'simulated': true,
        'real_order_submitted': false,
        'broker_submit_called': false,
        'manual_submit_called': false,
      }),
    ];
  }

  @override
  Future<LogsSummary> fetchLogsSummary() async {
    if (throwFetch) {
      throw const ApiRequestException('logs failed');
    }
    return const LogsSummary(
      latestRun: null,
      latestOrder: null,
      latestSignal: null,
      counts: {'runs': 3, 'orders': 1, 'signals': 1},
    );
  }

  @override
  Future<KisSchedulerSimulationStatus> fetchKisSchedulerStatus() async {
    if (throwFetch) {
      throw const ApiRequestException('logs failed');
    }
    return schedulerStatus;
  }

  @override
  Future<KisManualOrderSafetyStatus> fetchKisManualOrderSafetyStatus() async {
    if (throwFetch) {
      throw const ApiRequestException('logs failed');
    }
    return manualSafetyStatus;
  }

  @override
  Future<StrategyAutoBuyOperationsStatus>
      fetchStrategyAutoBuyOperationsStatus({
    String provider = 'kis',
    String market = 'KR',
  }) async {
    if (throwFetch) {
      throw const ApiRequestException('logs failed');
    }
    return StrategyAutoBuyOperationsStatus.fromJson(
      autoBuyOperationsJson(
        stage: 'no_dry_run',
        nextAction: 'run_dry_run',
        ready: false,
      ),
    );
  }
}
