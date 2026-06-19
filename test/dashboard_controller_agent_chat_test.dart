import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/models/agent_chat_conversation.dart';
import 'package:auto_invest_dashboard/models/agent_chat_message.dart';
import 'package:auto_invest_dashboard/models/agent_chat_send_response.dart';
import 'package:auto_invest_dashboard/models/agent_command.dart';
import 'package:auto_invest_dashboard/models/agent_live_prefill.dart';
import 'package:auto_invest_dashboard/models/agent_plan.dart';
import 'package:auto_invest_dashboard/models/agent_run.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_result.dart';
import 'package:auto_invest_dashboard/models/order_validation_result.dart';

void main() {
  test('sendAgentMessage uses chat send endpoint without legacy parse',
      () async {
    final api = _AgentChatFakeApiClient();
    final controller = DashboardController(api, autoload: false);

    final result = await controller.sendAgentMessage('show my positions');

    expect(result.success, isTrue);
    expect(api.chatSendCalls, 1);
    expect(api.chatConversationKey, 'agent_conv_created_1');
    expect(api.chatContext?['conversation_key'], 'agent_conv_created_1');
    expect(api.parseCalls, 0);
    expect(api.createPlanCalls, 0);
    expect(api.runPlanCalls, 0);
    expect(api.prepareTicketCalls, 0);
    expect(api.validationCalls, 0);
    expect(api.submitCalls, 0);
    expect(controller.latestAgentCommand, isNull);
    expect(controller.latestAgentPlan, isNull);
    expect(
      controller.agentMessages.any((message) =>
          message.role == AgentChatRole.user &&
          message.text == 'show my positions'),
      isTrue,
    );
    expect(controller.agentMessages.last.text, 'Read-only positions summary.');
    expect(controller.agentMessages.last.status, AgentChatStatus.sent);
    expect(controller.agentMessages.last.safetyBadges, contains('READ ONLY'));

    controller.dispose();
  });

  test('prepareAgentManualTicket applies prefill and keeps manual gates reset',
      () async {
    final api = _AgentChatFakeApiClient(plan: _manualPlan());
    final controller = DashboardController(api, autoload: false)
      ..latestAgentPlan = _manualPlan()
      ..orderTicketSymbol = '999999'
      ..orderTicketSide = 'sell'
      ..orderTicketQty = 5
      ..orderTicketQtyInput = '5'
      ..kisLiveConfirmation = true
      ..orderValidationResult = _validation();

    final result = await controller.prepareAgentManualTicket();

    expect(result.success, isTrue);
    expect(api.prepareTicketCalls, 1);
    expect(api.validationCalls, 0);
    expect(api.submitCalls, 0);
    expect(controller.orderTicketSymbol, '005930');
    expect(controller.orderTicketSide, 'buy');
    expect(controller.orderTicketQty, 2);
    expect(controller.orderTicketQtyInput, '2');
    expect(controller.kisLiveConfirmation, isFalse);
    expect(controller.orderValidationResult, isNull);
    expect(controller.kisManualOrderError, isNull);
    expect(controller.orderTicketSourceMetadata?['source'], 'agent_plan');
    expect(
        controller.orderTicketSourceMetadata?['manual_submit_called'], isFalse);
    expect(controller.latestAgentPrefill?.isReady, isTrue);

    controller.dispose();
  });
}

class _AgentChatFakeApiClient extends ApiClient {
  _AgentChatFakeApiClient({AgentPlan? plan}) : plan = plan ?? _safePlan();

