import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/i18n/app_language.dart';
import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/logs/widgets/daily_ops_summary_panel.dart';
import 'package:auto_invest_dashboard/models/daily_ops_summary.dart';

import 'daily_ops_summary_model_test.dart';

void main() {
  testWidgets('daily operations summary panel is read-only and refreshable',
      (tester) async {
    final api = _FakeDailyOpsApiClient();
    final controller = DashboardController(
      api,
      autoload: false,
      initialLanguage: AppLanguage.english,
    );

    await tester.pumpWidget(
      MaterialApp(
        theme: ThemeData.dark(),
        home: Scaffold(
          body: SingleChildScrollView(
            child: DailyOpsSummaryPanel(controller: controller),
          ),
        ),
      ),
    );

    expect(find.text('Daily Operations Summary'), findsOneWidget);

    final panel = find.byKey(const ValueKey('daily-ops-summary-panel'));
    expect(panel, findsOneWidget);

    final runtimeStatus =
        find.byKey(const ValueKey('daily-ops-runtime-status'));
    expect(runtimeStatus, findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('daily-ops-refresh-button')));
    await tester.pumpAndSettle();

    final cards = find.byKey(const ValueKey('daily-ops-summary-cards'));
    final plValueFinder = find.descendant(
      of: cards,
      matching: find.textContaining('800'),
    );
    expect(plValueFinder, findsOneWidget);

    expect(api.fetchCalls, 1);
    expect(find.text('Broker Reconciliation'), findsOneWidget);
    expect(find.text('Attention Required'), findsOneWidget);
    expect(find.text('Orders Today'), findsOneWidget);
    expect(find.text('3'), findsWidgets);
    expect(find.text('Calculation Incomplete'), findsOneWidget);
    expect(find.text('LOCAL DB ONLY'), findsOneWidget);
    expect(find.text('NO SYNC'), findsOneWidget);
    expect(find.text('NO LIVE ORDERS'), findsOneWidget);
    expect(find.text('SCHEDULER REAL ORDERS DISABLED'), findsOneWidget);
    expect(find.byType(FilledButton), findsNothing);
    expect(find.widgetWithText(TextButton, 'Buy'), findsNothing);
    expect(find.widgetWithText(TextButton, 'Sell'), findsNothing);
    expect(find.widgetWithText(TextButton, 'Retry'), findsNothing);
    expect(find.widgetWithText(TextButton, 'Force'), findsNothing);

    controller.dispose();
  });
}

class _FakeDailyOpsApiClient extends ApiClient {
  int fetchCalls = 0;

  @override
  Future<DailyOpsSummary> fetchDailyOpsSummary({
    String provider = 'kis',
    String market = 'KR',
    String? date,
    bool includeDetails = true,
  }) async {
    fetchCalls += 1;
    return DailyOpsSummary.fromJson(
      dailyOpsSummaryJson(provider: provider, market: market),
    );
  }
}
