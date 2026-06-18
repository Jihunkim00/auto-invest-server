import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/agent_review_queue.dart';

void main() {
  test('AgentReviewQueue parses queue items and actions', () {
    final queue = AgentReviewQueue.fromJson({
      'count': 1,
      'items': [
        {
          'queue_id': 'plan_12',
          'queue_key': 'plan_12',
          'item_type': 'agent_plan',
          'queue_type': 'manual_ticket_candidates',
          'priority': 'medium',
          'review_status': 'open',
          'conversation_key': 'conv_1',
          'command_log_id': 31,
          'plan_id': 12,
          'command_type': 'PREPARE_MANUAL_BUY_TICKET',
          'market': 'KR',
          'provider': 'kis',
          'symbol': '005930',
          'side': 'buy',
          'risk_level': 'prefill_only',
          'status': 'ready_for_review',
          'title': 'Manual buy ticket prepared',
          'summary': 'Prepare manually.',
          'safety_badges': [
            'NO_AUTO_SUBMIT',
            'MANUAL_VALIDATION_REQUIRED',
          ],
          'can_prepare_ticket': true,
          'can_run_safe_action': false,
          'created_at': '2026-06-18T10:00:00Z',
          'metadata': {'scope_hash': 'abc'},
        },
      ],
      'safety': {'read_only': true},
    });

    final item = queue.items.single;

    expect(queue.count, 1);
    expect(item.queueKey, 'plan_12');
    expect(item.canOpenChat, isTrue);
    expect(item.canPrepareTicket, isTrue);
    expect(item.canRunSafeAction, isFalse);
    expect(item.symbol, '005930');
    expect(item.safetyBadges, contains('NO_AUTO_SUBMIT'));
    expect(item.metadata['scope_hash'], 'abc');
  });
}
