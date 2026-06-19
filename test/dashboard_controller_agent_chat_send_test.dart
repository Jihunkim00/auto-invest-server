import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/models/agent_chat_conversation.dart';
import 'package:auto_invest_dashboard/models/agent_chat_message.dart';
import 'package:auto_invest_dashboard/models/agent_chat_send_response.dart';
import 'package:auto_invest_dashboard/models/agent_command.dart';
import 'package:auto_invest_dashboard/models/agent_plan.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_result.dart';
import 'package:auto_invest_dashboard/models/order_validation_result.dart';

void main() {
  test('sendAgentMessage uses /agent/chat/send first', () async {
    final api = _ChatSendFakeApi();
    final controller = DashboardController(api, autoload: false);

    final result = await controller.sendAgentMessage('삼전 현재가');

    expect(result.success, isTrue);
    expect(api.chatSendCalls, 1);
    expect(api.parseCalls, 0);
    expect(api.createPlanCalls, 0);
    expect(api.validationCalls, 0);
    expect(api.submitCalls, 0);
    expect(controller.activeAgentConversationKey, 'agent_conv_created_1');
    expect(controller.latestAgentPlan, isNull);
    expect(controller.agentMessages.last.text, contains('현재가'));
    expect(controller.agentMessages.last.safetyBadges, contains('READ ONLY'));
    expect(
        controller.agentMessages.last.safetyBadges, contains('NO AUTO SUBMIT'));

    controller.dispose();
  });

  test('chat send failure falls back to legacy parse flow safely', () async {
    final api = _ChatSendFakeApi(failChatSend: true);
    final controller = DashboardController(api, autoload: false);

    final result = await controller.sendAgentMessage('show my positions');

    expect(result.success, isTrue);
    expect(api.chatSendCalls, 1);
    expect(api.parseCalls, 1);
    expect(api.createPlanCalls, 1);
    expect(api.validationCalls, 0);
    expect(api.submitCalls, 0);
    expect(controller.latestAgentPlan?.id, 88);
    expect(controller.kisLiveConfirmation, isFalse);

    controller.dispose();
  });

  test(
      'manual ticket response shows prefill state without validation or submit',
      () async {
    final api = _ChatSendFakeApi(response: _manualTicketResponse());
    final controller = DashboardController(api, autoload: false)
      ..kisLiveConfirmation = true;

    final result = await controller.sendAgentMessage('삼성전자 3만원 매수 티켓 준비해줘');

    expect(result.success, isTrue);
    expect(api.validationCalls, 0);
    expect(api.submitCalls, 0);
    expect(controller.latestAgentPlan?.canPrepareManualTicket, isTrue);
    expect(controller.agentMessages.last.prefillAvailable, isTrue);
    expect(
        controller.agentMessages.last.safetyBadges, contains('PREFILL ONLY'));
    expect(controller.kisLiveConfirmation, isTrue);

    controller.dispose();
  });
}

class _ChatSendFakeApi extends ApiClient {
  _ChatSendFakeApi({this.failChatSend = false, AgentChatSendResponse? response})
      : response = response ?? _priceResponse();

  final bool failChatSend;
  final AgentChatSendResponse response;
  int chatSendCalls = 0;
  int parseCalls = 0;
  int createPlanCalls = 0;
  int appendCalls = 0;
  int validationCalls = 0;
  int submitCalls = 0;

  @override
  Future<List<AgentChatConversation>> fetchAgentChatConversations({
    String status = 'active',
    int limit = 20,
  }) async {
    return const [];
  }

  @override
  Future<AgentChatConversation> createAgentChatConversation({
    String? title,
    String source = 'flutter_dashboard',
    Map<String, dynamic>? metadata,
  }) async {
    return AgentChatConversation(
      id: 1,
      conversationKey: 'agent_conv_created_1',
      title: title,
      status: 'active',
      source: source,
      metadata: metadata ?? const {},
      createdAt: DateTime.utc(2026, 6, 18),
      updatedAt: DateTime.utc(2026, 6, 18),
      lastMessageAt: DateTime.utc(2026, 6, 18),
    );
  }

  @override
  Future<AgentChatSendResponse> sendAgentChatMessage({
    required String message,
    String? conversationKey,
    Map<String, dynamic>? context,
    bool autoCreateConversation = true,
  }) async {
    chatSendCalls += 1;
    if (failChatSend) {
      throw const ApiRequestException('chat send failed');
    }
    return response;
  }

  @override
  Future<AgentChatMessage> appendAgentChatMessage({
    required String conversationKey,
    required String role,
    required String text,
    String messageType = 'plain_text',
    String status = 'completed',
    int? commandLogId,
    int? planId,
    int? planRunId,
    int? authApprovalRequestId,
    int? prefillSourcePlanId,
    String? modelName,
    String? parserStatus,
    Map<String, dynamic>? safety,
    Map<String, dynamic>? metadata,
  }) async {
    appendCalls += 1;
    return AgentChatMessage(
      id: 'persisted-$appendCalls',
      role: agentChatRoleFromString(role),
      text: text,
      createdAt: DateTime.utc(2026, 6, 18, 9, appendCalls),
      status: agentChatStatusFromString(status),
      conversationKey: conversationKey,
      messageType: messageType,
      commandLogId: commandLogId,
      planId: planId,
      runId: planRunId,
      modelName: modelName,
      parserStatus: parserStatus,
      metadata: metadata ?? const {},
    );
  }

