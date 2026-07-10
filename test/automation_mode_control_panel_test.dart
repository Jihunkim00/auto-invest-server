import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/i18n/app_language.dart';
import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/settings/widgets/automation_mode_control_panel.dart';
import 'package:auto_invest_dashboard/models/automation_mode_control.dart';
import 'package:auto_invest_dashboard/models/ops_settings.dart';
import 'package:auto_invest_dashboard/models/portfolio_orchestrator.dart';
import 'package:auto_invest_dashboard/models/scheduler_status.dart';

import 'automation_mode_control_model_test.dart';
import 'portfolio_orchestrator_model_test.dart';

void main() {
  testWidgets('control panel renders required labels and no unsafe controls',
      (tester) async {
    await _setLargeView(tester);
    final controller = _controller(
      _FakeAutomationModeApi(
        initialStatus: AutomationModeControlStatus.fromJson(
          automationModeStatusJson(
            mode: 'phase1_live_ready',
            label: 'Phase 1 Live Ready',
            effectiveStatus: 'live_ready_blocked',
            blockingReasons: const ['dry_run_enabled'],
            warningReasons: const ['dry_run_is_separate'],
          ),
        ),
      ),
    );

    await tester.pumpWidget(_wrap(controller));

    expect(find.text('Automation Mode Control'), findsOneWidget);
    expect(find.text('Automation Off'), findsWidgets);
    expect(find.text('Monitoring Only'), findsOneWidget);
    expect(find.text('Dry-Run Automation'), findsOneWidget);
    expect(find.text('Phase 1 Live Ready'), findsWidgets);
    expect(find.text('Live Order Eligibility'), findsOneWidget);
    expect(find.text('Current Mode'), findsOneWidget);
    expect(find.text('Effective Status'), findsOneWidget);
    expect(find.text('Blocking Reasons'), findsOneWidget);
    expect(find.text('Warning Reasons'), findsOneWidget);
    expect(find.text('Next Safe Action'), findsOneWidget);
    expect(find.text('Independent Safety Gates Required'), findsWidgets);
    expect(find.text('Dry-run is separate'), findsWidgets);
    expect(find.text('Kill switch is separate'), findsOneWidget);
    expect(find.text('KIS real orders are separate'), findsOneWidget);
    expect(find.text('Turn Off Automation'), findsOneWidget);
    expect(find.text('Change with Risk Acknowledgement'), findsOneWidget);
    expect(find.text('Disabled by Default'), findsOneWidget);
    expect(find.text('No Broker Submit'), findsOneWidget);

    for (final label in [
      'Disable Kill Switch',
      'Turn Off Dry Run',
      'Enable KIS Real Orders',
      'Run Live Order',
      'Force Buy',
      'Force Sell',
      'Liquidate All',
      'Skip Gates',
      'Execute Orchestrator Live',
      'Enable Full Automation',
    ]) {
      expect(find.text(label), findsNothing);
    }

    controller.dispose();
  });

  testWidgets('phase1 mode requires acknowledgement before applying',
      (tester) async {
    await _setLargeView(tester);
    final api = _FakeAutomationModeApi();
    final controller = _controller(api);

    await tester.pumpWidget(_wrap(controller));

    await tester.tap(find.byKey(
      const ValueKey('automation-mode-option-phase1_live_ready'),
    ));
    await tester.pumpAndSettle();

    var button = tester.widget<FilledButton>(
      find.byKey(const ValueKey('automation-mode-apply-button')),
    );
    expect(button.onPressed, isNull);

    await tester.tap(
      find.byKey(const ValueKey('automation-mode-risk-ack-checkbox')),
    );
    await tester.pumpAndSettle();

    button = tester.widget<FilledButton>(
      find.byKey(const ValueKey('automation-mode-apply-button')),
    );
    expect(button.onPressed, isNotNull);

    await tester
        .tap(find.byKey(const ValueKey('automation-mode-apply-button')));
    await tester.pumpAndSettle();

    expect(api.setCalls, 1);
    expect(api.lastAutomationMode, 'phase1_live_ready');
    expect(api.lastAcknowledged, isTrue);

    controller.dispose();
  });

  testWidgets('off button calls only the dedicated off action', (tester) async {
    await _setLargeView(tester);
    final api = _FakeAutomationModeApi(
      initialStatus: AutomationModeControlStatus.fromJson(
        automationModeStatusJson(
          mode: 'dry_run_auto',
          label: 'Dry-Run Automation',
          effectiveStatus: 'dry_run_ready',
          blockingReasons: const ['phase1_live_disabled_in_dry_run_auto'],
          warningReasons: const ['dry_run_is_separate'],
        ),
      ),
    );
    final controller = _controller(api);

    await tester.pumpWidget(_wrap(controller));
    await tester.tap(find.byKey(const ValueKey('automation-mode-off-button')));
    await tester.pumpAndSettle();

    expect(api.offCalls, 1);
    expect(api.setCalls, 0);

    controller.dispose();
  });
}

