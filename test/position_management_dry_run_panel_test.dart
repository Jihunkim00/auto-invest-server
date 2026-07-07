import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/i18n/app_language.dart';
import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/logs/widgets/position_management_dry_run_panel.dart';
import 'package:auto_invest_dashboard/models/position_management_dry_run.dart';

void main() {
  testWidgets('position management dry-run panel renders Korean default labels',
      (tester) async {
    await _setLargeView(tester);
    final controller = _controller(_FakePositionManagementApi())
      ..positionManagementDryRun =
          PositionManagementDryRun.fromJson(_runJson());

    await tester.pumpWidget(_wrap(controller));

    expect(find.byKey(const ValueKey('position-management-dry-run-panel')),
        findsOneWidget);
    expect(
        find.text(controller.strings.positionManagementDryRun), findsOneWidget);
    expect(
        find.textContaining(controller.strings.positionsFirst), findsOneWidget);
    expect(find.text(controller.strings.dryRunOnly), findsOneWidget);
    expect(find.text(controller.strings.operatorNoLiveOrders), findsOneWidget);
    expect(find.text(controller.strings.noBrokerSubmitDisplay), findsOneWidget);
    expect(find.text(controller.strings.noSellExecution), findsOneWidget);
    expect(find.text(controller.strings.positionsChecked), findsOneWidget);
    expect(find.text(controller.strings.exitCandidates), findsOneWidget);
    expect(find.text(controller.strings.criticalCandidates), findsOneWidget);
    expect(find.text(controller.strings.syncRequired), findsOneWidget);

    controller.dispose();
  });

  testWidgets('position management dry-run panel renders English labels',
      (tester) async {
    await _setLargeView(tester);
    final controller = _controller(
      _FakePositionManagementApi(),
      language: AppLanguage.english,
    )..positionManagementDryRun = PositionManagementDryRun.fromJson(_runJson());

    await tester.pumpWidget(_wrap(controller));

    expect(find.text('Position Management Dry-Run'), findsOneWidget);
    expect(find.textContaining('Positions First'), findsOneWidget);
    expect(find.text('DRY-RUN ONLY'), findsOneWidget);
    expect(find.text('No Live Orders'), findsOneWidget);
    expect(find.text('No Broker Submit'), findsOneWidget);
    expect(find.text('No Sell Execution'), findsOneWidget);
    expect(find.text('Positions Checked'), findsOneWidget);
    expect(find.text('Exit Candidates'), findsOneWidget);
    expect(find.text('Critical Candidates'), findsOneWidget);
    expect(find.text('Sync Required'), findsOneWidget);
    expect(find.text('Run Position Management Dry-Run Once'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('run once calls only dry-run endpoint', (tester) async {
    await _setLargeView(tester);
    final api = _FakePositionManagementApi();
    final controller = _controller(api, language: AppLanguage.english)
      ..positionManagementDryRun =
          PositionManagementDryRun.fromJson(_runJson());

    await tester.pumpWidget(_wrap(controller));

    final button = find.byKey(
      const ValueKey('position-management-dry-run-run-once-button'),
    );
    await tester.ensureVisible(button);
    await tester.tap(button);
    await tester.pumpAndSettle();

    expect(api.runOnceCalls, 1);
    expect(api.refreshCalls, 0);
    expect(api.guardedSellCalls, 0);
    expect(api.manualSubmitCalls, 0);
    expect(api.sentConfirmLive, isFalse);

    controller.dispose();
  });

  testWidgets('position management dry-run panel has no unsafe controls',
      (tester) async {
    await _setLargeView(tester);
    final controller = _controller(
      _FakePositionManagementApi(),
      language: AppLanguage.english,
    )..positionManagementDryRun = PositionManagementDryRun.fromJson(_runJson());

    await tester.pumpWidget(_wrap(controller));

    for (final label in [
      'Sell Now',
      'Execute Sell',
      'Force Sell',
      'Auto Sell',
      'Liquidate All',
      'Retry Sell',
      'Enable Live Scheduler',
      'Enable Live Position Management',
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
  _FakePositionManagementApi api, {
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
        child: PositionManagementDryRunPanel(controller: controller),
      ),
    ),
  );
}

class _FakePositionManagementApi extends ApiClient {
  int refreshCalls = 0;
  int runOnceCalls = 0;
  int guardedSellCalls = 0;
  int manualSubmitCalls = 0;
  bool sentConfirmLive = false;

  @override
  Future<PositionManagementDryRun> fetchPositionManagementDryRunLatest({
    String provider = 'kis',
    String market = 'KR',
  }) async {
    refreshCalls += 1;
    return PositionManagementDryRun.fromJson(_runJson());
  }

  @override
  Future<PositionManagementDryRun> runPositionManagementDryRunOnce({
    String provider = 'kis',
    String market = 'KR',
    String? symbol,
    bool includeSellPreflight = true,
  }) async {
    runOnceCalls += 1;
    sentConfirmLive = false;
    return PositionManagementDryRun.fromJson(_runJson());
  }
}

Map<String, dynamic> _runJson() {
  return {
    'run_id': 42,
    'generated_at': '2026-07-07T09:00:00Z',
    'provider': 'kis',
    'market': 'KR',
    'trigger_source': 'manual_position_management_dry_run',
    'dry_run_only': true,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'positions_checked': 1,
    'exit_candidate_count': 1,
    'critical_candidate_count': 1,
    'warning_candidate_count': 0,
    'simulated_sell_preflight_count': 1,
    'blocked_preflight_count': 0,
    'sync_required_count': 1,
    'duplicate_sell_conflict_count': 0,
    'result_status': 'completed',
    'primary_reason': 'position_management_dry_run_completed',
    'risk_flags': const ['dry_run_only', 'sync_required'],
    'gating_notes': const ['No order path was called.'],
    'candidates': [_candidate()],
    'sell_preflight_results': const [
      {'symbol': '005930', 'preflight_status': 'allowed'},
    ],
    'next_safe_actions': const ['Review candidates.'],
    'priority': 'positions_first',
    'entry_orders_allowed': false,
    'exit_orders_allowed': false,
    'dry_run_monitoring_only': true,
    'scheduler_enabled': false,
    'scheduler_dry_run_only': true,
    'scheduler_allow_live_orders': false,
    'safety': const {'dry_run_only': true},
  };
}

Map<String, dynamic> _candidate() {
  return {
    'candidate_id': 'auto-exit:kis:KR:005930:stop_loss:20260707',
    'symbol': '005930',
    'provider': 'kis',
    'market': 'KR',
    'candidate_type': 'stop_loss',
    'severity': 'critical',
    'status': 'active',
    'action_hint': 'run_sell_preflight',
    'position_quantity': 3,
    'available_quantity': 3,
    'average_price': 10000,
    'current_price': 9000,
    'cost_basis': 30000,
    'current_value': 27000,
    'unrealized_pl': -3000,
    'unrealized_pl_pct': -0.10,
    'stop_loss_threshold_pct': 2,
    'take_profit_threshold_pct': 3,
    'stop_loss_triggered': true,
    'take_profit_triggered': false,
    'trend_breakdown_triggered': false,
    'risk_flags': const ['stop_loss_triggered'],
    'gating_notes': const ['Read-only candidate detection.'],
    'primary_reason': 'Stop-loss threshold was reached.',
    'next_safe_action': 'Run sell preflight.',
    'open_sell_order_conflict': false,
    'sync_required': true,
    'can_run_sell_preflight': false,
  };
}
