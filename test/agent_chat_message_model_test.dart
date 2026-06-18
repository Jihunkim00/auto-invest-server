import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/agent_chat_message.dart';

void main() {
  test('AgentChatMessage parses role and status strings', () {
    final message = AgentChatMessage.fromJson({
      'id': 'm1',
      'conversation_key': 'agent_conv_1',
      'role': 'safety',
      'text': 'No auto submit.',
      'created_at': '2026-06-18T10:00:00Z',
      'status': 'prefill_ready',
      'message_type': 'manual_prefill_result',
      'command_log_id': 7,
      'plan_id': 11,
      'plan_run_id': 13,
      'prefill_available': true,
      'model_name': 'gpt-5.4-mini',
      'parser_status': 'gpt',
      'metadata': {'source': 'agent_chat'},
    });

    expect(message.role, AgentChatRole.safety);
    expect(message.status, AgentChatStatus.prefillReady);
    expect(message.conversationKey, 'agent_conv_1');
    expect(message.messageType, 'manual_prefill_result');
    expect(message.commandLogId, 7);
    expect(message.planId, 11);
    expect(message.runId, 13);
    expect(message.modelName, 'gpt-5.4-mini');
    expect(message.parserStatus, 'gpt');
    expect(message.prefillAvailable, isTrue);
    expect(message.safetyBadges, contains('GPT-BACKED'));
    expect(message.safetyBadges, contains('PREFILL ONLY'));
    expect(message.safetyBadges, contains('NO AUTO SUBMIT'));
    expect(message.toJson()['status'], 'prefill_ready');
    expect(message.toJson()['plan_run_id'], 13);
  });
}
