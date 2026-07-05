import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/i18n/app_language.dart';
import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/logs/widgets/operator_alerts_panel.dart';
import 'package:auto_invest_dashboard/models/operator_alerts.dart';

import 'operator_alerts_model_test.dart';

void main() {
  testWidgets('operator alert center panel renders English alert data',
      (tester) async {
    final api = _FakeOperatorAlertsApiClient();
    final controller = DashboardController(
      api,
      autoload: false,
      initialLanguage: AppLanguage.english,
    )..selectedProvider = SelectedProvider.kis;

    await tester.pumpWidget(
      MaterialApp(
        theme: ThemeData.dark(),
        home: Scaffold(
          body: SingleChildScrollView(
            child: OperatorAlertsPanel(controller: controller),
          ),
        ),
      ),
    );

    expect(find.text('Operator Alert Center'), findsOneWidget);
    expect(find.byKey(const ValueKey('operator-alerts-panel')), findsOneWidget);

    await tester
        .tap(find.byKey(const ValueKey('operator-alerts-refresh-button')));
    await tester.pumpAndSettle();

    expect(api.fetchCalls, 1);
    expect(api.methods, ['GET']);
    expect(find.text('Risk Alerts'), findsOneWidget);
    expect(find.text('Critical'), findsWidgets);
    expect(find.text('Warning'), findsWidgets);
    expect(find.text('Sync Required'), findsOneWidget);
    expect(find.text('Rejected Order'), findsOneWidget);
    expect(find.text('Duplicate open order risk'), findsOneWidget);
    expect(find.text('Order status sync required'), findsOneWidget);
    expect(find.text('Primary Reason'), findsWidgets);
    expect(find.text('Next Safe Action'), findsWidgets);
    expect(find.text('Related Item'), findsWidgets);
    expect(find.text('Read Only'), findsOneWidget);
    expect(find.text('No Live Orders'), findsOneWidget);

    expect(find.widgetWithText(TextButton, 'Buy'), findsNothing);
    expect(find.widgetWithText(TextButton, 'Sell'), findsNothing);
    expect(find.widgetWithText(TextButton, 'Retry Order'), findsNothing);
    expect(find.widgetWithText(TextButton, 'Force Sync'), findsNothing);
    expect(find.widgetWithText(TextButton, 'Liquidate All'), findsNothing);
    expect(find.widgetWithText(TextButton, 'Auto Retry'), findsNothing);
    expect(
        find.widgetWithText(TextButton, 'Enable Live Scheduler'), findsNothing);
    expect(find.widgetWithText(TextButton, 'Change Settings'), findsNothing);
    expect(find.byType(FilledButton), findsNothing);

    controller.dispose();
  });

  testWidgets('operator alert center panel renders Korean default labels',
      (tester) async {
    final controller = DashboardController(
      _FakeOperatorAlertsApiClient(),
      autoload: false,
    )..selectedProvider = SelectedProvider.kis;

    await tester.pumpWidget(
      MaterialApp(
        theme: ThemeData.dark(),
        home: Scaffold(
          body: SingleChildScrollView(
            child: OperatorAlertsPanel(controller: controller),
          ),
        ),
      ),
    );

    expect(find.text(controller.strings.operatorAlertCenter), findsOneWidget);
    await tester
        .tap(find.byKey(const ValueKey('operator-alerts-refresh-button')));
    await tester.pumpAndSettle();

    expect(find.text(controller.strings.riskAlerts), findsOneWidget);
    expect(find.text(controller.strings.critical), findsWidgets);
    expect(find.text(controller.strings.operatorReadOnly), findsOneWidget);

    controller.dispose();
  });

  testWidgets('operator alert center panel renders empty state safely',
      (tester) async {
    final controller = DashboardController(
      _FakeOperatorAlertsApiClient(
        payload: operatorAlertsJson(activeAlertCount: 0, alerts: const []),
      ),
      autoload: false,
      initialLanguage: AppLanguage.english,
    )..selectedProvider = SelectedProvider.kis;

    await tester.pumpWidget(
      MaterialApp(
        theme: ThemeData.dark(),
        home: Scaffold(
          body: SingleChildScrollView(
            child: OperatorAlertsPanel(controller: controller),
          ),
        ),
      ),
    );

    await tester
        .tap(find.byKey(const ValueKey('operator-alerts-refresh-button')));
    await tester.pumpAndSettle();

    expect(find.text('No active alerts.'), findsOneWidget);
    expect(find.text('Operator Alert Center'), findsOneWidget);

    controller.dispose();
  });
}

class _FakeOperatorAlertsApiClient extends ApiClient {
  _FakeOperatorAlertsApiClient({Map<String, dynamic>? payload})
      : payload = payload ?? operatorAlertsJson();

  final Map<String, dynamic> payload;
  int fetchCalls = 0;
  final List<String> methods = <String>[];

  @override
  Future<OperatorAlerts> fetchOperatorAlerts({
    String provider = 'kis',
    String market = 'KR',
    String severity = 'all',
    String status = 'active',
    int limit = 50,
    bool includeDetails = true,
  }) async {
    fetchCalls += 1;
    methods.add('GET');
    return OperatorAlerts.fromJson({
      ...payload,
      'provider': provider,
      'market': market,
    });
  }
}
