import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/agent_chat_send_response.dart';
import 'package:auto_invest_dashboard/models/strategy_profile.dart';

void main() {
  test('StrategyProfileList parses safe balanced and aggressive profiles', () {
    final list = StrategyProfileList.fromJson({
      'profiles': [
        _profile('safe', '안정형', active: false),
        _profile('balanced', '보통형', active: true),
        _profile('aggressive', '고수익형', active: false),
      ],
      'active_profile': _profile('balanced', '보통형', active: true),
    });

    expect(list.profiles.map((profile) => profile.profileName), [
      'safe',
      'balanced',
      'aggressive',
    ]);
    expect(list.activeProfile.profileName, 'balanced');
    expect(list.activeProfile.displayName, '보통형');
    expect(list.activeProfile.monthlyTargetMinPct, 0.03);
    expect(list.activeProfile.monthlyTargetMaxPct, 0.05);
    expect(strategyProfileLabel('safe'), '안정형');
    expect(strategyProfileLabel('aggressive'), '고수익형');
  });

  test('AgentChatSendResponse parses strategy intent and pending action', () {
    final response = AgentChatSendResponse.fromJson({
      'conversation_key': 'conv_strategy',
      'intent': {
        'category': 'strategy_profile_change_request',
        'supported': true,
        'confidence': 0.92,
        'side': 'none',
        'requires_plan': false,
        'requires_auth': false,
        'requires_manual_confirmation': true,
        'requested_profile': 'aggressive',
        'target_monthly_return_pct': 0.05,
        'fallback_used': true,
        'parser_status': 'fallback',
      },
      'answer': {
        'role': 'assistant',
        'text': '고수익형 적용 확인이 필요합니다.',
        'answer_type': 'strategy_profile_change_confirmation_required',
      },
      'data': const {},
      'strategy_action': _strategyAction(),
      'available_actions': [
        'confirm_strategy_profile',
        'cancel_strategy_profile'
      ],
      'safety': _safety(),
    });

    expect(response.intent.requestedProfile, 'aggressive');
    expect(response.intent.targetMonthlyReturnPct, 0.05);
    expect(response.intent.isReadOnly, isFalse);
    expect(response.strategyAction?.isPending, isTrue);
    expect(
        response.strategyAction?.requestedProfilePayload?.displayName, '고수익형');
    expect(response.safety.realOrderSubmitted, isFalse);
    expect(response.safety.validationCalled, isFalse);
  });
}

Map<String, dynamic> _strategyAction() {
  return {
    'action_id': 70,
    'status': 'pending_confirmation',
    'action_type': 'strategy_profile_apply',
    'requested_profile': 'aggressive',
    'current_profile': 'balanced',
    'requested_profile_payload': _profile('aggressive', '고수익형'),
    'safety': _safety(),
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
    'monthly_max_loss_pct': aggressive
        ? -0.06
        : balanced
            ? -0.04
            : -0.02,
    'daily_max_loss_pct': aggressive
        ? -0.015
        : balanced
            ? -0.01
            : -0.005,
    'max_order_notional_pct': aggressive
        ? 0.06
        : balanced
            ? 0.04
            : 0.02,
    'max_order_notional_krw': aggressive
        ? 80000
        : balanced
            ? 50000
            : 30000,
    'max_trades_per_day': aggressive ? 2 : 1,
    'max_positions': aggressive ? 5 : 2,
    'buy_score_threshold': aggressive ? 62 : 75,
    'sell_score_threshold': aggressive ? 55 : 65,
    'stop_loss_pct': aggressive ? -0.03 : -0.012,
    'take_profit_pct': aggressive ? 0.06 : 0.02,
    'max_holding_days': aggressive ? 10 : 5,
    'stop_after_monthly_target': !aggressive,
    'reduce_size_after_loss': true,
    'consecutive_loss_reduce_threshold': aggressive ? 3 : 1,
    'is_active': active,
    'is_builtin': true,
  };
}

Map<String, dynamic> _safety() {
  return {
    'read_only': false,
    'safe_execution_only': true,
    'mutation': true,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'validation_called': false,
    'setting_changed': false,
    'scheduler_changed': false,
    'confirm_live_auto_checked': false,
  };
}
