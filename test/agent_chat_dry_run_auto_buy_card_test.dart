import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/features/dashboard/widgets/agent_chat_tool_result_card.dart';
import 'package:auto_invest_dashboard/models/agent_chat_tool_result.dart';

void main() {
  testWidgets('agent chat dry-run card renders no-order badges',
      (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: AgentChatToolResultCardList(
            cards: [
              AgentChatResultCard(
                cardType: 'strategy_dry_run_auto_buy',
                title: 'Profile-Aware Dry-Run Auto Buy',
                subtitle: 'BALANCED',
                primaryValue: 'WOULD_BUY',
                badges: [
                  'DRY RUN ONLY',
                  'NO ORDER SUBMIT',
                  'NO VALIDATION',
                  'PROFILE AWARE',
                  'TARGET AWARE',
                ],
                rows: [
                  {'label': 'Selected symbol', 'value': '005930'},
                  {'label': 'Recommended notional', 'value': '₩30,000'},
                ],
                data: {'action': 'would_buy'},
              ),
            ],
            followUpSuggestions: [],
          ),
        ),
      ),
    );

    expect(
      find.byKey(
        const ValueKey(
          'agent-chat-dry-run-auto-buy-card-strategy_dry_run_auto_buy',
        ),
      ),
      findsOneWidget,
    );
    expect(find.text('DRY RUN ONLY'), findsOneWidget);
    expect(find.text('NO ORDER SUBMIT'), findsOneWidget);
    expect(find.text('NO VALIDATION'), findsOneWidget);
    expect(find.text('Submit Order'), findsNothing);
    expect(find.text('Confirm Live Order'), findsNothing);
  });
}