  @override
  Future<AgentCommandParseResult> parseAgentCommand({
    required String message,
    String? conversationId,
    Map<String, dynamic>? context,
  }) async {
    parseCalls += 1;
    return AgentCommandParseResult.fromJson({
      'status': 'parsed',
      'parser_status': 'fallback',
      'command_log_id': 77,
      'command': {
        'schema_version': 'autoinvest_command_v1',
        'command_type': 'SHOW_POSITIONS',
        'domain': 'position',
        'intent': 'show_positions',
        'market': 'KR',
        'provider': 'kis',
        'side': 'none',
        'risk_level': 'read_only',
        'requires_auth': false,
        'user_visible_summary': 'Command parsed.',
        'execution_policy': {'allow_live_order': false},
        'safety': {'real_order_submitted': false},
      },
      'safety': {'real_order_submitted': false},
    });
  }

  @override
  Future<AgentPlanCreateResult> createAgentPlanFromCommand(
    int commandLogId, {
    String? planTitle,
    int expiresInMinutes = 60,
  }) async {
    createPlanCalls += 1;
    return AgentPlanCreateResult(
      status: 'plan_created',
      plan: _safePlan(),
      auth: const {'required': false},
      safety: const {'real_order_submitted': false},
    );
  }

  @override
  Future<OrderValidationResult> validateKisOrder({
    required String symbol,
    required String side,
    required int qty,
    String orderType = 'market',
    Map<String, dynamic>? sourceMetadata,
  }) async {
    validationCalls += 1;
    throw const ApiRequestException('validation should not run');
  }

  @override
  Future<KisManualOrderResult> submitKisManualOrder({
    required String symbol,
    required String side,
    required int qty,
    String orderType = 'market',
    required bool confirmLive,
    Map<String, dynamic>? sourceMetadata,
  }) async {
    submitCalls += 1;
    throw const ApiRequestException('submit should not run');
  }
}

AgentChatSendResponse _priceResponse() {
  return AgentChatSendResponse.fromJson({
    'conversation_key': 'agent_conv_created_1',
    'intent': {
      'category': 'read_only_price_query',
      'supported': true,
      'confidence': 0.9,
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
      'text': '삼성전자는 005930으로 조회됩니다. 현재가는 ₩72,000입니다.',
      'answer_type': 'read_only_result',
    },
    'data': {
      'price': {'symbol': '005930', 'price': 72000, 'currency': 'KRW'},
    },
    'available_actions': [],
    'safety': _safeSafety(readOnly: true),
  });
}

AgentChatSendResponse _manualTicketResponse() {
  return AgentChatSendResponse.fromJson({
    'conversation_key': 'agent_conv_created_1',
    'intent': {
      'category': 'manual_ticket_request',
      'supported': true,
      'confidence': 0.9,
      'market': 'KR',
      'provider': 'kis',
      'symbol': '005930',
      'side': 'buy',
      'notional': 30000,
      'requires_plan': true,
      'requires_auth': false,
      'requires_manual_confirmation': true,
      'fallback_used': true,
      'parser_status': 'fallback',
    },
    'answer': {
      'role': 'assistant',
      'text': '수동 주문 티켓 검토 계획을 준비했습니다. 주문은 실행하지 않았습니다.',
      'answer_type': 'manual_ticket_prepared',
    },
    'data': {'prefill_ready': true},
    'plan': _manualPlan().raw,
    'available_actions': ['prepare_manual_ticket', 'open_trading_ticket'],
    'safety': _safeSafety(readOnly: false),
  });
}

Map<String, dynamic> _safeSafety({required bool readOnly}) {
  return {
    'read_only': readOnly,
    'safe_execution_only': true,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'validation_called': false,
    'setting_changed': false,
    'scheduler_changed': false,
    'confirm_live_auto_checked': false,
  };
}

AgentPlan _safePlan() {
  return AgentPlan.fromJson({
    'id': 88,
    'plan_key': 'plan_safe',
    'command_type': 'SHOW_POSITIONS',
    'domain': 'position',
    'intent': 'show_positions',
    'market': 'KR',
    'provider': 'kis',
    'side': 'none',
    'risk_level': 'read_only',
    'status': 'ready',
    'plan_title': 'Show positions',
    'plan_summary': 'Review positions.',
    'user_visible_summary': 'Positions can be reviewed safely.',
    'command': {'command_type': 'SHOW_POSITIONS'},
    'execution_policy': {'allow_live_order': false},
    'safety': {'real_order_submitted': false},
    'requires_auth': false,
    'requires_recent_validation': false,
    'requires_confirm_live': false,
    'allow_live_order': false,
    'allow_setting_change': false,
    'allow_scheduler_change': false,
  });
}

AgentPlan _manualPlan() {
  return AgentPlan.fromJson({
    'id': 89,
    'plan_key': 'plan_manual',
    'command_type': 'PREPARE_MANUAL_BUY_TICKET',
    'domain': 'order',
    'intent': 'prepare_manual_buy_ticket',
    'market': 'KR',
    'provider': 'kis',
    'symbol': '005930',
    'side': 'buy',
    'risk_level': 'prefill_only',
    'status': 'ready_for_review',
    'plan_title': 'Prepare manual ticket',
    'plan_summary': 'Prepare ticket only.',
    'user_visible_summary': 'Manual ticket only.',
    'command': {
      'budget': {'amount': 30000, 'currency': 'KRW'}
    },
    'execution_policy': {'allow_live_order': false},
    'safety': {'real_order_submitted': false},
    'requires_auth': false,
    'requires_recent_validation': false,
    'requires_confirm_live': false,
    'allow_live_order': false,
    'allow_setting_change': false,
    'allow_scheduler_change': false,
  });
}
