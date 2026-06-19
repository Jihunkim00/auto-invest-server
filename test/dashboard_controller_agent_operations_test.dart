import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/models/agent_chat_message.dart';
import 'package:auto_invest_dashboard/models/agent_live_prefill.dart';
import 'package:auto_invest_dashboard/models/agent_operations.dart';
import 'package:auto_invest_dashboard/models/agent_review_queue.dart';
import 'package:auto_invest_dashboard/models/agent_run.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_result.dart';
import 'package:auto_invest_dashboard/models/order_validation_result.dart';

void main() {
  test('refreshAgentOperationsSummary and queue load API payloads', () async {
    final api = _AgentOperationsFakeApi();
    final controller = DashboardController(api, autoload: false);

    final summary = await controller.refreshAgentOperationsSummary();
    final queue = await controller.refreshAgentReviewQueue(filter: 'blocked');

    expect(summary.success, isTrue);
    expect(queue.success, isTrue);
    expect(api.summaryCalls, 1);
    expect(api.queueCalls, 1);
    expect(api.lastQueueType, 'blocked');
    expect(controller.agentOperationsSnapshot?.summary.blockedCount, 2);
    expect(controller.agentReviewQueue.items.single.queueType, 'blocked');

    controller.dispose();
  });

  test('openAgentConversationFromQueue loads chat and expands panel', () async {
    final api = _AgentOperationsFakeApi();
    final controller = DashboardController(api, autoload: false);

    final result =
        await controller.openAgentConversationFromQueue('conv_queue');

    expect(result.success, isTrue);
    expect(api.fetchChatMessagesCalls, 1);
    expect(controller.activeAgentConversationKey, 'conv_queue');
    expect(controller.agentChatMode, AgentChatPanelMode.expanded);
    expect(controller.agentMessages.single.text, 'Restored queue chat.');

    controller.dispose();
  });

  test('runSafeActionFromQueue calls only safe run endpoint', () async {
    final api = _AgentOperationsFakeApi();
    final controller = DashboardController(api, autoload: false);

    final result = await controller.runSafeActionFromQueue(88);

    expect(result.success, isTrue);
    expect(api.runPlanCalls, 1);
    expect(api.prepareTicketCalls, 0);
    expect(api.validationCalls, 0);
    expect(api.submitCalls, 0);
    expect(controller.latestAgentRun?.planId, 88);

    controller.dispose();
  });

  test('prepareTicketFromQueue applies prefill and keeps manual gates reset',
      () async {
    final api = _AgentOperationsFakeApi();
    final controller = DashboardController(api, autoload: false)
      ..kisLiveConfirmation = true
      ..orderValidationResult = _validation()
      ..kisManualOrderError = 'old error';

    final result = await controller.prepareTicketFromQueue(88);

    expect(result.success, isTrue);
    expect(api.prepareTicketCalls, 1);
    expect(api.validationCalls, 0);
    expect(api.submitCalls, 0);
    expect(controller.orderTicketSymbol, '005930');
    expect(controller.orderTicketSide, 'buy');
    expect(controller.orderTicketQty, 2);
    expect(controller.kisLiveConfirmation, isFalse);
    expect(controller.orderValidationResult, isNull);
    expect(controller.kisManualOrderError, isNull);
    expect(
        controller.orderTicketSourceMetadata?['manual_submit_called'], isFalse);

    controller.dispose();
  });

  test('reviewed and dismiss queue actions call API and refresh queue',
      () async {
    final api = _AgentOperationsFakeApi();
    final controller = DashboardController(api, autoload: false);

    final reviewed = await controller.markAgentQueueItemReviewed('plan_1');
    final dismissed = await controller.dismissAgentQueueItem('plan_1');

    expect(reviewed.success, isTrue);
    expect(dismissed.success, isTrue);
    expect(api.reviewedCalls, 1);
    expect(api.dismissCalls, 1);
    expect(api.queueCalls, 2);
    expect(api.summaryCalls, 2);

    controller.dispose();
  });
}

