import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/logs/logs_screen.dart';
import 'package:auto_invest_dashboard/models/log_items.dart';

void main() {
  testWidgets('Logs screen shows backend activity source and safety labels',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 2200);
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
    expect(find.text('NO BROKER SUBMIT'), findsOneWidget);
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
}

class _FakeLogsApiClient extends ApiClient {
  @override
  Future<List<TradingLogItem>> fetchRecentRuns({int limit = 20}) async {
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
    return const LogsSummary(
      latestRun: null,
      latestOrder: null,
      latestSignal: null,
      counts: {'runs': 3, 'orders': 1, 'signals': 1},
    );
  }
}
