import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/i18n/app_language.dart';
import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/models/agent_chat_conversation.dart';
import 'package:auto_invest_dashboard/models/agent_chat_live_order_action.dart';
import 'package:auto_invest_dashboard/models/agent_chat_message.dart';
import 'package:auto_invest_dashboard/models/agent_chat_send_response.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_result.dart';
import 'package:auto_invest_dashboard/models/order_validation_result.dart';

void main() {
  test(
      'sendAgentMessage renders pending live order without validation or submit',
      () async {
    final api = _LiveOrderFakeApi();
    final controller = DashboardController(
      api,
      autoload: false,
      initialLanguage: AppLanguage.english,
    )..kisLiveConfirmation = true;

    final result = await controller.sendAgentMessage('Buy Samsung 1 share');

    expect(result.success, isTrue);
    expect(api.chatSendCalls, 1);
    expect(api.confirmCalls, 0);
    expect(api.cancelCalls, 0);
    expect(api.validationCalls, 0);
    expect(api.manualSubmitCalls, 0);
    expect(controller.kisLiveConfirmation, isTrue);
    expect(controller.agentMessages.last.liveOrderAction?.isPending, isTrue);
    expect(controller.agentMessages.last.safetyBadges, contains('LIVE ORDER'));
    expect(
      controller.agentMessages.last.safetyBadges,
      contains('CONFIRM REQUIRED'),
    );
    expect(
      controller.agentMessages.last.safetyBadges,
      contains('VALIDATION REQUIRED'),
    );
    expect(
      controller.agentMessages.last.safetyBadges,
      isNot(contains('NO VALIDATION')),
    );

    controller.dispose();
  });

  test('confirmAgentChatLiveOrder uses chat confirm endpoint only', () async {
    final api = _LiveOrderFakeApi();
    final action = AgentChatLiveOrderAction.fromJson(_actionJson());
    final controller = DashboardController(api, autoload: false)
      ..activeAgentConversationKey = 'conv_live_order'
      ..agentMessages = [
        AgentChatMessage(
          id: 'assistant-pending',
          role: AgentChatRole.assistant,
          text: 'Live order is ready for confirmation.',
          createdAt: DateTime.utc(2026, 6, 21),
          status: AgentChatStatus.readyForReview,
          metadata: {'live_order_action': action.raw},
        ),
      ];

    final result = await controller.confirmAgentChatLiveOrder(action);

    expect(result.success, isTrue);
    expect(api.confirmCalls, 1);
    expect(api.cancelCalls, 0);
    expect(api.validationCalls, 0);
    expect(api.manualSubmitCalls, 0);
    expect(controller.isAgentLiveOrderActionBusy(action.actionId), isFalse);
    expect(controller.agentMessages.first.liveOrderAction?.status, 'submitted');
    expect(controller.agentMessages.last.messageType, 'live_order_submitted');
    expect(controller.agentMessages.last.safetyBadges, contains('REAL ORDER'));
    expect(controller.agentMessages.last.safetyBadges, contains('VALIDATED'));
    expect(
      controller.agentMessages.last.metadata['live_order_result']['status'],
      'submitted',
    );

    controller.dispose();
  });

  test('cancelAgentChatLiveOrder marks pending action cancelled', () async {
    final api = _LiveOrderFakeApi();
    final action = AgentChatLiveOrderAction.fromJson(_actionJson());
    final controller = DashboardController(api, autoload: false)
      ..agentMessages = [
        AgentChatMessage(
          id: 'assistant-pending',
          role: AgentChatRole.assistant,
          text: 'Live order is ready for confirmation.',
          createdAt: DateTime.utc(2026, 6, 21),
          status: AgentChatStatus.readyForReview,
          metadata: {'live_order_action': action.raw},
        ),
      ];

    final result = await controller.cancelAgentChatLiveOrder(action);

    expect(result.success, isTrue);
    expect(api.confirmCalls, 0);
    expect(api.cancelCalls, 1);
    expect(api.manualSubmitCalls, 0);
    expect(controller.agentMessages.first.liveOrderAction?.status, 'cancelled');
    expect(controller.agentMessages.last.messageType, 'live_order_cancelled');
    expect(
      controller.agentMessages.last.safetyBadges,
      contains('NO ORDER SUBMITTED'),
    );

    controller.dispose();
  });

  test('syncAgentChatLiveOrder appends status bubble without manual submit',
      () async {
    final api = _LiveOrderFakeApi();
    final action = AgentChatLiveOrderAction.fromJson(
      _actionJson(status: 'submitted', relatedOrderId: 123),
    );
    final controller = DashboardController(api, autoload: false)
      ..agentMessages = [
        AgentChatMessage(
          id: 'assistant-submitted',
          role: AgentChatRole.assistant,
          text: 'Live KIS order submitted.',
          createdAt: DateTime.utc(2026, 6, 21),
          status: AgentChatStatus.sent,
          metadata: {'live_order_action': action.raw},
        ),
      ];

    final result = await controller.syncAgentChatLiveOrder(action);

    expect(result.success, isTrue);
    expect(api.syncCalls, 1);
    expect(api.manualSubmitCalls, 0);
    expect(controller.agentMessages.first.liveOrderAction?.status, 'filled');
    expect(
        controller.agentMessages.last.messageType, 'live_order_status_synced');
    expect(controller.agentMessages.last.safetyBadges, contains('SYNCED'));

    controller.dispose();
  });
}

