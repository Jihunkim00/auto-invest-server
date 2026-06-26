import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/logs/widgets/auto_buy_operations_panel.dart';
import 'package:auto_invest_dashboard/models/strategy_auto_buy_operations.dart';

import 'auto_buy_operations_model_test.dart';

void main() {
  testWidgets('operations panel shows promotion pending scheduler stage',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 900);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _OperationsSchedulerApiClient();
    final controller = DashboardController(api, autoload: false);
    await controller.refreshStrategyAutoBuyOperations(silent: true);

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: AutoBuyOperationsPanel(controller: controller)),
    ));

    expect(find.text('PROMOTION PENDING'), findsWidgets);
    expect(find.text('REVIEW PROMOTION'), findsWidgets);
    expect(find.text('SCHEDULED DRY RUN'), findsOneWidget);
    expect(find.text('PROMOTION ONLY'), findsOneWidget);
    expect(find.text('NO LIVE SCHEDULER'), findsOneWidget);
    expect(find.textContaining('1 pending'), findsOneWidget);

    controller.dispose();
  });
}

class _OperationsSchedulerApiClient extends ApiClient {
  @override
  Future<StrategyAutoBuyOperationsStatus> fetchStrategyAutoBuyOperationsStatus({
    String provider = 'kis',
    String market = 'KR',
  }) async {
    return StrategyAutoBuyOperationsStatus.fromJson(
      autoBuyOperationsJson(
        stage: 'promotion_pending',
        nextAction: 'review_promotion',
        ready: true,
      ),
    );
  }
}
