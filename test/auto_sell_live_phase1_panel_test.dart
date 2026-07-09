import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/i18n/app_language.dart';
import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/logs/widgets/auto_sell_live_phase1_panel.dart';
import 'package:auto_invest_dashboard/models/auto_exit_candidate.dart';
import 'package:auto_invest_dashboard/models/auto_sell_live_phase1.dart';
import 'package:auto_invest_dashboard/models/position_management_dry_run.dart';

import 'auto_sell_live_phase1_model_test.dart';

void main() {
  testWidgets('sell phase one panel renders locked safety posture',
      (tester) async {
    _setLargeViewport(tester);
    final api = _SellPhase1ApiClient();
    final controller = DashboardController(
      api,
      autoload: false,
      initialLanguage: AppLanguage.english,
    );
    await controller.refreshAutoSellLivePhase1(silent: true);

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: AutoSellLivePhase1Panel(controller: controller)),
    ));

    expect(find.byKey(const ValueKey('auto-sell-live-phase1-panel')),
        findsOneWidget);
    expect(find.text('Auto Sell Phase 1'), findsOneWidget);
    expect(find.text('Disabled by Default'), findsWidgets);
    expect(find.text('Max 1 Per Day'), findsOneWidget);
    expect(find.text('Held Positions Only'), findsWidgets);
    expect(find.text('Risk Reduction Only'), findsWidgets);
    expect(find.text('Exit Candidate Required'), findsOneWidget);
    expect(find.text('No Broker Submit'), findsWidgets);
    expect(find.text('No Auto Retry'), findsWidgets);
    expect(find.text('Refresh Sell Phase 1 Status'), findsWidgets);
    expect(find.text('Run Phase 1 Sell Once'), findsOneWidget);
    expect(find.text('Enable KIS Real Orders'), findsNothing);
    expect(find.text('Turn Off Dry Run'), findsNothing);
    expect(find.text('Disable Kill Switch'), findsNothing);
    expect(find.text('Force Sell'), findsNothing);
    expect(find.text('Retry Sell'), findsNothing);
    expect(find.text('Liquidate All'), findsNothing);
    expect(find.text('Auto Sell All'), findsNothing);

    controller.dispose();
  });

  testWidgets('sell phase one run button calls phase endpoint only once',
      (tester) async {
    _setLargeViewport(tester);
    final api = _SellPhase1ApiClient();
    final controller = DashboardController(
      api,
      autoload: false,
      initialLanguage: AppLanguage.english,
    );
    await controller.refreshAutoSellLivePhase1(silent: true);

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: AutoSellLivePhase1Panel(controller: controller)),
    ));

    await tester.tap(find.byKey(const ValueKey('run-auto-sell-phase1-once')));
    await tester.pumpAndSettle();

    expect(api.runCalls, 1);
    expect(api.lastConfirmPhase1Run, isTrue);
    expect(api.lastTriggerSource, 'manual_phase1_test');
    expect(api.exitCandidateCalls, 1);
    expect(api.positionDryRunCalls, 1);
    expect(api.settingsMutationCalls, 0);
    expect(api.legacyGuardedSellCalls, 0);
    expect(find.text('Auto Sell Submitted'), findsWidgets);
    expect(find.text('KIS-SELL-1'), findsWidgets);
    expect(find.text('Retry Order'), findsNothing);
    expect(find.text('Submit Again'), findsNothing);
    expect(find.text('Force Sell'), findsNothing);

    controller.dispose();
  });
}

