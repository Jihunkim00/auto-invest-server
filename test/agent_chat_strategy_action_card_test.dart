import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/features/dashboard/widgets/agent_chat_strategy_action_card.dart';
import 'package:auto_invest_dashboard/models/agent_chat_strategy_action.dart';

void main() {
  testWidgets('strategy action card confirms and warns for aggressive profile',
      (tester) async {
    var confirmCalls = 0;
    var cancelCalls = 0;
    final action = _action();

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: AgentChatStrategyActionCard(
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
      ),
    );

    expect(find.text('Strategy Profile Confirmation Required'), findsOneWidget);
    expect(find.text('PROFILE ONLY'), findsOneWidget);
    expect(find.text('NO ORDER SUBMIT'), findsOneWidget);
    expect(find.text('CONFIRM REQUIRED'), findsOneWidget);
    expect(find.text('STRATEGY TARGET'), findsOneWidget);
    expect(find.text('AGGRESSIVE'), findsOneWidget);
    expect(find.textContaining('월 5% 이상'), findsOneWidget);
    expect(find.textContaining('주문을 즉시 실행하지 않습니다'), findsOneWidget);
    expect(find.text('Confirm Live Order'), findsNothing);
    expect(find.textContaining('dry_run'), findsNothing);
    expect(find.textContaining('kill_switch'), findsNothing);

    await tester.tap(
      find.byKey(const ValueKey('agent-chat-strategy-action-confirm')),
    );
    await tester.pumpAndSettle();

    await tester.tap(
      find.byKey(const ValueKey('agent-chat-strategy-action-cancel')),
    );
    await tester.pumpAndSettle();

    expect(confirmCalls, 1);
    expect(cancelCalls, 1);
  });

  testWidgets('strategy action card disables buttons after terminal status',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: AgentChatStrategyActionCard(
            action: _action(status: 'applied'),
            busy: false,
            onConfirm: (_) async {},
            onCancel: (_) async {},
          ),
        ),
      ),
    );

    final confirm = tester.widget<FilledButton>(
      find.byKey(const ValueKey('agent-chat-strategy-action-confirm')),
    );
    final cancel = tester.widget<OutlinedButton>(
      find.byKey(const ValueKey('agent-chat-strategy-action-cancel')),
    );

    expect(confirm.onPressed, isNull);
    expect(cancel.onPressed, isNull);
  });
}

AgentChatStrategyAction _action({String status = 'pending_confirmation'}) {
  return AgentChatStrategyAction.fromJson({
    'action_id': 70,
    'status': status,
    'action_type': 'strategy_profile_apply',
    'requested_profile': 'aggressive',
    'current_profile': 'balanced',
    'expires_at': '2026-06-23T12:00:00Z',
    'requested_profile_payload': {
      'id': 3,
      'profile_name': 'aggressive',
      'display_name': '고수익형',
      'monthly_target_return_pct': 0.06,
      'monthly_target_min_pct': 0.05,
      'monthly_target_max_pct': 0.08,
      'monthly_max_loss_pct': -0.06,
      'daily_max_loss_pct': -0.015,
      'max_order_notional_pct': 0.06,
      'max_order_notional_krw': 80000,
      'max_trades_per_day': 2,
      'max_positions': 5,
      'buy_score_threshold': 62,
      'sell_score_threshold': 55,
      'stop_loss_pct': -0.03,
      'take_profit_pct': 0.06,
      'max_holding_days': 10,
      'stop_after_monthly_target': false,
      'reduce_size_after_loss': true,
      'consecutive_loss_reduce_threshold': 3,
      'is_active': false,
      'is_builtin': true,
    },
    'safety': {
      'real_order_submitted': false,
      'validation_called': false,
      'scheduler_changed': false,
    },
  });
}
