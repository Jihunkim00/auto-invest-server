import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/models/agent_chat_message.dart';
import 'package:auto_invest_dashboard/models/agent_chat_strategy_action.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_result.dart';
import 'package:auto_invest_dashboard/models/order_validation_result.dart';
import 'package:auto_invest_dashboard/models/strategy_profile.dart';

void main() {
  test('refresh and apply strategy profile use strategy endpoints only',
      () async {
    final api = _StrategyFakeApi();
    final controller = DashboardController(api, autoload: false);

    final refresh = await controller.refreshStrategyProfiles();
    final apply = await controller.applyStrategyProfilePreset('aggressive');

    expect(refresh.success, isTrue);
    expect(apply.success, isTrue);
    expect(api.fetchProfileCalls, 1);
    expect(api.applyProfileCalls, 1);
    expect(api.appliedProfiles, ['aggressive']);
    expect(api.validationCalls, 0);
    expect(api.manualSubmitCalls, 0);
    expect(controller.activeStrategyProfile?.profileName, 'aggressive');
    expect(controller.strategyProfiles.last.isActive, isTrue);

    controller.dispose();
  });

  test('confirm strategy chat action applies profile without order paths',
      () async {
    final api = _StrategyFakeApi();
    final action = AgentChatStrategyAction.fromJson(_strategyAction());
    final controller = DashboardController(api, autoload: false)
      ..activeAgentConversationKey = 'conv_strategy'
      ..agentMessages = [
        AgentChatMessage(
          id: 'assistant-pending',
          role: AgentChatRole.assistant,
          text: 'Strategy profile confirmation required.',
          createdAt: DateTime.utc(2026, 6, 23),
          status: AgentChatStatus.readyForReview,
          metadata: {'strategy_action': action.raw},
        ),
      ];

    final result = await controller.confirmAgentChatStrategyAction(action);

    expect(result.success, isTrue);
    expect(api.confirmActionCalls, 1);
    expect(api.cancelActionCalls, 0);
    expect(api.validationCalls, 0);
    expect(api.manualSubmitCalls, 0);
    expect(controller.isAgentStrategyActionBusy(action.actionId), isFalse);
    expect(controller.activeStrategyProfile?.profileName, 'aggressive');
    expect(controller.agentMessages.first.strategyAction?.status, 'applied');
    expect(
        controller.agentMessages.last.messageType, 'strategy_profile_applied');
    expect(
        controller.agentMessages.last.safetyBadges, contains('PROFILE ONLY'));
    expect(controller.agentMessages.last.safetyBadges,
        contains('NO ORDER SUBMIT'));
    expect(
      controller.agentMessages.last.safetyBadges,
      contains('STRATEGY APPLIED'),
    );

    controller.dispose();
  });

  test('cancel strategy chat action marks pending action cancelled', () async {
    final api = _StrategyFakeApi();
    final action = AgentChatStrategyAction.fromJson(_strategyAction());
    final controller = DashboardController(api, autoload: false)
      ..agentMessages = [
        AgentChatMessage(
          id: 'assistant-pending',
          role: AgentChatRole.assistant,
          text: 'Strategy profile confirmation required.',
          createdAt: DateTime.utc(2026, 6, 23),
          status: AgentChatStatus.readyForReview,
          metadata: {'strategy_action': action.raw},
        ),
      ];

    final result = await controller.cancelAgentChatStrategyAction(action);

    expect(result.success, isTrue);
    expect(api.confirmActionCalls, 0);
    expect(api.cancelActionCalls, 1);
    expect(api.validationCalls, 0);
    expect(api.manualSubmitCalls, 0);
    expect(controller.agentMessages.first.strategyAction?.status, 'cancelled');
    expect(controller.agentMessages.last.messageType,
        'strategy_profile_cancelled');
    expect(
        controller.agentMessages.last.safetyBadges, contains('PROFILE ONLY'));
    expect(
      controller.agentMessages.last.safetyBadges,
      contains('NO SETTINGS CHANGE'),
    );

    controller.dispose();
  });
}

class _StrategyFakeApi extends ApiClient {
  int fetchProfileCalls = 0;
  int applyProfileCalls = 0;
  int confirmActionCalls = 0;
  int cancelActionCalls = 0;
  int validationCalls = 0;
  int manualSubmitCalls = 0;
  final List<String> appliedProfiles = [];

