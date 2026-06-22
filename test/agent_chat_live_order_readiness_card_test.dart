import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/agent_chat_live_order_readiness_card.dart';
import 'package:auto_invest_dashboard/models/agent_chat_live_order_readiness.dart';

void main() {
  testWidgets('readiness card shows blocked state and blocking reasons',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: AgentChatLiveOrderReadinessCard(
              readiness: _readiness(ready: false),
              loading: false,
              error: null,
              applyingPreset: null,
              onRefresh: () async => const ActionResult(
                success: true,
                message: 'refreshed',
              ),
              onApplyPreset: (_) async => const ActionResult(
                success: true,
                message: 'applied',
              ),
            ),
          ),
        ),
      ),
    );

    expect(find.byKey(const ValueKey('agent-chat-live-order-readiness-card')),
        findsOneWidget);
    expect(find.text('BLOCKED'), findsOneWidget);
    expect(find.text('Blocking Reasons'), findsOneWidget);
    expect(find.textContaining('dry_run is ON'), findsOneWidget);
    expect(find.text('READINESS ONLY'), findsOneWidget);
    expect(find.text('NO AUTO SCHEDULER'), findsOneWidget);
    expect(find.text('NO BACKGROUND ORDERS'), findsOneWidget);
  });

  testWidgets('preset button opens confirmation dialog and applies preset',
      (tester) async {
    String? appliedPreset;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: AgentChatLiveOrderReadinessCard(
              readiness: _readiness(ready: false),
              loading: false,
              error: null,
              applyingPreset: null,
              onRefresh: () async => const ActionResult(
                success: true,
                message: 'refreshed',
              ),
              onApplyPreset: (preset) async {
                appliedPreset = preset;
                return const ActionResult(
                  success: true,
                  message: 'preset applied',
                );
              },
            ),
          ),
        ),
      ),
    );

    await tester.tap(
      find.byKey(
        const ValueKey(
          'agent-chat-live-order-preset-chat_confirmed_buy_only',
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey('agent-chat-live-order-preset-confirm-dialog')),
      findsOneWidget,
    );
    expect(
      find.textContaining('No order is submitted'),
      findsOneWidget,
    );

    await tester.tap(
      find.byKey(const ValueKey('agent-chat-live-order-preset-apply')),
    );
    await tester.pumpAndSettle();

    expect(appliedPreset, 'chat_confirmed_buy_only');
  });

  testWidgets('full guarded preset shows stronger warning', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: AgentChatLiveOrderReadinessCard(
              readiness: _readiness(ready: true),
              loading: false,
              error: null,
              applyingPreset: null,
              onRefresh: () async => const ActionResult(
                success: true,
                message: 'refreshed',
              ),
              onApplyPreset: (_) async => const ActionResult(
                success: true,
                message: 'applied',
              ),
            ),
          ),
        ),
      ),
    );

    await tester.tap(
      find.byKey(
        const ValueKey(
          'agent-chat-live-order-preset-chat_confirmed_full_guarded',
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.textContaining('both buy and sell chat-confirmed orders'),
      findsOneWidget,
    );
    expect(
      find.textContaining('No order is submitted by this preset'),
      findsOneWidget,
    );
  });

  testWidgets('card does not render forbidden operational buttons',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: AgentChatLiveOrderReadinessCard(
            readiness: _readiness(ready: false),
            loading: false,
            error: null,
            applyingPreset: null,
            onRefresh: () async => const ActionResult(
              success: true,
              message: 'refreshed',
            ),
            onApplyPreset: (_) async => const ActionResult(
              success: true,
              message: 'applied',
            ),
          ),
        ),
      ),
    );

    expect(find.text('Submit order'), findsNothing);
    expect(find.text('Disable dry-run'), findsNothing);
    expect(find.text('Turn off kill switch'), findsNothing);
    expect(find.text('Enable scheduler real order'), findsNothing);
    expect(find.text('Enable KIS auto-buy scheduler'), findsNothing);
  });
}

AgentChatLiveOrderReadiness _readiness({required bool ready}) {
  return AgentChatLiveOrderReadiness.fromJson({
    'status': ready ? 'ready' : 'blocked',
    'ready': ready,
    'ready_for_chat_confirmed_live_order': ready,
    'provider': 'kis',
    'market': 'KR',
    'summary': ready ? 'Ready.' : 'Blocked.',
    'checks': [
      {
        'key': 'dry_run',
        'label': 'Dry Run',
        'ok': ready,
        'value': !ready,
        'severity': ready ? 'ok' : 'blocking',
        'message': ready ? 'OK.' : 'dry_run is ON.',
      },
      {
        'key': 'agent_chat_live_order_enabled',
        'label': 'Agent Chat Live Order',
        'ok': ready,
        'value': ready,
        'severity': ready ? 'ok' : 'blocking',
        'message': ready ? 'OK.' : 'Agent Chat live order is OFF.',
      },
      {
        'key': 'scheduler_real_orders_disabled',
        'label': 'Scheduler Real Orders Disabled',
        'ok': true,
        'value': true,
        'severity': 'ok',
        'message': 'OK.',
      },
    ],
    'limits': {
      'max_orders_per_day': 1,
      'orders_used_today': 0,
      'orders_remaining_today': 1,
      'max_notional_krw': 50000,
      'max_notional_pct': 0.03,
    },
    'capabilities': {
      'buy_enabled': ready,
      'sell_enabled': false,
      'market_order_enabled': true,
      'limit_order_enabled': false,
    },
    'safety': {
      'read_only': true,
      'real_order_submitted': false,
      'validation_called': false,
      'scheduler_changed': false,
    },
  });
}
