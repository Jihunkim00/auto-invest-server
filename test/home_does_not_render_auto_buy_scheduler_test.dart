import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_screen.dart';

void main() {
  testWidgets('Home default view does not render auto buy scheduler or queue',
      (tester) async {
    final controller = DashboardController(_NoopApiClient(), autoload: false)
      ..activeAgentConversationKey = 'home-pr78-test';

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: DashboardScreen(controller: controller)),
    ));
    await tester.pump();

    expect(
        find.byKey(const ValueKey('auto-buy-scheduler-panel')), findsNothing);
    expect(find.byKey(const ValueKey('auto-buy-promotion-queue-panel')),
        findsNothing);
    expect(find.text('Auto Buy Scheduler'), findsNothing);
    expect(find.text('Auto Buy Promotion Queue'), findsNothing);

    controller.dispose();
  });
}

class _NoopApiClient extends ApiClient {}
