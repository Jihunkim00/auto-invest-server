import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/strategy_risk_state_card.dart';
import 'package:auto_invest_dashboard/models/strategy_risk.dart';

import 'strategy_risk_model_test.dart';

void main() {
  testWidgets('risk state card renders profile limits and blocked badges',
      (tester) async {
    final risk = StrategyRiskState.fromJson(
      strategyRiskJson(
        newEntriesAllowed: false,
        primaryBlockReason: 'daily_loss_limit_hit',
        flags: const [
          'daily_loss_limit_hit',
          'near_monthly_target_size_reduced',
        ],
      ),
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: StrategyRiskStateCard(
              riskState: risk,
              loading: false,
              error: null,
              onRefresh: () async => const ActionResult(
                success: true,
                message: 'refreshed',
              ),
            ),
          ),
        ),
      ),
    );

    expect(find.text('Target-Aware Risk State'), findsOneWidget);
    expect(find.text('Active profile: BALANCED'), findsOneWidget);
    expect(find.text('ENTRY BLOCKED'), findsOneWidget);
    expect(find.text('SIZE REDUCED'), findsOneWidget);
    expect(find.text('LOSS LIMIT HIT'), findsOneWidget);
    expect(find.text('Monthly return / limit'), findsOneWidget);
    expect(find.text('Daily return / limit'), findsOneWidget);
    expect(find.textContaining('₩40000'), findsOneWidget);
    expect(find.text('Submit Order'), findsNothing);
    expect(find.text('Turn Off Dry Run'), findsNothing);
    expect(find.text('Disable Kill Switch'), findsNothing);
  });
}
