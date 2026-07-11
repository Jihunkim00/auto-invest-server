import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/i18n/app_language.dart';
import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/logs/widgets/broker_sync_watchdog_panel.dart';
import 'package:auto_invest_dashboard/models/broker_sync_watchdog.dart';

import 'broker_sync_watchdog_model_test.dart';

void main() {
  testWidgets('panel renders Korean watchdog labels', (tester) async {
    await _setLargeView(tester);
    final controller = _controller(
      BrokerSyncWatchdogResult.fromJson(brokerSyncWatchdogJson()),
    );

    await _pumpPanel(tester, controller);

    expect(find.byKey(const ValueKey('broker-sync-watchdog-panel')),
        findsOneWidget);
    expect(find.text('釉뚮줈而??숆린??媛먯떆'), findsOneWidget);
    expect(find.text('二쇰Ц/?ъ????숆린???곹깭'), findsOneWidget);
    expect(find.text('?숆린???뺤긽'), findsOneWidget);
    expect(find.text('二쇰Ц 痍⑥냼 ?놁쓬'), findsOneWidget);
    expect(find.text('媛먯떆 1???ㅽ뻾'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('panel renders English healthy status and safe controls',
      (tester) async {
    await _setLargeView(tester);
    final controller = _controller(
      BrokerSyncWatchdogResult.fromJson(brokerSyncWatchdogJson()),
      language: AppLanguage.english,
    );

    await _pumpPanel(tester, controller);

    expect(find.text('Broker Sync Watchdog'), findsOneWidget);
    expect(find.text('Order / Position Sync Health'), findsOneWidget);
    expect(find.text('Sync Healthy'), findsOneWidget);
    expect(find.text('Automation Allowed'), findsOneWidget);
    expect(find.text('Read Only'), findsOneWidget);
    expect(find.text('No Live Orders'), findsOneWidget);
    expect(find.text('No Order Cancel'), findsOneWidget);
    expect(find.text('No Broker Submit'), findsOneWidget);
    expect(find.text('Refresh Watchdog Status'), findsOneWidget);
    expect(find.text('Run Watchdog Once'), findsOneWidget);

    for (final forbidden in const [
      'Submit Order',
      'Cancel Order',
      'Force Buy',
      'Force Sell',
      'Liquidate All',
      'Retry Order',
      'Disable Kill Switch',
      'Turn Off Dry Run',
      'Enable KIS Real Orders',
      'Skip Gates',
    ]) {
      expect(find.text(forbidden), findsNothing, reason: forbidden);
    }

    controller.dispose();
  });

  testWidgets('unsafe status shows blockers and issue details', (tester) async {
    await _setLargeView(tester);
    final unsafe = BrokerSyncWatchdogResult.fromJson(
      brokerSyncWatchdogJson(
        syncHealth: 'unsafe',
        automationBlocked: true,
        staleLocalOrderCount: 1,
        pendingSyncOrderCount: 1,
        missingKisOdnoCount: 1,
        positionMismatchCount: 1,
        blockingReasons: const ['broker_sync_watchdog_blocked'],
        issues: const [
          {
            'issue_id': 'stale-1',
            'issue_type': 'stale_local_order',
            'severity': 'critical',
            'provider': 'kis',
            'market': 'KR',
            'symbol': '005930',
            'order_id': 42,
            'kis_odno': '0000000042',
            'detected_at': '2026-07-10T01:05:00Z',
            'age_minutes': 18.5,
            'local_status': 'ACCEPTED',
            'automation_blocking': true,
            'recommended_action': 'manual_review',
            'reason': 'Local order is stale.',
            'sanitized_context': {'source': 'unit_test'},
          },
          {
            'issue_id': 'position-1',
            'issue_type': 'position_quantity_mismatch',
            'severity': 'warning',
            'provider': 'kis',
            'market': 'KR',
            'symbol': '000660',
            'detected_at': '2026-07-10T01:06:00Z',
            'local_quantity': 2,
            'broker_quantity': 1,
            'automation_blocking': true,
            'recommended_action': 'inspect_broker_app',
            'reason': 'Position quantity differs.',
            'sanitized_context': {},
          },
        ],
      ),
    );
    final controller = _controller(unsafe, language: AppLanguage.english);

    await _pumpPanel(tester, controller);

    expect(find.text('Sync Unsafe'), findsOneWidget);
    expect(find.text('Automation Blocked'), findsOneWidget);
    expect(find.text('Stale Orders'), findsOneWidget);
    expect(find.text('Pending Sync Orders'), findsOneWidget);
    expect(find.text('Missing KIS ODNO'), findsOneWidget);
    expect(find.text('Position Quantity Mismatch'), findsOneWidget);

    await tester.tap(
      find.byKey(const ValueKey('toggle-broker-sync-watchdog-details')),
    );
    await tester.pumpAndSettle();

    expect(find.text('Issue Details'), findsOneWidget);
    expect(find.text('STALE LOCAL ORDER'), findsOneWidget);
    expect(find.text('POSITION QUANTITY MISMATCH'), findsOneWidget);
    expect(find.text('Local order is stale.'), findsOneWidget);
    expect(find.text('Position quantity differs.'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('run once calls only watchdog run action', (tester) async {
    await _setLargeView(tester);
    final api = _WatchdogApi(
      BrokerSyncWatchdogResult.fromJson(
        brokerSyncWatchdogJson(syncHealth: 'warning'),
      ),
    );
    final controller = DashboardController(
      api,
      autoload: false,
      initialLanguage: AppLanguage.english,
    )..brokerSyncWatchdogStatus = api.result;

    await _pumpPanel(tester, controller);
    await tester.tap(find.byKey(const ValueKey('run-broker-sync-watchdog-once')));
    await tester.pumpAndSettle();

    expect(api.runCalls, 1);
    expect(api.statusCalls, 0);
    expect(api.latestCalls, 0);
    expect(api.lastProvider, 'kis');
    expect(api.lastMarket, 'KR');

    controller.dispose();
  });
}

DashboardController _controller(
  BrokerSyncWatchdogResult result, {
  AppLanguage language = AppLanguage.korean,
}) {
  final api = _WatchdogApi(result);
  return DashboardController(
    api,
    autoload: false,
    initialLanguage: language,
  )..brokerSyncWatchdogStatus = result;
}

Future<void> _pumpPanel(
  WidgetTester tester,
  DashboardController controller,
) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: BrokerSyncWatchdogPanel(controller: controller)),
    ),
  );
  await tester.pump();
}

Future<void> _setLargeView(WidgetTester tester) async {
  tester.view.physicalSize = const Size(1200, 2200);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

class _WatchdogApi extends ApiClient {
  _WatchdogApi(this.result);

  final BrokerSyncWatchdogResult result;
  int statusCalls = 0;
  int latestCalls = 0;
  int runCalls = 0;
  String? lastProvider;
  String? lastMarket;

  @override
  Future<BrokerSyncWatchdogResult> fetchBrokerSyncWatchdogStatus({
    String provider = 'kis',
    String market = 'KR',
  }) async {
    statusCalls += 1;
    lastProvider = provider;
    lastMarket = market;
    return result;
  }

  @override
  Future<BrokerSyncWatchdogResult> fetchBrokerSyncWatchdogLatest({
    String provider = 'kis',
    String market = 'KR',
  }) async {
    latestCalls += 1;
    lastProvider = provider;
    lastMarket = market;
    return result;
  }

  @override
  Future<BrokerSyncWatchdogResult> runBrokerSyncWatchdogOnce({
    String provider = 'kis',
    String market = 'KR',
  }) async {
    runCalls += 1;
    lastProvider = provider;
    lastMarket = market;
    return result;
  }
}
