import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/features/dashboard/widgets/agent_chat_tool_result_card.dart';
import 'package:auto_invest_dashboard/models/agent_chat_tool_result.dart';

import 'auto_buy_operations_model_test.dart';

void main() {
  testWidgets('Agent Chat renders auto buy operations result card',
      (tester) async {
    final card = AgentChatResultCard.fromJson({
      'card_type': 'strategy_auto_buy_operations_status',
      'title': 'Auto Buy Operations',
      'subtitle': 'SAFE',
      'primary_value': 'LIVE_READINESS_BLOCKED',
      'badges': [
        'AUTO BUY OPS',
        'READ ONLY',
        'NO CHAT EXECUTION',
        'NO VALIDATION',
        'NO BROKER SUBMIT',
        'SCHEDULED DRY RUN',
        'PROMOTION ONLY',
        'NO LIVE SCHEDULER',
        'NO AUTO RETRY',
      ],
      'rows': [
        {'label': 'Next action', 'value': 'enable_prerequisites_manually'},
        {'label': 'Block reason', 'value': 'target_risk_rejected'},
      ],
      'data': autoBuyOperationsJson(
        ready: false,
        stage: 'live_readiness_blocked',
        nextAction: 'enable_prerequisites_manually',
      ),
    });

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(
        body: AgentChatToolResultCardList(
          cards: [card],
          followUpSuggestions: const [],
        ),
      ),
    ));

    expect(find.byKey(const ValueKey('agent-chat-auto-buy-operations-card')),
        findsOneWidget);
    expect(find.text('Auto Buy Operations'), findsOneWidget);
    expect(find.text('LIVE_READINESS_BLOCKED'), findsOneWidget);
    expect(find.text('AUTO BUY OPS'), findsOneWidget);
    expect(find.text('READ ONLY'), findsOneWidget);
    expect(find.text('NO CHAT EXECUTION'), findsOneWidget);
    expect(find.text('NO VALIDATION'), findsOneWidget);
    expect(find.text('NO BROKER SUBMIT'), findsOneWidget);
  });
}
