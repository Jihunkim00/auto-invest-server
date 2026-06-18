import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/agent_plan.dart';

void main() {
  test('AgentPlan parses backend response and action eligibility', () {
    final manualPlan = AgentPlan.fromJson({
      'id': 9,
      'plan_key': 'plan_test',
      'command_type': 'PREPARE_MANUAL_BUY_TICKET',
      'domain': 'order',
      'intent': 'prepare_manual_buy_ticket',
      'market': 'KR',
      'provider': 'kis',
      'symbol': '005930',
      'side': 'buy',
      'risk_level': 'prefill_only',
      'status': 'ready',
      'plan_title': 'Manual ticket',
      'plan_summary': 'Prepare a manual ticket.',
      'user_visible_summary': 'Manual ticket only.',
      'command': {
        'quantity': 2,
        'budget': {'amount': 30000, 'currency': 'KRW'},
      },
      'execution_policy': {'allow_live_order': false},
      'safety': {'real_order_submitted': false},
      'requires_auth': false,
      'requires_recent_validation': true,
      'requires_confirm_live': true,
      'allow_live_order': false,
    });

    expect(manualPlan.canPrepareManualTicket, isTrue);
    expect(manualPlan.canRunSafeAction, isFalse);
    expect(manualPlan.notional, 30000);
    expect(manualPlan.currency, 'KRW');

    final safePlan = AgentPlan.fromJson({
      ...manualPlan.raw,
      'id': 10,
      'command_type': 'SHOW_POSITIONS',
      'domain': 'position',
      'risk_level': 'read_only',
      'side': 'none',
    });

    expect(safePlan.canRunSafeAction, isTrue);
    expect(safePlan.canPrepareManualTicket, isFalse);

    final authPlan = AgentPlan.fromJson({
      ...manualPlan.raw,
      'id': 11,
      'status': 'pending_auth',
      'requires_auth': true,
    });

    expect(authPlan.isAuthRequired, isTrue);
    expect(authPlan.canPrepareManualTicket, isFalse);
  });
}
