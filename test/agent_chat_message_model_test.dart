import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/agent_chat_message.dart';

void main() {
  test('AgentChatMessage parses role and status strings', () {
    final message = AgentChatMessage.fromJson({
      'id': 'm1',
      'role': 'safety',
      'text': 'No auto submit.',
      'created_at': '2026-06-18T10:00:00Z',
      'status': 'prefill_ready',
      'command_log_id': 7,
      'plan_id': 11,
      'run_id': 13,
      'prefill_available': true,
      'safety_badges': ['NO AUTO SUBMIT'],
      'metadata': {'parser_status': 'fallback'},
    });

    expect(message.role, AgentChatRole.safety);
    expect(message.status, AgentChatStatus.prefillReady);
    expect(message.commandLogId, 7);
    expect(message.planId, 11);
    expect(message.runId, 13);
    expect(message.prefillAvailable, isTrue);
    expect(message.safetyBadges, contains('NO AUTO SUBMIT'));
    expect(message.toJson()['status'], 'prefill_ready');
  });
}
