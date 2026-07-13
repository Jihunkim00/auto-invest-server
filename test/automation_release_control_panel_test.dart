import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/i18n/app_language.dart';
import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/logs/widgets/automation_release_status_panel.dart';
import 'package:auto_invest_dashboard/features/settings/widgets/automation_release_control_panel.dart';
import 'package:auto_invest_dashboard/models/automation_mode_control.dart';
import 'package:auto_invest_dashboard/models/automation_release.dart';
import 'package:auto_invest_dashboard/models/automation_soak_test.dart';
import 'package:auto_invest_dashboard/models/auto_buy_live_phase1.dart';
import 'package:auto_invest_dashboard/models/auto_sell_live_phase1.dart';
import 'package:auto_invest_dashboard/models/broker_sync_watchdog.dart';
import 'package:auto_invest_dashboard/models/ops_production_readiness.dart';
import 'package:auto_invest_dashboard/models/portfolio_orchestrator.dart';

import 'automation_mode_control_model_test.dart';
import 'automation_release_model_test.dart';
import 'automation_soak_test_model_test.dart';
import 'auto_buy_live_phase1_model_test.dart';
import 'auto_sell_live_phase1_model_test.dart';
import 'broker_sync_watchdog_model_test.dart';
import 'portfolio_orchestrator_model_test.dart';

void main() {
  testWidgets('control panel renders labels and hides unsafe controls',
      (tester) async {
    await _setLargeView(tester);
    final api = _FakeAutomationReleaseApi();
    final controller = _controller(api, AppLanguage.english);

    await tester.pumpWidget(_wrap(AutomationReleaseControlPanel(
      controller: controller,
    )));

    expect(find.text('Controlled Full Automation Release'), findsOneWidget);
    expect(find.text('Automation Release'), findsWidgets);
    expect(find.text('Release Preflight'), findsWidgets);
    expect(find.text('Arm Release'), findsOneWidget);
    expect(find.text('Disarm Release'), findsOneWidget);
    expect(find.text('Arm with Risk Acknowledgement'), findsOneWidget);
    expect(find.text('Checklist'), findsOneWidget);
    expect(find.text('Blocking Reasons'), findsOneWidget);
    expect(find.text('Warning Reasons'), findsOneWidget);
    expect(find.text('Next Safe Action'), findsOneWidget);
    expect(find.text('No Live Orders'), findsOneWidget);
    expect(find.text('No Broker Submit'), findsWidgets);
    expect(find.text('No Order Cancel'), findsWidgets);

    for (final label in [
      'Force Run',
      'Skip Gates',
      'Disable Kill Switch',
      'Turn Off Dry Run',
      'Enable KIS Real Orders',
      'Submit Order',
      'Cancel Order',
      'Force Buy',
      'Force Sell',
      'Liquidate All',
      'Retry Order',
    ]) {
      expect(find.text(label), findsNothing);
    }

    controller.dispose();
  });

  testWidgets('Korean control panel label renders', (tester) async {
    await _setLargeView(tester);
    final api = _FakeAutomationReleaseApi();
    final controller = _controller(api, AppLanguage.korean);

    await tester.pumpWidget(_wrap(AutomationReleaseControlPanel(
      controller: controller,
    )));

    expect(find.text('제한형 완전 자동화 릴리스'), findsOneWidget);
    controller.dispose();
  });

  testWidgets('arm requires acknowledgement and disarm uses release endpoint',
      (tester) async {
    await _setLargeView(tester);
    final api = _FakeAutomationReleaseApi();
    final controller = _controller(api, AppLanguage.english);

    await tester.pumpWidget(_wrap(AutomationReleaseControlPanel(
      controller: controller,
    )));

    var arm = tester.widget<FilledButton>(
      find.byKey(const ValueKey('automation-release-arm-button')),
    );
    expect(arm.onPressed, isNull);

    await tester.tap(
      find.byKey(const ValueKey('automation-release-risk-ack-checkbox')),
    );
    await tester.pumpAndSettle();
    arm = tester.widget<FilledButton>(
      find.byKey(const ValueKey('automation-release-arm-button')),
    );
    expect(arm.onPressed, isNotNull);

    await tester
        .tap(find.byKey(const ValueKey('automation-release-arm-button')));
    await tester.pumpAndSettle();
    expect(api.armCalls, 1);
    expect(api.lastArmAcknowledged, isTrue);

    await tester
        .tap(find.byKey(const ValueKey('automation-release-disarm-button')));
    await tester.pumpAndSettle();
    expect(api.disarmCalls, 1);

    controller.dispose();
  });

  testWidgets('preflight and dry-run cycle use safe release calls',
      (tester) async {
    await _setLargeView(tester);
    final api = _FakeAutomationReleaseApi();
    final controller = _controller(api, AppLanguage.english);

    await tester.pumpWidget(_wrap(AutomationReleaseControlPanel(
      controller: controller,
    )));

    await tester
        .tap(find.byKey(const ValueKey('automation-release-preflight-button')));
    await tester.pumpAndSettle();
    expect(api.preflightCalls, 1);

    await tester.tap(
      find.byKey(const ValueKey('automation-release-dry-run-cycle-button')),
    );
    await tester.pumpAndSettle();
    expect(api.cycleCalls, 1);
    expect(api.lastCycleMode, 'dry_run');
    expect(api.lastCycleAcknowledged, isFalse);

    controller.dispose();
  });

  testWidgets('logs status panel is read-only', (tester) async {
    await _setLargeView(tester);
    final api = _FakeAutomationReleaseApi();
    final controller = _controller(api, AppLanguage.english);

    await tester.pumpWidget(_wrap(AutomationReleaseStatusPanel(
      controller: controller,
    )));

    expect(find.text('Automation Release'), findsWidgets);
    expect(find.text('Checklist'), findsOneWidget);
    expect(find.text('Arm Release'), findsNothing);
    expect(find.text('Disarm Release'), findsNothing);
    expect(find.text('No Broker Submit'), findsWidgets);

    await tester
        .tap(find.byKey(const ValueKey('automation-release-status-refresh')));
    await tester.pumpAndSettle();
    expect(api.statusCalls, 1);

    controller.dispose();
  });
}

