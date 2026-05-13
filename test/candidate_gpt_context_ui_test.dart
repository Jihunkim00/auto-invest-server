import 'package:auto_invest_dashboard/features/analysis/widgets/candidate_card.dart';
import 'package:auto_invest_dashboard/models/candidate.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('Watchlist candidate UI displays GPT risk badges',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 1800);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final candidate = Candidate.fromJson({
      'symbol': 'AAPL',
      'final_entry_score': 72,
      'entry_ready': false,
      'action_hint': 'watch',
      'reason': 'Research allows visibility only.',
      'gpt_context': {
        'event_risk_level': 'high',
        'entry_penalty': 6,
        'hard_block_new_buy': true,
        'allow_sell_or_exit': true,
        'gpt_buy_score': 58,
        'gpt_sell_score': 54,
        'risk_flags': ['fx_pressure'],
        'gating_notes': ['entry penalty observed'],
        'reason': 'External risk is elevated.',
      },
    }, scoreKey: 'final_entry_score', noteKey: 'reason');

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: CandidateCard(index: 0, candidate: candidate),
        ),
      ),
    ));

    expect(find.text('Event Risk high'), findsWidgets);
    expect(find.text('Entry Penalty 6'), findsWidgets);
    expect(find.text('New Buy Blocked YES'), findsWidgets);
    expect(find.text('GPT Score 58/54'), findsWidgets);
    expect(find.text('Risk Flags 1'), findsWidgets);
    expect(find.text('GPT Risk Filter'), findsOneWidget);
    expect(find.text('External risk is elevated.'), findsOneWidget);
  });
}
