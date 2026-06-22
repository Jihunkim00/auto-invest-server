import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/features/dashboard/widgets/agent_chat_live_order_status_card.dart';
import 'package:auto_invest_dashboard/models/agent_chat_live_order_action.dart';

void main() {
  testWidgets('status card renders submitted and refreshes status',
      (tester) async {
    var refreshCalls = 0;

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: AgentChatLiveOrderStatusCard(
            action: _action(status: 'submitted'),
            busy: false,
            onRefresh: (_) async {
              refreshCalls += 1;
            },
            onCancel: (_) async {},
          ),
        ),
      ),
    );

    expect(find.text('Live Order Status: Submitted'), findsOneWidget);
    expect(find.text('Samsung Electronics(005930)'), findsOneWidget);
    expect(find.text('Refresh Status'), findsOneWidget);
    expect(find.text('${'Retry'} ${'Submit'}'), findsNothing);
    expect(find.text('${'Submit'} ${'Again'}'), findsNothing);

    await tester
        .tap(find.byKey(const ValueKey('agent-chat-live-order-refresh-status')));
    await tester.pumpAndSettle();

    expect(refreshCalls, 1);
  });

  testWidgets('status card shows safety controls and warning states',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: AgentChatLiveOrderStatusCard(
            action: _action(
              status: 'sync_required',
              safetyControls: const {
                'dry_run': true,
                'kill_switch': true,
                'kis_enabled': true,
                'kis_real_order_enabled': false,
                'agent_chat_live_order_enabled': true,
                'market_open': false,
                'entry_allowed_now': false,
                'daily_limit_remaining': 0,
                'max_notional_limit': 50000,
              },
            ),
            busy: false,
            onRefresh: (_) async {},
            onCancel: (_) async {},
          ),
        ),
      ),
    );

    expect(find.text('Safety Controls'), findsOneWidget);
    expect(find.text('dry_run: ON'), findsOneWidget);
    expect(find.text('kill_switch: ON'), findsOneWidget);
    expect(find.text('kis_real_order_enabled: OFF'), findsOneWidget);
    expect(find.text('market_open: OFF'), findsOneWidget);
  });

  testWidgets('cancel pending action only appears for pending status',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: AgentChatLiveOrderStatusCard(
            action: _action(status: 'filled'),
            busy: false,
            onRefresh: (_) async {},
            onCancel: (_) async {},
          ),
        ),
      ),
    );

    expect(find.text('Cancel Pending Action'), findsNothing);
  });
}

AgentChatLiveOrderAction _action({
  required String status,
  Map<String, dynamic> safetyControls = const {
    'dry_run': false,
    'kill_switch': false,
    'kis_enabled': true,
    'kis_real_order_enabled': true,
    'agent_chat_live_order_enabled': true,
    'market_open': true,
    'entry_allowed_now': true,
    'daily_limit_remaining': 1,
    'max_notional_limit': 50000,
  },
}) {
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
    'related_order_id': 123,
    'broker_order_id': 'ODNO-1',
    'broker_status': 'ACCEPTED',
    'internal_status': 'SUBMITTED',
    'last_sync_at': '2026-06-21T12:05:00Z',
    'safety_controls': safetyControls,
  });
}
