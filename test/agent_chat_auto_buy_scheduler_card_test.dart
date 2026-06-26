import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/features/dashboard/widgets/agent_chat_tool_result_card.dart';
import 'package:auto_invest_dashboard/models/agent_chat_tool_result.dart';

import 'auto_buy_promotion_model_test.dart';
import 'auto_buy_scheduler_model_test.dart';

void main() {
  testWidgets('Agent Chat scheduler card is read-only', (tester) async {
    final card = AgentChatResultCard.fromJson({
      'card_type': 'strategy_auto_buy_scheduler_status',
      'title': 'Scheduled Dry-Run Auto Buy',
      'subtitle': 'SAFE',
      'primary_value': 'DISABLED',
      'badges': [
        'SCHEDULED DRY RUN',
        'READ ONLY',
        'NO LIVE SCHEDULER',
        'NO VALIDATION',
        'NO BROKER SUBMIT',
        'OPERATOR CONFIRM REQUIRED',
      ],
      'rows': [
        {'label': 'Runs today', 'value': 1},
        {'label': 'Block reason', 'value': 'scheduler_disabled'},
      ],
      'data': autoBuySchedulerStatusJson(),
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

    expect(
      find.byKey(
        const ValueKey(
          'agent-chat-result-card-strategy_auto_buy_scheduler_status',
        ),
      ),
      findsOneWidget,
    );
    expect(find.text('Scheduled Dry-Run Auto Buy'), findsOneWidget);
    expect(find.text('READ ONLY'), findsOneWidget);
    expect(find.text('NO LIVE SCHEDULER'), findsOneWidget);
    expect(find.text('NO VALIDATION'), findsOneWidget);
    expect(find.text('NO BROKER SUBMIT'), findsOneWidget);
  });

  testWidgets('Agent Chat promotion queue card is promotion-only',
      (tester) async {
    final card = AgentChatResultCard.fromJson({
      'card_type': 'strategy_auto_buy_promotions',
      'title': 'Auto Buy Promotion Queue',
      'subtitle': 'SAFE',
      'primary_value': '005930',
      'badges': [
        'PROMOTION ONLY',
        'READ ONLY',
        'NO CHAT EXECUTION',
        'NO VALIDATION',
        'NO BROKER SUBMIT',
      ],
      'rows': [
        {'label': 'Visible candidates', 'value': 1},
        {'label': 'Latest status', 'value': 'pending'},
      ],
      'data': autoBuyPromotionsJson(),
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

    expect(
      find.byKey(
        const ValueKey('agent-chat-result-card-strategy_auto_buy_promotions'),
      ),
      findsOneWidget,
    );
    expect(find.text('PROMOTION ONLY'), findsOneWidget);
    expect(find.text('NO CHAT EXECUTION'), findsOneWidget);
    expect(find.text('NO VALIDATION'), findsOneWidget);
    expect(find.text('NO BROKER SUBMIT'), findsOneWidget);
  });
}