class _AgentOperationsFakeApi extends ApiClient {
  int summaryCalls = 0;
  int queueCalls = 0;
  int reviewedCalls = 0;
  int dismissCalls = 0;
  int fetchChatMessagesCalls = 0;
  int runPlanCalls = 0;
  int prepareTicketCalls = 0;
  int validationCalls = 0;
  int submitCalls = 0;
  String? lastQueueType;

  @override
  Future<AgentOperationsSnapshot> fetchAgentOperationsSummary() async {
    summaryCalls += 1;
    return AgentOperationsSnapshot.fromJson({
      'summary': {
        'active_plans': 4,
        'pending_auth_count': 1,
        'blocked_count': 2,
        'prefill_ready_count': 1,
        'safe_run_completed_count': 3,
        'failed_count': 0,
        'active_conversation_count': 2,
      },
      'safety': {'read_only': true},
    });
  }

  @override
  Future<AgentReviewQueue> fetchAgentReviewQueue({
    String status = 'open',
    String queueType = 'all',
    String? conversationKey,
    int limit = 50,
  }) async {
    queueCalls += 1;
    lastQueueType = queueType;
    return AgentReviewQueue.fromJson({
      'count': 1,
      'items': [
        _queueItem(queueType == 'all' ? 'blocked' : queueType),
      ],
      'safety': {'read_only': true},
    });
  }

  @override
  Future<AgentReviewQueueStateResult> markAgentReviewQueueItemReviewed(
    String queueKey, {
    String? reviewerNote,
  }) async {
    reviewedCalls += 1;
    return AgentReviewQueueStateResult.fromJson({
      'state': {
        'queue_key': queueKey,
        'status': 'reviewed',
        'reviewer_note': reviewerNote,
      },
    });
  }

  @override
  Future<AgentReviewQueueStateResult> dismissAgentReviewQueueItem(
    String queueKey, {
    String? reviewerNote,
  }) async {
    dismissCalls += 1;
    return AgentReviewQueueStateResult.fromJson({
      'state': {
        'queue_key': queueKey,
        'status': 'dismissed',
        'reviewer_note': reviewerNote,
      },
    });
  }

  @override
  Future<List<AgentChatMessage>> fetchAgentChatMessages(
    String conversationKey, {
    int limit = 100,
    int? beforeId,
  }) async {
    fetchChatMessagesCalls += 1;
    return [
      AgentChatMessage(
        id: 'chat-1',
        role: AgentChatRole.assistant,
        text: 'Restored queue chat.',
        createdAt: DateTime.utc(2026, 6, 18),
        status: AgentChatStatus.sent,
        conversationKey: conversationKey,
      ),
    ];
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
      'plan_run_id': 33,
      'command_type': 'SHOW_POSITIONS',
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
      'plan_run_id': 44,
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
          'manual_submit_called': false,
          'broker_submit_called': false,
        },
      },
      'auth': {'required': false},
      'safety': {
        'real_order_submitted': false,
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

Map<String, dynamic> _queueItem(String queueType) {
  return {
    'queue_id': 'plan_1',
    'queue_key': 'plan_1',
    'item_type': 'agent_plan',
    'queue_type': queueType,
    'priority': queueType == 'blocked' ? 'high' : 'medium',
    'review_status': 'open',
    'conversation_key': 'conv_queue',
    'plan_id': 88,
    'command_type': queueType == 'prefill_ready'
        ? 'PREPARE_MANUAL_BUY_TICKET'
        : 'SHOW_POSITIONS',
    'market': 'KR',
    'provider': 'kis',
    'symbol': '005930',
    'side': 'buy',
    'risk_level': queueType == 'prefill_ready' ? 'prefill_only' : 'read_only',
    'status': 'ready_for_review',
    'title': 'Queue item',
    'summary': 'Review this item.',
    'blocked_reason': queueType == 'blocked' ? 'live action blocked' : null,
    'safety_badges': ['NO_AUTO_SUBMIT'],
    'can_run_safe_action': queueType == 'ready_for_review',
    'can_prepare_ticket': queueType == 'prefill_ready',
  };
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
