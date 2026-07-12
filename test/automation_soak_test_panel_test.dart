import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/i18n/app_language.dart';
import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/logs/widgets/automation_soak_test_panel.dart';
import 'package:auto_invest_dashboard/models/automation_mode_control.dart';
import 'package:auto_invest_dashboard/models/automation_soak_test.dart';
import 'package:auto_invest_dashboard/models/broker_sync_watchdog.dart';
import 'package:auto_invest_dashboard/models/daily_ops_summary.dart';
import 'package:auto_invest_dashboard/models/operator_alerts.dart';
import 'package:auto_invest_dashboard/models/ops_production_readiness.dart';
import 'package:auto_invest_dashboard/models/portfolio_orchestrator.dart';

import 'automation_mode_control_model_test.dart';
import 'automation_soak_test_model_test.dart';
import 'broker_sync_watchdog_model_test.dart';
import 'daily_ops_summary_model_test.dart';
import 'operator_alerts_model_test.dart';
import 'portfolio_orchestrator_model_test.dart';

void main() {
  testWidgets('automation soak panel is read-only and runs dry-run soak only',
      (tester) async {
    await _setLargeView(tester);
    final api = _FakeAutomationSoakApi();
    final controller = DashboardController(
      api,
      autoload: false,
      initialLanguage: AppLanguage.english,
    )..automationSoakStatus = api.status;

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: AutomationSoakTestPanel(controller: controller)),
    ));

    expect(find.text('Automation Soak Test'), findsOneWidget);
    expect(find.textContaining('Long-Run Stability Check'), findsWidgets);
    expect(find.text('Read Only'), findsOneWidget);
    expect(find.text('No Live Orders'), findsOneWidget);
    expect(find.text('No Order Cancel'), findsOneWidget);
    expect(find.text('No Broker Submit'), findsOneWidget);
    expect(find.text('Force Run'), findsNothing);
    expect(find.text('Submit Order'), findsNothing);
    expect(find.text('Cancel Order'), findsNothing);

    await tester.tap(find.byKey(const ValueKey('refresh-automation-soak-status')));
    await tester.pumpAndSettle();
    expect(api.statusCalls, 1);

    await tester.tap(find.byKey(const ValueKey('run-automation-soak-once')));
    await tester.pumpAndSettle();
    expect(api.runCalls, 1);
    expect(api.lastRunMode, 'dry_run_monitoring');
    expect(api.lastRunAcknowledgement, isFalse);

    controller.dispose();
  });

  testWidgets('kill latch reset requires acknowledgement', (tester) async {
    await _setLargeView(tester);
    final api = _FakeAutomationSoakApi(
      status: AutomationSoakStatus.fromJson(
        automationSoakStatusJson(
          effectiveStatus: 'kill_latched',
          killLatchActive: true,
          killLatchReason: 'broker_sync_unsafe',
          blockingReasons: const ['broker_sync_unsafe'],
          killRules: [
            automationKillRuleJson(
              ruleId: 'broker_sync_unsafe',
              triggered: true,
            ),
          ],
        ),
      ),
    );
    final controller = DashboardController(
      api,
      autoload: false,
      initialLanguage: AppLanguage.english,
    )..automationSoakStatus = api.status;

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: AutomationSoakTestPanel(controller: controller)),
    ));

    expect(find.text('Kill Latch Active'), findsWidgets);
    expect(
      tester.widget<OutlinedButton>(
        find.byKey(const ValueKey('reset-automation-soak-kill-latch')),
      ).onPressed,
      isNull,
    );

    await tester.tap(find.byKey(const ValueKey('automation-soak-reset-ack')));
    await tester.pumpAndSettle();
    expect(
      tester.widget<OutlinedButton>(
        find.byKey(const ValueKey('reset-automation-soak-kill-latch')),
      ).onPressed,
      isNotNull,
    );

    await tester.tap(
      find.byKey(const ValueKey('reset-automation-soak-kill-latch')),
    );
    await tester.pumpAndSettle();

    expect(api.resetCalls, 1);
    expect(api.lastResetAcknowledgement, isTrue);
    controller.dispose();
  });
}

Future<void> _setLargeView(WidgetTester tester) async {
  tester.view.physicalSize = const Size(1200, 2200);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

class _FakeAutomationSoakApi extends ApiClient {
  _FakeAutomationSoakApi({AutomationSoakStatus? status})
      : status = status ??
            AutomationSoakStatus.fromJson(
              automationSoakStatusJson(
                killRules: [
                  automationKillRuleJson(triggered: false),
                ],
              ),
            );

  AutomationSoakStatus status;
  int statusCalls = 0;
  int runCalls = 0;
  int resetCalls = 0;
  String? lastRunMode;
  bool? lastRunAcknowledgement;
  bool? lastResetAcknowledgement;

  @override
  Future<AutomationSoakStatus> fetchAutomationSoakStatus() async {
    statusCalls += 1;
    return status;
  }

  @override
  Future<AutomationSoakRunResult> runAutomationSoakOnce({
    String provider = 'kis',
    String market = 'KR',
    String mode = 'dry_run_monitoring',
    String triggerSource = 'manual_soak_test',
    String language = 'ko',
    String locale = 'ko-KR',
    bool operatorAcknowledgedRisks = false,
  }) async {
    runCalls += 1;
    lastRunMode = mode;
    lastRunAcknowledgement = operatorAcknowledgedRisks;
    return AutomationSoakRunResult.fromJson(automationSoakRunJson());
  }

  @override
  Future<AutomationSoakStatus> resetAutomationSoakKillLatch({
    required bool operatorAcknowledgedRisks,
    String? reason,
  }) async {
    resetCalls += 1;
    lastResetAcknowledgement = operatorAcknowledgedRisks;
    status = AutomationSoakStatus.fromJson(automationSoakStatusJson());
    return status;
  }

  @override
  Future<AutomationModeControlStatus> fetchAutomationModeStatus() async {
    return AutomationModeControlStatus.fromJson(automationModeStatusJson());
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
  Future<OpsProductionReadiness> fetchOpsProductionReadiness({
    String provider = 'kis',
    String market = 'KR',
    bool includeDetails = true,
    bool includeRaw = false,
    int days = 7,
    bool includeRecent = true,
  }) async {
    return OpsProductionReadiness.fromJson({
      'generated_at': '2026-07-12T00:00:00Z',
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
        'can_use_guarded_live_buy': false,
        'can_use_guarded_live_sell': false,
        'can_enable_scheduler_live_orders': false,
        'scheduler_real_orders_allowed': false,
        'automation_unlock_allowed': false,
      },
      'checklist': const [],
      'blocking_reasons': const [],
      'warnings': const [],
      'next_safe_actions': const [],
      'safety_flags': const {'read_only': true},
    });
  }

  @override
  Future<DailyOpsSummary> fetchDailyOpsSummary({
    String provider = 'kis',
    String market = 'KR',
    String? date,
    bool includeDetails = true,
  }) async {
    return DailyOpsSummary.fromJson(
      dailyOpsSummaryJson(provider: provider, market: market),
    );
  }

  @override
  Future<OperatorAlerts> fetchOperatorAlerts({
    String provider = 'kis',
    String market = 'KR',
    String severity = 'all',
    String status = 'active',
    int limit = 50,
    bool includeDetails = true,
  }) async {
    return OperatorAlerts.fromJson(
      operatorAlertsJson(provider: provider, market: market),
    );
  }
}
