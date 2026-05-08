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

    await tester.tap(find.text('Orders').last);
    await tester.pumpAndSettle();

    expect(find.text('KIS MANUAL LIVE'), findsOneWidget);
    expect(find.text('REAL ORDER SUBMITTED'), findsOneWidget);
    expect(find.text('MANUAL ONLY'), findsOneWidget);
    expect(find.text('real_order_submitted=true'), findsOneWidget);
    expect(find.text('broker_submit_called=true'), findsOneWidget);
    expect(find.text('manual_submit_called=true'), findsOneWidget);

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
        'internal_status': 'SUBMITTED',
        'broker_order_status': 'submitted',
        'kis_odno': '0001234567',
        'created_at': '2026-05-08T00:03:00',
        'updated_at': '2026-05-08T00:04:00',
        'real_order_submitted': true,
        'broker_submit_called': true,
        'manual_submit_called': true,
      }),
    ];
  }

  @override
  Future<List<SignalLogItem>> fetchRecentSignals({int limit = 20}) async {
    return const [];
  }

  @override
  Future<LogsSummary> fetchLogsSummary() async {
    return const LogsSummary(
      latestRun: null,
      latestOrder: null,
      latestSignal: null,
      counts: {'runs': 3, 'orders': 1, 'signals': 0},
    );
  }
}
