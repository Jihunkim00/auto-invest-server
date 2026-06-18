import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/agent_operations_summary_card.dart';
import 'package:auto_invest_dashboard/models/agent_operations.dart';

void main() {
  testWidgets('summary card renders counts and safety badges', (tester) async {
    final controller = DashboardController(_SummaryFakeApi(), autoload: false);

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(body: _wrap(controller)),
    ));
    await tester.pump();
    await tester.pump();

    expect(find.text('Agent Operations'), findsOneWidget);
    expect(find.text('READ ONLY'), findsOneWidget);
    expect(find.text('NO AUTO SUBMIT'), findsOneWidget);
    expect(find.text('SAFE REVIEW QUEUE'), findsOneWidget);
    expect(find.text('Active Plans'), findsOneWidget);
    expect(find.text('Pending Auth'), findsOneWidget);
    expect(find.text('Blocked'), findsOneWidget);
    expect(find.text('Prefill Ready'), findsOneWidget);
    expect(find.text('Safe Runs'), findsOneWidget);
    expect(find.text('Active Chats'), findsOneWidget);
    expect(find.text('7'), findsOneWidget);
    expect(find.text('2'), findsWidgets);

    controller.dispose();
  });
}

Widget _wrap(DashboardController controller) {
  return AnimatedBuilder(
    animation: controller,
    builder: (context, _) => AgentOperationsSummaryCard(controller: controller),
  );
}

class _SummaryFakeApi extends ApiClient {
  @override
  Future<AgentOperationsSnapshot> fetchAgentOperationsSummary() async {
    return AgentOperationsSnapshot.fromJson({
      'summary': {
        'active_plans': 7,
        'pending_auth_count': 2,
        'blocked_count': 1,
        'prefill_ready_count': 3,
        'safe_run_completed_count': 4,
        'failed_count': 0,
        'active_conversation_count': 5,
      },
      'safety': {
        'read_only': true,
        'real_order_submitted': false,
        'broker_submit_called': false,
        'manual_submit_called': false,
        'validation_called': false,
        'setting_changed': false,
        'scheduler_changed': false,
      },
    });
  }
}
