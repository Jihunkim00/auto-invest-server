import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/app.dart';
import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';

void main() {
  testWidgets('user shell exposes Home, AI, and Assets only', (tester) async {
    final controller = DashboardController(ApiClient(), autoload: false);

    await tester.pumpWidget(
      MaterialApp(home: AutoInvestApp(controller: controller)),
    );
    await tester.pumpAndSettle();

    expect(find.text('AI'), findsOneWidget);
    expect(find.text('Assets'), findsOneWidget);
    expect(find.byKey(const ValueKey('home-open-admin')), findsOneWidget);
    expect(find.text('Watchlist'), findsNothing);
    expect(find.text('Manual'), findsNothing);
  });

  testWidgets('AI and Assets tabs render their user-facing entry points',
      (tester) async {
    final controller = DashboardController(ApiClient(), autoload: false);

    await tester.pumpWidget(
      MaterialApp(home: AutoInvestApp(controller: controller)),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('AI'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('ai-v2-welcome-card')), findsOneWidget);
    expect(find.byKey(const ValueKey('ai-quick-종목 분석')), findsOneWidget);

    await tester.tap(find.text('Assets'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('assets-summary-card')), findsOneWidget);
    expect(find.byKey(const ValueKey('assets-open-admin')), findsOneWidget);
  });

  testWidgets('Admin keeps legacy operational screens accessible',
      (tester) async {
    final controller = DashboardController(ApiClient(), autoload: false);

    await tester.pumpWidget(
      MaterialApp(home: AutoInvestApp(controller: controller)),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('home-open-admin')));
    await tester.pumpAndSettle();

    expect(find.text('Advanced / Admin'), findsOneWidget);
    expect(find.byKey(const ValueKey('admin-open-logs')), findsOneWidget);
    expect(find.byKey(const ValueKey('admin-open-settings')), findsOneWidget);
    expect(find.byKey(const ValueKey('admin-open-test4')), findsOneWidget);
  });
}
