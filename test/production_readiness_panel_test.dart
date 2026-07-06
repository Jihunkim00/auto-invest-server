import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/i18n/app_language.dart';
import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/logs/widgets/production_readiness_panel.dart';
import 'package:auto_invest_dashboard/models/ops_production_readiness.dart';

void main() {
  testWidgets('production readiness panel renders Korean default labels',
      (tester) async {
    await _setLargeView(tester);
    final controller = _controller(_FakeReadinessApi())
      ..latestOpsProductionReadiness =
          OpsProductionReadiness.fromJson(_readinessJson());

    await tester.pumpWidget(_wrap(controller));

    expect(find.byKey(const ValueKey('production-readiness-panel')),
        findsOneWidget);
    expect(find.text('운영 준비 점검'), findsOneWidget);
    expect(find.text('실전 준비 상태'), findsOneWidget);
    expect(find.text('차단됨'), findsWidgets);
    expect(find.text('읽기 전용'), findsOneWidget);
    expect(find.text('실주문 없음'), findsOneWidget);
    expect(find.text('자동화 해제 불가'), findsOneWidget);
    expect(find.text('주요 차단 사유'), findsOneWidget);
    expect(find.text('다음 안전 조치'), findsOneWidget);
    expect(find.text('런타임 설정'), findsOneWidget);
    expect(find.text('브로커 상태'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('production readiness panel renders English labels',
      (tester) async {
    await _setLargeView(tester);
    final controller = _controller(
      _FakeReadinessApi(),
      language: AppLanguage.english,
    )..latestOpsProductionReadiness =
        OpsProductionReadiness.fromJson(_readinessJson());

    await tester.pumpWidget(_wrap(controller));

    expect(find.text('Production Readiness'), findsOneWidget);
    expect(find.text('Live Readiness Status'), findsOneWidget);
    expect(find.text('Blocked'), findsWidgets);
    expect(find.text('Read Only'), findsOneWidget);
    expect(find.text('No Live Orders'), findsOneWidget);
    expect(find.text('Automation Unlock Not Allowed'), findsOneWidget);
    expect(find.text('Primary Block Reasons'), findsOneWidget);
    expect(find.text('Next Safe Actions'), findsOneWidget);
    expect(find.text('Runtime Settings'), findsOneWidget);
    expect(find.text('Broker Status'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('production readiness panel refreshes only through API client',
      (tester) async {
    await _setLargeView(tester);
    final api = _FakeReadinessApi();
    final controller = _controller(api)
      ..latestOpsProductionReadiness =
          OpsProductionReadiness.fromJson(_readinessJson());

    await tester.pumpWidget(_wrap(controller));

    await tester
        .tap(find.byKey(const ValueKey('production-readiness-refresh-button')));
    await tester.pumpAndSettle();

    expect(api.refreshCalls, 1);
    expect(api.lastProvider, 'kis');
    expect(api.lastMarket, 'KR');

    controller.dispose();
  });

  testWidgets('production readiness panel has no unsafe controls',
      (tester) async {
    await _setLargeView(tester);
    final controller = _controller(_FakeReadinessApi())
      ..latestOpsProductionReadiness =
          OpsProductionReadiness.fromJson(_readinessJson());

    await tester.pumpWidget(_wrap(controller));

    for (final label in [
      'Enable Live Trading',
      'Turn Off Dry Run',
      'Disable Kill Switch',
      'Enable Real Orders',
      'Enable Live Scheduler',
      'Buy',
      'Sell',
      'Retry',
      'Force Sync',
      'Liquidate All',
      'Auto Exit',
    ]) {
      expect(find.text(label), findsNothing);
    }

    controller.dispose();
  });
}

Future<void> _setLargeView(WidgetTester tester) async {
  tester.view.physicalSize = const Size(1200, 6400);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

DashboardController _controller(
  _FakeReadinessApi api, {
  AppLanguage language = AppLanguage.korean,
}) {
  return DashboardController(
    api,
    autoload: false,
    initialLanguage: language,
  )
    ..selectedProvider = SelectedProvider.kis
    ..selectedPortfolioMarket = PortfolioMarket.kr;
}

Widget _wrap(DashboardController controller) {
  return MaterialApp(
    theme: ThemeData.dark(),
    home: Scaffold(
      body: SingleChildScrollView(
        child: ProductionReadinessPanel(controller: controller),
      ),
    ),
  );
}

class _FakeReadinessApi extends ApiClient {
  int refreshCalls = 0;
  String? lastProvider;
  String? lastMarket;

  @override
  Future<OpsProductionReadiness> fetchOpsProductionReadiness({
    String provider = 'kis',
    String market = 'KR',
    bool includeDetails = true,
    bool includeRaw = false,
    int days = 7,
    bool includeRecent = true,
  }) async {
    refreshCalls += 1;
    lastProvider = provider;
    lastMarket = market;
    return OpsProductionReadiness.fromJson(_readinessJson());
  }
}

Map<String, dynamic> _readinessJson() {
  return {
    'generated_at': '2026-07-06T09:00:00+09:00',
    'timezone': 'Asia/Seoul',
    'provider': 'kis',
    'market': 'KR',
    'overall_status': 'blocked',
    'readiness_score': 62,
    'summary': {
      'ready_count': 4,
      'warning_count': 2,
      'blocked_count': 1,
      'unknown_count': 0,
      'critical_block_count': 1,
      'can_use_guarded_live_buy': false,
      'can_use_guarded_live_sell': false,
      'can_enable_scheduler_live_orders': false,
      'scheduler_real_orders_allowed': false,
      'automation_unlock_allowed': false,
      'active_alert_count': 2,
      'sync_required_alert_count': 1,
    },
    'checklist': [
      _item('kill_switch_off', 'runtime', 'pass', 'Kill switch off'),
      _item(
        'dry_run_blocks_live_submit',
        'runtime',
        'warn',
        'Dry-run live block',
        blocking: true,
      ),
      _item('broker_config_present', 'broker', 'fail', 'Broker configuration',
          blocking: true),
      _item('scheduler_real_orders_allowed', 'scheduler', 'pass',
          'Scheduler real orders disabled'),
      _item('pending_sync_count', 'orders', 'warn', 'Pending reconciliation'),
      _item('incomplete_pl_count', 'pnl', 'warn', 'Incomplete P/L'),
      _item('active_alert_count', 'alerts', 'warn', 'Active alerts'),
      _item('agent_chat_read_only_for_trading', 'agent_chat', 'pass',
          'Agent Chat trading guardrails'),
    ],
    'blocking_reasons': ['broker_config_present'],
    'warnings': ['dry_run_blocks_live_submit'],
    'next_safe_actions': ['Keep this report read-only.'],
    'safety_flags': {
      'read_only': true,
      'no_live_orders': true,
      'automation_unlock_allowed': false,
    },
  };
}

Map<String, dynamic> _item(
  String key,
  String category,
  String status,
  String title, {
  bool blocking = false,
}) {
  return {
    'key': key,
    'category': category,
    'status': status,
    'title': title,
    'detail': '$title detail.',
    'blocking': blocking,
    'severity': blocking ? 'critical' : 'info',
    'related_type': null,
    'related_id': null,
    'next_safe_action': '$title review.',
  };
}
