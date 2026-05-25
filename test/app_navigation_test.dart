import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/app.dart';
import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';

void main() {
  testWidgets('Bottom navigation uses 4 mobile tabs and language toggle',
      (tester) async {
    final controller = DashboardController(ApiClient(), autoload: false);

    await tester
        .pumpWidget(MaterialApp(home: AutoInvestApp(controller: controller)));
    await tester.pumpAndSettle();

    expect(find.text('Home'), findsWidgets);
    expect(find.text('Trading'), findsOneWidget);
    expect(find.text('Analysis'), findsOneWidget);
    expect(find.text('Logs'), findsOneWidget);
    expect(find.byKey(const ValueKey('language-toggle-chip')), findsOneWidget);
  });

  testWidgets('Global broker selector drives screen context', (tester) async {
    final controller = DashboardController(ApiClient(), autoload: false);

    await tester
        .pumpWidget(MaterialApp(home: AutoInvestApp(controller: controller)));
    await tester.pumpAndSettle();

    expect(
        find.byKey(const ValueKey('global-broker-selector')), findsOneWidget);
    expect(controller.selectedProvider, SelectedProvider.alpaca);

    await tester.tap(find.descendant(
      of: find.byKey(const ValueKey('global-broker-selector')),
      matching: find.text('KIS'),
    ));
    await tester.pumpAndSettle();

    expect(controller.selectedProvider, SelectedProvider.kis);

    await tester.tap(find.text('Watchlist'));
    await tester.pumpAndSettle();
    expect(find.text('KIS / KR'), findsWidgets);
    expect(find.byKey(const ValueKey('global-broker-selector')), findsNothing);

    await tester.tap(find.text('Trading'));
    await tester.pumpAndSettle();
    expect(find.text('KIS Analyze & Buy'), findsOneWidget);
    expect(find.text('KIS Guarded Trading'), findsNothing);
    expect(find.text('KIS / KR'), findsWidgets);

    await tester.tap(find.text('Settings'));
    await tester.pumpAndSettle();
    expect(find.text('KIS safety and manual live status.'), findsOneWidget);
    expect(find.byKey(const ValueKey('global-broker-selector')), findsNothing);
  });
}


void _toggleLanguage(DashboardController controller){controller.toggleUiLanguage();}
