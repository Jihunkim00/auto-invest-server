import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/agent_review_queue_panel.dart';
import 'package:auto_invest_dashboard/models/agent_operations.dart';
import 'package:auto_invest_dashboard/models/agent_review_queue.dart';

void main() {
  testWidgets('review queue panel renders filters and blocked item',
      (tester) async {
    final controller = DashboardController(_QueueFakeApi('blocked'), autoload: false);

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(body: _wrap(controller)),
    ));
    await tester.pump();
    await tester.pump();

    expect(find.text('Agent Review Queue'), findsOneWidget);
    expect(find.byKey(const ValueKey('agent-review-filter-all')), findsOneWidget);
    expect(
      find.byKey(const ValueKey('agent-review-filter-auth_required')),
      findsOneWidget,
    );
    expect(find.text('SHOW_POSITIONS'), findsOneWidget);
    expect(find.text('live action blocked'), findsOneWidget);
    expect(find.text('Open Chat'), findsOneWidget);
    expect(find.text('Mark Reviewed'), findsOneWidget);
    expect(find.text('Dismiss'), findsOneWidget);
    expect(find.text('Submit Live Order'), findsNothing);
    expect(find.text('Validate'), findsNothing);
    expect(find.text('Enable Auto Buy'), findsNothing);

    controller.dispose();
  });

  testWidgets('prefill item shows Prepare Ticket without submit controls',
      (tester) async {
    final controller =
        DashboardController(_QueueFakeApi('prefill_ready'), autoload: false);

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(body: _wrap(controller)),
    ));
    await tester.pump();
    await tester.pump();

    expect(find.text('PREPARE_MANUAL_BUY_TICKET'), findsOneWidget);
    expect(find.text('Prepare Ticket'), findsOneWidget);
    expect(find.text('Submit Live Order'), findsNothing);
    expect(find.text('Validate'), findsNothing);

    controller.dispose();
  });
}

Widget _wrap(DashboardController controller) {
  return AnimatedBuilder(
    animation: controller,
    builder: (context, _) => AgentReviewQueuePanel(controller: controller),
  );
}

class _QueueFakeApi extends ApiClient {
  _QueueFakeApi(this.queueType);

  final String queueType;

  @override
  Future<AgentReviewQueue> fetchAgentReviewQueue({
    String status = 'open',
    String queueType = 'all',
    String? conversationKey,
    int limit = 50,
  }) async {
    return AgentReviewQueue.fromJson({
      'count': 1,
      'items': [_queueItem(this.queueType)],
      'safety': {'read_only': true},
    });
  }

  @override
  Future<AgentOperationsSnapshot> fetchAgentOperationsSummary() async {
    return AgentOperationsSnapshot.empty();
  }
}

Map<String, dynamic> _queueItem(String queueType) {
  return {
    'queue_id': 'plan_1',
    'queue_key': 'plan_1',
    'item_type': 'agent_plan',
    'queue_type': queueType,
    'priority': queueType == 'blocked' ? 'high' : 'medium',
    'review_status': 'open',
    'conversation_key': 'conv_1',
    'plan_id': 88,
    'command_type': queueType == 'prefill_ready'
        ? 'PREPARE_MANUAL_BUY_TICKET'
        : 'SHOW_POSITIONS',
    'market': 'KR',
    'provider': 'kis',
    'symbol': '005930',
    'side': 'buy',
    'risk_level': queueType == 'prefill_ready' ? 'prefill_only' : 'read_only',
    'status': 'ready_for_review',
    'title': 'Queue item',
    'summary': 'Review this item.',
    'blocked_reason': queueType == 'blocked' ? 'live action blocked' : null,
    'safety_badges': ['NO_AUTO_SUBMIT'],
    'can_prepare_ticket': queueType == 'prefill_ready',
    'can_run_safe_action': queueType == 'ready_for_review',
  };
}
