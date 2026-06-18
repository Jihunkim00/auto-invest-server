import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/agent_chat_send_response.dart';

void main() {
  test('AgentChatSendResponse parses answer intent safety and optional plan', () {
    final response = AgentChatSendResponse.fromJson({
      'conversation_key': 'conv_1',
      'user_message_id': 10,
      'assistant_message_id': 11,
      'intent': {
        'category': 'read_only_price_query',
        'supported': true,
        'confidence': 0.91,
        'market': 'KR',
        'provider': 'kis',
        'symbol': '005930',
        'symbol_name': '삼성전자',
        'side': 'none',
        'requires_plan': false,
        'requires_auth': false,
        'requires_manual_confirmation': false,
        'fallback_used': true,
        'parser_status': 'fallback',
      },
      'answer': {
        'role': 'assistant',
        'text': '삼성전자는 005930으로 조회됩니다.',
        'answer_type': 'read_only_result',
      },
      'data': {
        'price': {
          'symbol': '005930',
          'price': 72000,
          'currency': 'KRW',
        },
      },
      'available_actions': ['prepare_manual_ticket'],
      'safety': {
        'read_only': true,
        'safe_execution_only': true,
        'real_order_submitted': false,
        'broker_submit_called': false,
        'manual_submit_called': false,
        'validation_called': false,
        'setting_changed': false,
        'scheduler_changed': false,
        'confirm_live_auto_checked': false,
      },
    });

    expect(response.conversationKey, 'conv_1');
    expect(response.intent.category, 'read_only_price_query');
    expect(response.intent.symbol, '005930');
    expect(response.intent.isReadOnly, isTrue);
    expect(response.answer.answerType, 'read_only_result');
    expect(response.data['price']['price'], 72000);
    expect(response.availableActions, contains('prepare_manual_ticket'));
    expect(response.safety.readOnly, isTrue);
    expect(response.safety.realOrderSubmitted, isFalse);
    expect(response.safety.validationCalled, isFalse);
  });
}