class _LiveOrderFakeApi extends ApiClient {
  int chatSendCalls = 0;
  int confirmCalls = 0;
  int cancelCalls = 0;
  int syncCalls = 0;
  int validationCalls = 0;
  int manualSubmitCalls = 0;

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
      conversationKey: 'conv_live_order',
      title: title,
      status: 'active',
      source: source,
      metadata: metadata ?? const {},
      createdAt: DateTime.utc(2026, 6, 21),
      updatedAt: DateTime.utc(2026, 6, 21),
      lastMessageAt: DateTime.utc(2026, 6, 21),
    );
  }

  @override
  Future<AgentChatSendResponse> sendAgentChatMessage({
    required String message,
    String? conversationKey,
    Map<String, dynamic>? context,
    bool autoCreateConversation = true,
    String language = 'ko',
    String locale = 'ko-KR',
  }) async {
    chatSendCalls += 1;
    return AgentChatSendResponse.fromJson({
      'conversation_key': conversationKey ?? 'conv_live_order',
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
      'safety': _safety(validationCalled: false),
    });
  }

  @override
  Future<AgentChatLiveOrderResponse> confirmAgentChatLiveOrder(
    AgentChatLiveOrderAction action,
  ) async {
    confirmCalls += 1;
    return AgentChatLiveOrderResponse.fromJson({
      'status': 'submitted',
      'answer': {
        'role': 'assistant',
        'text': 'Live KIS order submitted.',
        'answer_type': 'live_order_submitted',
      },
      'live_order_action': _actionJson(
        status: 'submitted',
        relatedOrderId: 123,
        brokerOrderId: 'KIS-ODNO-1',
      ),
      'order': {'order_id': 123, 'status': 'submitted'},
      'assistant_message_id': 44,
      'safety': _safety(
        validationCalled: true,
        riskApproved: true,
        realOrderSubmitted: true,
        brokerSubmitCalled: true,
        manualSubmitCalled: true,
      ),
      'diagnostics': {'idempotent_replay': false},
    });
  }

  @override
  Future<AgentChatLiveOrderResponse> cancelAgentChatLiveOrder(
    int actionId,
  ) async {
    cancelCalls += 1;
    return AgentChatLiveOrderResponse.fromJson({
      'status': 'cancelled',
      'answer': {
        'role': 'assistant',
        'text': 'Live order action cancelled.',
        'answer_type': 'live_order_cancelled',
      },
      'live_order_action': _actionJson(status: 'cancelled'),
      'safety': _safety(validationCalled: false),
      'diagnostics': {},
    });
  }

  @override
  Future<AgentChatLiveOrderResponse> syncAgentChatLiveOrder(
    int actionId,
  ) async {
    syncCalls += 1;
    return AgentChatLiveOrderResponse.fromJson({
      'status': 'synced',
      'answer': {
        'role': 'assistant',
        'text': 'Live order status synced.',
        'answer_type': 'live_order_status_synced',
      },
      'live_order_action': _actionJson(
        status: 'filled',
        relatedOrderId: 123,
        brokerOrderId: 'KIS-ODNO-1',
      ),
      'order': {'order_id': 123, 'internal_status': 'FILLED'},
      'safety': _safety(validationCalled: false),
      'diagnostics': {'sync_submitted_new_order': false},
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
    throw const ApiRequestException('frontend validation should not run');
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
    manualSubmitCalls += 1;
    throw const ApiRequestException('frontend manual submit should not run');
  }
}

Map<String, dynamic> _actionJson({
  String status = 'pending_confirmation',
  int? relatedOrderId,
  String? brokerOrderId,
}) {
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
    if (relatedOrderId != null) 'related_order_id': relatedOrderId,
    if (brokerOrderId != null) 'broker_order_id': brokerOrderId,
    'safety': _safety(validationCalled: status == 'submitted'),
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
  };
}

Map<String, dynamic> _safety({
  required bool validationCalled,
  bool riskApproved = false,
  bool realOrderSubmitted = false,
  bool brokerSubmitCalled = false,
  bool manualSubmitCalled = false,
}) {
  return {
    'read_only': false,
    'safe_execution_only': false,
    'real_order_submitted': realOrderSubmitted,
    'broker_submit_called': brokerSubmitCalled,
    'manual_submit_called': manualSubmitCalled,
    'validation_called': validationCalled,
    'risk_approved': riskApproved,
    'setting_changed': false,
    'scheduler_changed': false,
    'confirm_live_auto_checked': true,
    'mutation': realOrderSubmitted,
  };
}
