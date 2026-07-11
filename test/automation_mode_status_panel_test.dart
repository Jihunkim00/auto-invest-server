import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/i18n/app_language.dart';
import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/logs/widgets/automation_mode_status_panel.dart';
import 'package:auto_invest_dashboard/models/automation_mode_control.dart';

import 'automation_mode_control_model_test.dart';

void main() {
  testWidgets('logs automation mode panel is read-only and refreshes status',
      (tester) async {
    await _setLargeView(tester);
    final api = _FakeAutomationModeStatusApi();
    final controller = DashboardController(
      api,
      autoload: false,
      initialLanguage: AppLanguage.english,
    )..automationModeStatus = api.status;

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: AutomationModeStatusPanel(controller: controller)),
    ));

    expect(find.text('Automation Mode Control'), findsOneWidget);
    expect(find.text('Live Order Eligibility'), findsOneWidget);
    expect(find.text('Current Mode'), findsOneWidget);
    expect(find.text('Effective Status'), findsOneWidget);
    expect(find.text('Order / Position Sync Health'), findsOneWidget);
    expect(find.text('Sync Healthy'), findsOneWidget);
    expect(find.text('No Broker Submit'), findsOneWidget);
    expect(find.text('Change with Risk Acknowledgement'), findsNothing);
    expect(find.text('Turn Off Automation'), findsNothing);

    await tester
        .tap(find.byKey(const ValueKey('automation-mode-status-refresh')));
    await tester.pumpAndSettle();

    expect(api.statusCalls, 1);
    controller.dispose();
  });
}

Future<void> _setLargeView(WidgetTester tester) async {
  tester.view.physicalSize = const Size(1200, 2600);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

class _FakeAutomationModeStatusApi extends ApiClient {
  AutomationModeControlStatus status = AutomationModeControlStatus.fromJson(
    automationModeStatusJson(
      mode: 'monitor_only',
      label: 'Monitoring Only',
      effectiveStatus: 'monitoring',
      blockingReasons: const ['phase1_live_disabled_in_monitor_only'],
      warningReasons: const ['kis_real_orders_are_separate'],
    ),
  );
  int statusCalls = 0;

  @override
  Future<AutomationModeControlStatus> fetchAutomationModeStatus() async {
    statusCalls += 1;
    return status;
  }
}