Future<void> _setLargeView(WidgetTester tester) async {
  tester.view.physicalSize = const Size(1200, 5200);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

DashboardController _controller(
  _FakeAutomationReleaseApi api,
  AppLanguage language,
) {
  return DashboardController(
    api,
    autoload: false,
    initialLanguage: language,
  )
    ..selectedProvider = SelectedProvider.kis
    ..selectedPortfolioMarket = PortfolioMarket.kr
    ..automationReleaseStatus = api.status
    ..automationReleaseCycleResult = api.cycle;
}

Widget _wrap(Widget child) {
  return MaterialApp(
    theme: ThemeData.dark(),
    home: Scaffold(body: SingleChildScrollView(child: child)),
  );
}

class _FakeAutomationReleaseApi extends ApiClient {
  _FakeAutomationReleaseApi()
      : status =
            AutomationReleaseStatus.fromJson(automationReleaseStatusJson()),
        cycle = AutomationReleaseCycleResult.fromJson(
          automationReleaseCycleJson(),
        );

  AutomationReleaseStatus status;
  AutomationReleaseCycleResult cycle;
  int statusCalls = 0;
  int preflightCalls = 0;
  int armCalls = 0;
  int disarmCalls = 0;
  int cycleCalls = 0;
  bool? lastArmAcknowledged;
  String? lastCycleMode;
  bool? lastCycleAcknowledged;

  @override
  Future<AutomationReleaseStatus> fetchAutomationReleaseStatus() async {
    statusCalls += 1;
    return status;
  }

  @override
  Future<AutomationReleaseStatus> runAutomationReleasePreflight() async {
    preflightCalls += 1;
    return status;
  }

  @override
  Future<AutomationReleaseStatus> armAutomationRelease({
    required bool operatorAcknowledgedRisks,
    String? reason,
    String releaseMode = 'controlled_phase1',
    String language = 'ko',
    String locale = 'ko-KR',
  }) async {
    armCalls += 1;
    lastArmAcknowledged = operatorAcknowledgedRisks;
    status = AutomationReleaseStatus.fromJson(
      automationReleaseStatusJson(releaseEnabled: true),
    );
    return status;
  }

  @override
  Future<AutomationReleaseStatus> disarmAutomationRelease({
    String? reason,
    String language = 'ko',
    String locale = 'ko-KR',
  }) async {
    disarmCalls += 1;
    status = AutomationReleaseStatus.fromJson(
      automationReleaseStatusJson(releaseEnabled: false),
    );
    return status;
  }

  @override
  Future<AutomationReleaseCycleResult> runAutomationReleaseCycleOnce({
    String mode = 'monitoring',
    bool operatorAcknowledgedRisks = false,
    String triggerSource = 'manual_release_cycle',
    String provider = 'kis',
    String market = 'KR',
    String language = 'ko',
    String locale = 'ko-KR',
  }) async {
    cycleCalls += 1;
    lastCycleMode = mode;
    lastCycleAcknowledged = operatorAcknowledgedRisks;
    cycle = AutomationReleaseCycleResult.fromJson(
      automationReleaseCycleJson(resultStatus: 'dry_run_completed'),
    );
    return cycle;
  }

  @override
  Future<AutomationModeControlStatus> fetchAutomationModeStatus() async {
    return AutomationModeControlStatus.fromJson(automationModeStatusJson());
  }

  @override
  Future<AutomationSoakStatus> fetchAutomationSoakStatus() async {
    return AutomationSoakStatus.fromJson(automationSoakStatusJson());
  }

  @override
  Future<BrokerSyncWatchdogResult> fetchBrokerSyncWatchdogLatest({
    String provider = 'kis',
    String market = 'KR',
  }) async {
    return BrokerSyncWatchdogResult.fromJson(brokerSyncWatchdogJson());
  }

  @override
  Future<PortfolioOrchestratorResult> fetchPortfolioOrchestratorLatest({
    String provider = 'kis',
    String market = 'KR',
  }) async {
    return PortfolioOrchestratorResult.fromJson(portfolioOrchestratorJson());
  }

  @override
  Future<AutoBuyLivePhase1Result> fetchAutoBuyLivePhase1Status({
    String provider = 'kis',
    String market = 'KR',
  }) async {
    return AutoBuyLivePhase1Result.fromJson(autoBuyLivePhase1Json());
  }

  @override
  Future<AutoSellLivePhase1Result> fetchAutoSellLivePhase1Status({
    String provider = 'kis',
    String market = 'KR',
  }) async {
    return AutoSellLivePhase1Result.fromJson(autoSellLivePhase1Json());
  }

  @override
  Future<OpsProductionReadiness> fetchOpsProductionReadiness({
    String provider = 'kis',
    String market = 'KR',
    bool includeDetails = true,
    bool includeRaw = false,
    int days = 7,
    bool includeRecent = true,
  }) async {
    return OpsProductionReadiness.fromJson({
      'generated_at': '2026-07-13T00:00:00Z',
      'timezone': 'Asia/Seoul',
      'provider': provider,
      'market': market,
      'overall_status': 'ready',
      'readiness_score': 100,
      'summary': const {
        'ready_count': 1,
        'warning_count': 0,
        'blocked_count': 0,
        'unknown_count': 0,
        'critical_block_count': 0,
      },
      'checklist': const [],
      'blocking_reasons': const [],
      'warning_reasons': const [],
      'next_safe_actions': const [],
      'safety_flags': const {},
      'runtime_settings': const {},
      'broker_status': const {},
      'scheduler_status': const {},
      'order_metrics': const {},
      'position_metrics': const {},
      'alert_metrics': const {},
      'agent_chat': const {},
      'recent_activity': const {},
    });
  }
}