Future<void> _setLargeView(WidgetTester tester) async {
  tester.view.physicalSize = const Size(1200, 5200);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

DashboardController _controller(_FakeAutomationModeApi api) {
  return DashboardController(
    api,
    autoload: false,
    initialLanguage: AppLanguage.english,
  )
    ..selectedProvider = SelectedProvider.kis
    ..selectedPortfolioMarket = PortfolioMarket.kr
    ..automationModeStatus = api.status;
}

Widget _wrap(DashboardController controller) {
  return MaterialApp(
    theme: ThemeData.dark(),
    home: Scaffold(
      body: SingleChildScrollView(
        child: AutomationModeControlPanel(controller: controller),
      ),
    ),
  );
}

class _FakeAutomationModeApi extends ApiClient {
  _FakeAutomationModeApi({AutomationModeControlStatus? initialStatus})
      : status = initialStatus ??
            AutomationModeControlStatus.fromJson(automationModeStatusJson());

  AutomationModeControlStatus status;
  int statusCalls = 0;
  int setCalls = 0;
  int offCalls = 0;
  String? lastAutomationMode;
  bool? lastAcknowledged;

  @override
  Future<AutomationModeControlStatus> fetchAutomationModeStatus() async {
    statusCalls += 1;
    return status;
  }

  @override
  Future<AutomationModeControlStatus> setAutomationMode({
    required String automationMode,
    String? reason,
    bool operatorAcknowledgedRisks = false,
    String language = 'ko',
    String locale = 'ko-KR',
  }) async {
    setCalls += 1;
    lastAutomationMode = automationMode;
    lastAcknowledged = operatorAcknowledgedRisks;
    status = AutomationModeControlStatus.fromJson(
      automationModeStatusJson(
        mode: automationMode,
        label: automationMode == 'phase1_live_ready'
            ? 'Phase 1 Live Ready'
            : 'Dry-Run Automation',
        effectiveStatus: automationMode == 'phase1_live_ready'
            ? 'live_ready_blocked'
            : 'dry_run_ready',
        blockingReasons: automationMode == 'phase1_live_ready'
            ? const ['dry_run_enabled']
            : const ['phase1_live_disabled_in_dry_run_auto'],
        warningReasons: const ['dry_run_is_separate'],
      ),
    );
    return status;
  }

  @override
  Future<AutomationModeControlStatus> turnOffAutomationMode({
    String? reason,
    String language = 'ko',
    String locale = 'ko-KR',
  }) async {
    offCalls += 1;
    status = AutomationModeControlStatus.fromJson(automationModeStatusJson());
    return status;
  }

  @override
  Future<OpsSettings> getOpsSettings() async {
    return const OpsSettings(
      schedulerEnabled: false,
      botEnabled: false,
      dryRun: true,
      killSwitch: false,
      brokerMode: 'Paper',
      defaultGateLevel: 2,
      maxDailyTrades: 5,
      maxDailyEntries: 2,
      minEntryScore: 65,
      minScoreGap: 3,
    );
  }

  @override
  Future<SchedulerStatus> fetchSchedulerStatus() async {
    return SchedulerStatus.safeDefault();
  }

  @override
  Future<PortfolioOrchestratorResult> fetchPortfolioOrchestratorLatest({
    String provider = 'kis',
    String market = 'KR',
  }) async {
    return PortfolioOrchestratorResult.fromJson(portfolioOrchestratorJson());
  }
}
