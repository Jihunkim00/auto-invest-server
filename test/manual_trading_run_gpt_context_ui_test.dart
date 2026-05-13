import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/manual_trading_run_section.dart';
import 'package:auto_invest_dashboard/models/manual_trading_run_result.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('Manual result UI displays GPT Risk Context', (tester) async {
    tester.view.physicalSize = const Size(1200, 1800);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = DashboardController(ApiClient(), autoload: false);
    controller.manualRunResult = ManualTradingRunResult.fromJson({
      'symbol': 'AAPL',
      'gate_level': 2,
      'action': 'hold',
      'result': 'skipped',
      'reason': 'signal action is HOLD; execution skipped',
      'risk_flags': ['hold_signal'],
      'gating_notes': ['score_threshold_not_met'],
      'hard_blocked': false,
      'gpt_context': {
        'market_risk_regime': 'risk_off',
        'event_risk_level': 'high',
        'fx_risk_level': 'medium',
        'macro_risk_level': 'medium',
        'geopolitical_risk_level': 'low',
        'energy_risk_level': 'medium',
        'entry_penalty': 6,
        'hard_block_new_buy': true,
        'allow_sell_or_exit': true,
        'gpt_buy_score': 58,
        'gpt_sell_score': 54,
        'risk_flags': ['fx_pressure'],
        'gating_notes': ['GPT applied entry penalty.'],
        'reason': 'External risk is elevated.',
      },
    });

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: ManualTradingRunSection(controller: controller),
        ),
      ),
    ));

    expect(find.text('GPT Risk Context'), findsOneWidget);
    await tester.ensureVisible(find.text('GPT Risk Context'));
    await tester.tap(find.text('GPT Risk Context'));
    await tester.pumpAndSettle();

    expect(find.text('GPT Risk Filter'), findsOneWidget);
    expect(find.text('Market Risk'), findsOneWidget);
    expect(find.text('risk_off'), findsOneWidget);
    expect(find.text('New Buy Blocked'), findsOneWidget);
    expect(find.text('External risk is elevated.'), findsOneWidget);
  });
}