  final AgentPlan plan;
  int chatSendCalls = 0;
  int parseCalls = 0;
  int createPlanCalls = 0;
  int runPlanCalls = 0;
  int prepareTicketCalls = 0;
  int validationCalls = 0;
  int submitCalls = 0;
  String? chatConversationKey;
  Map<String, dynamic>? chatContext;

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
    chatConversationKey = conversationKey;
    chatContext = context;
    return AgentChatSendResponse.fromJson({
      'conversation_key': conversationKey ?? 'agent_conv_created_1',
      'user_message_id': 10,
      'assistant_message_id': 11,
      'intent': {
        'category': 'read_only_positions_query',
        'supported': true,
        'confidence': 0.9,
        'market': 'KR',
        'provider': 'kis',
        'side': 'none',
        'requires_plan': false,
        'requires_auth': false,
        'requires_manual_confirmation': false,
        'fallback_used': true,
        'parser_status': 'fallback',
      },
      'answer': {
        'role': 'assistant',
        'text': 'Read-only positions summary.',
        'answer_type': 'read_only_result',
      },
      'data': {
        'positions': [],
        'count': 0,
      },
      'available_actions': [],
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
      'parser_status': 'gpt',
      'model_name': 'gpt-5.4-mini',
      'command_log_id': 77,
      'command': {
        'schema_version': 'autoinvest_command_v1',
        'command_type': plan.commandType,
        'domain': plan.domain,
        'intent': plan.intent,
        'market': plan.market,
        'provider': plan.provider,
        'symbol': plan.symbol,
        'side': plan.side,
        'risk_level': plan.riskLevel,
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
      plan: plan,
      auth: const {'required': false},
      safety: const {'real_order_submitted': false},
    );
  }

  @override
  Future<AgentPlanRunResult> runAgentPlan(
    int planId, {
    String? operatorNote,
  }) async {
    runPlanCalls += 1;
    return AgentPlanRunResult.fromJson({
      'status': 'executed_safe_action',
      'plan_id': planId,
      'plan_run_id': 12,
      'command_type': plan.commandType,
      'result': {'result_type': 'read_only_result'},
      'safety': {'real_order_submitted': false},
    });
  }

  @override
  Future<AgentLivePrefill> prepareAgentManualTicket(
    int planId, {
    String? operatorNote,
    bool requireAuthApproval = true,
  }) async {
    prepareTicketCalls += 1;
    return AgentLivePrefill.fromJson({
      'status': 'manual_ticket_prefill_ready',
      'plan_id': planId,
      'plan_run_id': 21,
      'command_type': 'PREPARE_MANUAL_BUY_TICKET',
      'result': {'prefill_ready': true},
      'prefill': {
        'provider': 'kis',
        'market': 'KR',
        'symbol': '005930',
        'side': 'buy',
        'quantity': 2,
        'qty': 2,
        'notional': 30000,
        'currency': 'KRW',
        'order_type': 'market',
        'dry_run': true,
        'confirm_live': false,
        'source_context': 'agent_manual_prefill',
        'source_metadata': {
          'source': 'agent_plan',
          'agent_plan_id': planId,
          'command_log_id': 77,
          'manual_submit_called': false,
        },
      },
      'auth': {'required': false},
      'safety': {
        'real_order_submitted': false,
        'broker_submit_called': false,
        'manual_submit_called': false,
      },
    });
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

AgentPlan _safePlan() {
  return AgentPlan.fromJson({
    'id': 88,
    'plan_key': 'plan_safe',
    'command_type': 'SHOW_POSITIONS',
    'domain': 'position',
    'intent': 'show_positions',
    'market': 'KR',
    'provider': 'kis',
    'symbol': null,
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
    'id': 88,
    'plan_key': 'plan_manual',
    'command_type': 'PREPARE_MANUAL_BUY_TICKET',
    'domain': 'order',
    'intent': 'prepare_manual_buy_ticket',
    'market': 'KR',
    'provider': 'kis',
    'symbol': '005930',
    'side': 'buy',
    'risk_level': 'prefill_only',
    'status': 'ready',
    'plan_title': 'Prepare manual ticket',
    'plan_summary': 'Prepare ticket only.',
    'user_visible_summary': 'Manual ticket only.',
    'command': {'quantity': 2},
    'execution_policy': {'allow_live_order': false},
    'safety': {'real_order_submitted': false},
    'requires_auth': false,
    'requires_recent_validation': true,
    'requires_confirm_live': true,
    'allow_live_order': false,
    'allow_setting_change': false,
    'allow_scheduler_change': false,
  });
}

OrderValidationResult _validation() {
  return OrderValidationResult.fromJson({
    'provider': 'kis',
    'market': 'KR',
    'environment': 'paper',
    'dry_run': true,
    'validated_for_submission': true,
    'can_submit_later': true,
    'symbol': '999999',
    'side': 'sell',
    'qty': 5,
    'order_type': 'market',
    'market_session': {},
    'order_preview': {},
  });
}
