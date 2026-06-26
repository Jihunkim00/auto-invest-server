import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/agent_chat_send_response.dart';

void main() {
  test('parses PR65 Agent Chat response fields with Korean UTF-8 intact', () {
    final raw = {
      'conversation_key': 'conv_eval_1',
      'user_message_id': 101,
      'assistant_message_id': 102,
      'intent': {
        'category': 'manual_ticket_request',
        'supported': true,
        'confidence': 0.91,
        'market': 'US',
        'provider': 'alpaca',
        'symbol': 'AAPL',
        'symbol_name': 'Apple',
        'side': 'buy',
        'notional': 10.0,
        'currency': 'USD',
        'requires_plan': true,
        'requires_auth': false,
        'requires_manual_confirmation': true,
        'reason': 'Manual ticket only.',
        'fallback_used': true,
        'parser_status': 'fallback',
        'model_name': 'test-agent-router',
        'selected_tools': [
          {
            'tool_name': 'manual_ticket_prefill',
            'arguments': {'symbol': 'AAPL'},
            'reason': 'Manual ticket review is required.',
          }
        ],
      },
      'answer': {
        'role': 'assistant',
        'text': 'AAPL 수동 주문 티켓을 준비했습니다. 주문은 실행하지 않았습니다.',
        'answer_type': 'manual_ticket_prepared',
      },
      'data': {'prefill_ready': true},
      'available_actions': ['prepare_manual_ticket', 'open_trading_ticket'],
      'safety': {
        'read_only': false,
        'safe_execution_only': true,
        'real_order_submitted': false,
        'broker_submit_called': false,
        'manual_submit_called': false,
        'validation_called': false,
        'setting_changed': false,
        'scheduler_changed': false,
        'confirm_live_auto_checked': false,
        'broker_api_called': false,
        'agent_schedule_created': false,
        'mutation': false,
      },
      'context_snapshot': {
        'last_symbol': 'AAPL',
        'last_symbol_name': 'Apple',
        'last_market': 'US',
        'last_provider': 'alpaca',
      },
      'selected_tools': [
        {
          'tool_name': 'manual_ticket_prefill',
          'arguments': {'symbol': 'AAPL'},
          'reason': 'Manual ticket review is required.',
        }
      ],
      'tool_results': [
        {
          'tool_name': 'manual_ticket_prefill',
          'status': 'blocked',
          'result_type': 'prefill_only',
          'data': {},
          'summary': 'Tool is not allowed to auto-execute from chat.',
          'safety': {
            'read_only': true,
            'mutation': false,
            'real_order_submitted': false,
            'broker_submit_called': false,
            'manual_submit_called': false,
            'validation_called': false,
            'setting_changed': false,
            'scheduler_changed': false,
            'confirm_live_auto_checked': false,
          },
        }
      ],
      'result_cards': [
        {
          'card_type': 'analysis',
          'title': 'Safe Analysis',
          'primary_value': 'HOLD',
          'badges': ['SAFE ANALYSIS', 'NO ORDER', 'NO VALIDATION'],
          'rows': [],
          'data': {'symbol': 'AAPL'},
        }
      ],
      'follow_up_suggestions': ['이 종목 분석해줘'],
      'diagnostics': {
        'encoding_safe': true,
        'answer_contains_mojibake_marker': false,
        'router': 'fallback',
        'fallback_used': true,
        'tool_count': 1,
        'result_card_count': 1,
      },
      'answer_type': 'manual_ticket_prepared',
      'fallback_used': true,
    };

    final response = AgentChatSendResponse.fromJson(raw);

    expect(response.conversationKey, 'conv_eval_1');
    expect(response.intent.category, 'manual_ticket_request');
    expect(response.intent.symbol, 'AAPL');
    expect(response.intent.notional, 10.0);
    expect(response.intent.currency, 'USD');
    expect(response.intent.requiresManualConfirmation, isTrue);
    expect(response.answer.text, contains('주문은 실행하지 않았습니다'));
    expect(response.availableActions, contains('prepare_manual_ticket'));
    expect(response.selectedTools.single.toolName, 'manual_ticket_prefill');
    expect(response.toolResults.single.isBlocked, isTrue);
    expect(response.resultCards.single.cardType, 'analysis');
    expect(response.followUpSuggestions.single, contains('분석'));
    expect(response.diagnostics['encoding_safe'], isTrue);
    expect(response.safety.realOrderSubmitted, isFalse);
    expect(response.safety.brokerSubmitCalled, isFalse);
    expect(response.safety.manualSubmitCalled, isFalse);
    expect(response.safety.validationCalled, isFalse);
    expect(response.safety.confirmLiveAutoChecked, isFalse);
    expect(response.safety.raw['broker_api_called'], isFalse);

    final encoded = jsonEncode(raw);
    for (final marker in _mojibakeMarkers) {
      expect(encoded, isNot(contains(marker)));
    }
  });
}

final _mojibakeMarkers = List<String>.unmodifiable(
    [0x00EC, 0x00EB, 0x00EA].map(String.fromCharCode));