void _setLargeViewport(WidgetTester tester) {
  tester.view.physicalSize = const Size(1200, 1400);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

class _SellPhase1ApiClient extends ApiClient {
  int statusCalls = 0;
  int runCalls = 0;
  int exitCandidateCalls = 0;
  int positionDryRunCalls = 0;
  int settingsMutationCalls = 0;
  int legacyGuardedSellCalls = 0;
  bool? lastConfirmPhase1Run;
  String? lastTriggerSource;

  @override
  Future<AutoSellLivePhase1Result> fetchAutoSellLivePhase1Status({
    String provider = 'kis',
    String market = 'KR',
  }) async {
    statusCalls += 1;
    return AutoSellLivePhase1Result.fromJson(
      runCalls == 0
          ? autoSellLivePhase1Json()
          : autoSellLivePhase1Json(
              enabled: true,
              status: 'submitted',
              realOrderSubmitted: true,
              brokerSubmitCalled: true,
              selectedCandidateId: 'exit-005930-stop',
              selectedSymbol: '005930',
              orderId: 55,
              brokerOrderId: 'KIS-SELL-1',
              dailyCount: 1,
            ),
    );
  }

  @override
  Future<AutoSellLivePhase1Result> runAutoSellLivePhase1Once({
    String provider = 'kis',
    String market = 'KR',
    String? symbol,
    String? candidateId,
    String triggerSource = 'manual_phase1_test',
    String language = 'ko',
    String locale = 'ko-KR',
    bool confirmPhase1Run = true,
  }) async {
    runCalls += 1;
    lastConfirmPhase1Run = confirmPhase1Run;
    lastTriggerSource = triggerSource;
    return AutoSellLivePhase1Result.fromJson(
      autoSellLivePhase1Json(
        enabled: true,
        status: 'submitted',
        realOrderSubmitted: true,
        brokerSubmitCalled: true,
        selectedCandidateId: candidateId ?? 'exit-005930-stop',
        selectedSymbol: symbol ?? '005930',
        orderId: 55,
        brokerOrderId: 'KIS-SELL-1',
        dailyCount: 1,
      ),
    );
  }

  @override
  Future<AutoExitCandidates> fetchAutoExitCandidates({
    String provider = 'kis',
    String market = 'KR',
    String? symbol,
    bool includeDetails = true,
    String? minSeverity,
  }) async {
    exitCandidateCalls += 1;
    return AutoExitCandidates.fromJson(_autoExitCandidatesJson());
  }

  @override
  Future<PositionManagementDryRun> fetchPositionManagementDryRunLatest({
    String provider = 'kis',
    String market = 'KR',
  }) async {
    positionDryRunCalls += 1;
    return PositionManagementDryRun.fromJson(_positionManagementDryRunJson());
  }

  @override
  Future<void> updateOpsSettings(Map<String, dynamic> values) async {
    settingsMutationCalls += 1;
  }
}

Map<String, dynamic> _autoExitCandidatesJson() {
  return {
    'generated_at': '2026-07-09T00:00:00Z',
    'timezone': 'Asia/Seoul',
    'provider': 'kis',
    'market': 'KR',
    'candidates': const [],
    'summary': const {
      'candidate_count': 0,
      'critical_count': 0,
      'warning_count': 0,
      'info_count': 0,
      'stop_loss_count': 0,
      'take_profit_count': 0,
      'trend_breakdown_count': 0,
      'manual_review_count': 0,
      'duplicate_sell_block_count': 0,
      'sync_required_count': 0,
    },
    'safety_flags': const ['read_only', 'no_live_orders'],
  };
}

Map<String, dynamic> _positionManagementDryRunJson() {
  return {
    'run_id': null,
    'generated_at': '2026-07-09T00:00:00Z',
    'provider': 'kis',
    'market': 'KR',
    'trigger_source': 'position_management_dry_run_latest_lookup',
    'dry_run_only': true,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'positions_checked': 0,
    'exit_candidate_count': 0,
    'critical_candidate_count': 0,
    'warning_candidate_count': 0,
    'simulated_sell_preflight_count': 0,
    'blocked_preflight_count': 0,
    'sync_required_count': 0,
    'duplicate_sell_conflict_count': 0,
    'result_status': 'skipped',
    'primary_reason': 'no_recent_position_management_dry_run',
    'risk_flags': const ['no_recent_run'],
    'gating_notes': const [
      'No position management dry-run has been recorded yet.',
    ],
    'candidates': const [],
    'sell_preflight_results': const [],
    'next_safe_actions': const ['Continue monitoring held positions.'],
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