  @override
  Future<StrategyProfileList> fetchStrategyProfiles() async {
    fetchProfileCalls += 1;
    return StrategyProfileList.fromJson({
      'profiles': [
        _profile('safe', '안정형'),
        _profile('balanced', '보통형', active: true),
        _profile('aggressive', '고수익형'),
      ],
      'active_profile': _profile('balanced', '보통형', active: true),
    });
  }

  @override
  Future<StrategyProfileApplyResult> applyStrategyProfilePreset(
    String profileName,
  ) async {
    applyProfileCalls += 1;
    appliedProfiles.add(profileName);
    return StrategyProfileApplyResult.fromJson({
      'status': 'applied',
      'active_profile': _profile('aggressive', '고수익형', active: true),
      'audit_id': 700,
      'safety': _safety(settingChanged: true),
    });
  }

  @override
  Future<AgentChatStrategyActionResponse> confirmAgentChatStrategyAction(
    AgentChatStrategyAction action,
  ) async {
    confirmActionCalls += 1;
    return AgentChatStrategyActionResponse.fromJson({
      'status': 'applied',
      'answer': {
        'role': 'assistant',
        'text': '고수익형 profile applied. No order submitted.',
        'answer_type': 'strategy_profile_applied',
      },
      'strategy_action': _strategyAction(status: 'applied'),
      'active_profile': _profile('aggressive', '고수익형', active: true),
      'assistant_message_id': 77,
      'safety': _safety(settingChanged: true),
      'diagnostics': {'order_submitted': false},
    });
  }

  @override
  Future<AgentChatStrategyActionResponse> cancelAgentChatStrategyAction(
    int actionId,
  ) async {
    cancelActionCalls += 1;
    return AgentChatStrategyActionResponse.fromJson({
      'status': 'cancelled',
      'answer': {
        'role': 'assistant',
        'text': 'Strategy profile change cancelled.',
        'answer_type': 'strategy_profile_cancelled',
      },
      'strategy_action': _strategyAction(status: 'cancelled'),
      'safety': _safety(),
      'diagnostics': {'order_submitted': false},
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

Map<String, dynamic> _strategyAction({
  String status = 'pending_confirmation',
}) {
  return {
    'action_id': 70,
    'conversation_key': 'conv_strategy',
    'status': status,
    'action_type': 'strategy_profile_apply',
    'requested_profile': 'aggressive',
    'current_profile': 'balanced',
    'requested_profile_payload': _profile('aggressive', '고수익형'),
    if (status == 'applied')
      'active_profile': _profile('aggressive', '고수익형', active: true),
    'safety': _safety(settingChanged: status == 'applied'),
  };
}

Map<String, dynamic> _profile(
  String profileName,
  String displayName, {
  bool active = false,
}) {
  final aggressive = profileName == 'aggressive';
  final balanced = profileName == 'balanced';
  return {
    'id': aggressive
        ? 3
        : balanced
            ? 2
            : 1,
    'profile_name': profileName,
    'display_name': displayName,
    'description': '$displayName profile',
    'monthly_target_return_pct': aggressive
        ? 0.06
        : balanced
            ? 0.04
            : 0.015,
    'monthly_target_min_pct': aggressive
        ? 0.05
        : balanced
            ? 0.03
            : 0.01,
    'monthly_target_max_pct': aggressive
        ? 0.08
        : balanced
            ? 0.05
            : 0.02,
    'monthly_max_loss_pct': aggressive ? -0.06 : -0.04,
    'daily_max_loss_pct': aggressive ? -0.015 : -0.01,
    'max_order_notional_pct': aggressive ? 0.06 : 0.04,
    'max_order_notional_krw': aggressive ? 80000 : 50000,
    'max_trades_per_day': aggressive ? 2 : 1,
    'max_positions': aggressive ? 5 : 3,
    'buy_score_threshold': aggressive ? 62 : 68,
    'sell_score_threshold': aggressive ? 55 : 60,
    'stop_loss_pct': aggressive ? -0.03 : -0.02,
    'take_profit_pct': aggressive ? 0.06 : 0.04,
    'max_holding_days': aggressive ? 10 : 7,
    'stop_after_monthly_target': !aggressive,
    'reduce_size_after_loss': true,
    'consecutive_loss_reduce_threshold': aggressive ? 3 : 2,
    'is_active': active,
    'is_builtin': true,
  };
}

Map<String, dynamic> _safety({bool settingChanged = false}) {
  return {
    'read_only': false,
    'safe_execution_only': true,
    'mutation': settingChanged,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'validation_called': false,
    'setting_changed': settingChanged,
    'scheduler_changed': false,
    'confirm_live_auto_checked': false,
  };
}
