import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/core/utils/timestamp_formatter.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/logs/logs_screen.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_safety_status.dart';
import 'package:auto_invest_dashboard/models/kis_scheduler_simulation.dart';
import 'package:auto_invest_dashboard/models/log_items.dart';

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
    expect(find.text('preview_only=true'), findsOneWidget);
    expect(find.text('real_order_submitted=false'), findsWidgets);
    expect(find.text('broker_submit_called=false'), findsWidgets);
    expect(find.text('manual_submit_called=false'), findsOneWidget);
    expect(find.text('05-08 00:00 (KST 09:00)'), findsOneWidget);

    await tester.tap(find.text('Orders').last);
    await tester.pumpAndSettle();

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
    expect(find.text('real_order_submitted=true'), findsOneWidget);
    expect(find.text('broker_submit_called=true'), findsOneWidget);
    expect(find.text('manual_submit_called=true'), findsOneWidget);
    expect(find.text('05-08 00:03 (KST 09:03)'), findsOneWidget);
    expect(find.text('05-08 00:04 (KST 09:04)'), findsOneWidget);

    await tester.tap(find.text('Signals').last);
    await tester.pumpAndSettle();

    expect(find.text('05-08 00:05 (KST 09:05)'), findsOneWidget);

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
    expect(find.text('real_order_submitted=false'), findsWidgets);
    expect(find.text('broker_submit_called=false'), findsWidgets);
    expect(find.text('manual_submit_called=false'), findsWidgets);
    expect(find.text('real_orders_allowed=false'), findsWidgets);
    expect(find.text('live_scheduler=disabled'), findsOneWidget);
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
    expect(find.text('real_order_submitted=false'), findsWidgets);
    expect(find.text('broker_submit_called=false'), findsWidgets);
    expect(find.text('manual_submit_called=false'), findsWidgets);
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
}
