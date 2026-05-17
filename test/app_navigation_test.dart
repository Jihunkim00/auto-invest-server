import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/app.dart';
import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';

void main() {
  testWidgets('Bottom navigation removes Portfolio tab and keeps Watchlist',
      (tester) async {
    final controller = DashboardController(ApiClient(), autoload: false);

    await tester.pumpWidget(MaterialApp(home: AutoInvestApp(controller: controller)));
    await tester.pumpAndSettle();

    expect(find.text('Home'), findsWidgets);
    expect(find.text('Watchlist'), findsOneWidget);
    expect(find.text('Manual'), findsOneWidget);
    expect(find.text('Analysis'), findsOneWidget);
    expect(find.text('Logs'), findsOneWidget);
    expect(find.text('Settings'), findsOneWidget);
    expect(find.text('Test Lab'), findsOneWidget);
    expect(find.text('Portfolio'), findsNothing);
  });
}
