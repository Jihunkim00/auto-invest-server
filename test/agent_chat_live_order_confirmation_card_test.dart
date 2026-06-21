import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/features/dashboard/widgets/agent_chat_live_order_confirmation_card.dart';
import 'package:auto_invest_dashboard/models/agent_chat_live_order_action.dart';

void main() {
  testWidgets('live order card requires final dialog before confirm',
      (tester) async {
    var confirmCalls = 0;
    var cancelCalls = 0;
    final action = _action();

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: AgentChatLiveOrderConfirmationCard(
            action: action,
            busy: false,
            onConfirm: (_) async {
              confirmCalls += 1;
            },
            onCancel: (_) async {
              cancelCalls += 1;
            },
          ),
        ),
      ),
    );

    expect(find.text('Live Order Confirmation Required'), findsOneWidget);
    expect(find.text('Samsung Electronics(005930)'), findsOneWidget);
    expect(find.text('KRW 72,000'), findsWidgets);

    await tester.tap(find.byKey(const ValueKey('agent-chat-live-order-confirm')));
    await tester.pumpAndSettle();

    expect(
      find.text(
        'This will submit a real KIS order if backend validation and risk gates pass. Continue?',
      ),
      findsOneWidget,
    );
    expect(confirmCalls, 0);

    await tester
        .tap(find.byKey(const ValueKey('agent-chat-live-order-dialog-confirm')));
    await tester.pumpAndSettle();

    expect(confirmCalls, 1);
    expect(cancelCalls, 0);
  });

  testWidgets('live order card cancel calls cancel handler', (tester) async {
    var cancelCalls = 0;

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: AgentChatLiveOrderConfirmationCard(
            action: _action(),
            busy: false,
            onConfirm: (_) async {},
            onCancel: (_) async {
              cancelCalls += 1;
            },
          ),
        ),
      ),
    );

    await tester.tap(find.byKey(const ValueKey('agent-chat-live-order-cancel')));
    await tester.pumpAndSettle();

    expect(cancelCalls, 1);
  });

  testWidgets('live order card disables actions after terminal status',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: AgentChatLiveOrderConfirmationCard(
            action: _action(status: 'submitted'),
            busy: false,
            onConfirm: (_) async {},
            onCancel: (_) async {},
          ),
        ),
      ),
    );

    final confirm = tester.widget<FilledButton>(
      find.byKey(const ValueKey('agent-chat-live-order-confirm')),
    );
    final cancel = tester.widget<OutlinedButton>(
      find.byKey(const ValueKey('agent-chat-live-order-cancel')),
    );

    expect(confirm.onPressed, isNull);
    expect(cancel.onPressed, isNull);
  });
}

AgentChatLiveOrderAction _action({String status = 'pending_confirmation'}) {
  return AgentChatLiveOrderAction.fromJson({
    'action_id': 67,
    'status': status,
    'provider': 'kis',
    'market': 'KR',
    'symbol': '005930',
    'symbol_name': 'Samsung Electronics',
    'side': 'buy',
    'order_type': 'market',
    'quantity': 1,
    'currency': 'KRW',
    'estimated_price': 72000,
    'estimated_notional': 72000,
    'expires_at': '2026-06-21T12:02:00Z',
    'confirmation_phrase': 'CONFIRM 005930 BUY 1',
    'confirmation_token': 'scope-token',
    'safety': {'validation_called': false},
  });
}
