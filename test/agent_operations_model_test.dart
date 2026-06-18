import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/agent_operations.dart';

void main() {
  test('AgentOperationsSnapshot parses summary and safety payload', () {
    final snapshot = AgentOperationsSnapshot.fromJson({
      'summary': {
        'total_plans': 12,
        'total_active_plans': 10,
        'active_plans': 10,
        'ready_for_review_count': 4,
        'pending_auth_count': 3,
        'blocked_count': 2,
        'prefill_ready_count': 1,
        'safe_run_completed_count': 5,
        'failed_count': 1,
        'active_conversation_count': 6,
        'archived_conversation_count': 2,
        'today_messages_count': 9,
        'latest_conversation_key': 'conv_latest',
        'latest_plan_id': 44,
        'latest_run_id': 55,
        'latest_plan_at': '2026-06-18T10:00:00Z',
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

    expect(snapshot.summary.totalPlans, 12);
    expect(snapshot.summary.pendingAuthCount, 3);
    expect(snapshot.summary.prefillReadyCount, 1);
    expect(snapshot.summary.latestConversationKey, 'conv_latest');
    expect(snapshot.summary.latestPlanId, 44);
    expect(snapshot.safety.noUnsafeAction, isTrue);
  });
}
