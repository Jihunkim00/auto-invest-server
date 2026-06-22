import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/agent_chat_live_order_action.dart';
import 'package:auto_invest_dashboard/models/agent_chat_message.dart';
import 'package:auto_invest_dashboard/models/agent_chat_send_response.dart';

void main() {
  test('AgentChatLiveOrderAction parses pending confirmation payload', () {
    final action = AgentChatLiveOrderAction.fromJson(_actionJson());

    expect(action.actionId, 67);
    expect(action.status, 'pending_confirmation');
    expect(action.displayName, 'Samsung Electronics(005930)');
    expect(action.isPending, isTrue);
    expect(action.quantity, 1);
    expect(action.estimatedNotional, 72000);
    expect(action.confirmationToken, 'scope-token');
    expect(action.brokerStatus, 'ACCEPTED');
    expect(action.internalStatus, 'SUBMITTED');
    expect(action.lastSyncAt, '2026-06-21T12:05:00Z');
    expect(action.safetyControls['dry_run'], isFalse);
    expect(action.audit['requested_by'], 'agent_chat');
    expect(action.safety['validation_called'], isFalse);
    expect(action.raw['symbol'], '005930');
  });

  test('AgentChatSendResponse and AgentChatMessage expose live order action',
      () {
    final response = AgentChatSendResponse.fromJson({
      'conversation_key': 'conv_live_order',
      'intent': {
        'category': 'live_order_request',
        'supported': true,
        'confidence': 0.9,
        'market': 'KR',
        'provider': 'kis',
        'symbol': '005930',
        'symbol_name': 'Samsung Electronics',
        'side': 'buy',
        'requires_plan': false,
        'requires_auth': false,
        'requires_manual_confirmation': true,
        'fallback_used': true,
        'parser_status': 'fallback',
      },
      'answer': {
        'role': 'assistant',
        'text': 'Live order is ready for confirmation.',
        'answer_type': 'live_order_confirmation_required',
      },
      'live_order_action': _actionJson(),
      'available_actions': ['confirm_live_order', 'cancel_live_order'],
      'safety': {
        'read_only': false,
        'safe_execution_only': false,
        'real_order_submitted': false,
        'broker_submit_called': false,
        'manual_submit_called': false,
        'validation_called': false,
        'setting_changed': false,
        'scheduler_changed': false,
        'confirm_live_auto_checked': false,
        'mutation': false,
      },
    });

    expect(response.liveOrderAction?.actionId, 67);
    expect(response.liveOrderAction?.isPending, isTrue);

    final message = AgentChatMessage(
      id: 'assistant-1',
      role: AgentChatRole.assistant,
      text: response.answer.text,
      createdAt: DateTime.utc(2026, 6, 21),
      status: AgentChatStatus.readyForReview,
      metadata: {'live_order_action': response.liveOrderAction!.raw},
    );

    expect(message.liveOrderAction?.actionId, 67);
    expect(message.liveOrderAction?.symbol, '005930');
  });
}

Map<String, dynamic> _actionJson({String status = 'pending_confirmation'}) {
  return {
    'action_id': 67,
    'status': status,
    'action_type': 'chat_confirmed_live_order',
    'provider': 'kis',
    'market': 'KR',
    'symbol': '005930',
    'symbol_name': 'Samsung Electronics',
    'side': 'buy',
    'order_type': 'market',
    'quantity': 1,
    'currency': 'KRW',
    'estimated_price': 72000,
    'estimated_notional': 72000,
    'expires_at': '2026-06-21T12:02:00Z',
    'confirmation_phrase': 'CONFIRM 005930 BUY 1',
    'confirmation_token': 'scope-token',
    'broker_status': 'ACCEPTED',
    'internal_status': 'SUBMITTED',
    'last_sync_at': '2026-06-21T12:05:00Z',
    'audit': {'requested_by': 'agent_chat'},
    'safety_controls': {
      'dry_run': false,
      'kill_switch': false,
      'kis_enabled': true,
      'kis_real_order_enabled': true,
      'agent_chat_live_order_enabled': true,
      'market_open': true,
      'entry_allowed_now': true,
      'daily_limit_remaining': 1,
      'max_notional_limit': 50000,
    },
    'safety': {
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'validation_called': false,
    },
  };
}
