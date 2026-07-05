import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/app.dart';
import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';

void main() {
  testWidgets('Bottom navigation removes Portfolio tab and keeps Watchlist',
      (tester) async {
    final controller = DashboardController(ApiClient(), autoload: false);

    await tester
        .pumpWidget(MaterialApp(home: AutoInvestApp(controller: controller)));
    await tester.pumpAndSettle();

    expect(find.text('홈'), findsWidgets);
    expect(find.text('관심종목'), findsOneWidget);
    expect(find.text('Manual'), findsNothing);
    expect(find.text('거래'), findsOneWidget);
    expect(find.text('분석'), findsOneWidget);
    expect(find.text('기록'), findsOneWidget);
    expect(find.text('설정'), findsOneWidget);
    expect(find.text('한국투자증권 자동화'), findsOneWidget);
    expect(find.text('Portfolio'), findsNothing);
  });

  testWidgets('Global broker selector drives screen context', (tester) async {
    final controller = DashboardController(ApiClient(), autoload: false);

    await tester
        .pumpWidget(MaterialApp(home: AutoInvestApp(controller: controller)));
    await tester.pumpAndSettle();

    expect(
        find.byKey(const ValueKey('global-broker-selector')), findsOneWidget);
    expect(controller.selectedProvider, SelectedProvider.alpaca);

    await tester.tap(find.byKey(const ValueKey('broker-option-kis-label')));
    await tester.pumpAndSettle();

    expect(controller.selectedProvider, SelectedProvider.kis);

    await tester.tap(find.text('관심종목'));
    await tester.pumpAndSettle();
    expect(find.text('한국투자증권 / 국내'), findsWidgets);
    expect(find.byKey(const ValueKey('global-broker-selector')), findsNothing);

    await tester.tap(find.text('거래'));
    await tester.pumpAndSettle();
    expect(find.text('KIS Analyze / Validate / Submit'), findsOneWidget);
    expect(find.text('KIS Guarded Trading'), findsNothing);
    expect(find.text('한국투자증권 / 국내'), findsWidgets);

    await tester.tap(find.text('설정'));
    await tester.pumpAndSettle();
    expect(find.text('한국투자증권 안전 상태와 수동 실거래 상태입니다.'), findsOneWidget);
    expect(find.byKey(const ValueKey('global-broker-selector')), findsNothing);
  });
}
