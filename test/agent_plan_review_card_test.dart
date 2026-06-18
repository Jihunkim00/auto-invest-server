import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/features/dashboard/widgets/agent_plan_review_card.dart';
import 'package:auto_invest_dashboard/models/agent_plan.dart';

void main() {
  testWidgets('safe analysis plan shows safe action only', (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: AgentPlanReviewCard(plan: _plan(riskLevel: 'analysis_only')),
      ),
    ));

    expect(find.text('Run Safe Action'), findsOneWidget);
    expect(find.text('Submit Live Order'), findsNothing);
    expect(find.text('Prepare Manual Ticket'), findsNothing);
  });

  testWidgets('manual ticket plan shows prepare action only', (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: AgentPlanReviewCard(
          plan: _plan(
            commandType: 'PREPARE_MANUAL_BUY_TICKET',
            domain: 'order',
            riskLevel: 'prefill_only',
            side: 'buy',
          ),
        ),
      ),
    ));

    expect(find.text('Prepare Manual Ticket'), findsOneWidget);
    expect(find.text('Submit Live Order'), findsNothing);
    expect(find.text('Run Safe Action'), findsNothing);
  });

  testWidgets('auth and blocked plans do not expose actions', (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Column(children: [
          AgentPlanReviewCard(
            plan: _plan(
              commandType: 'PREPARE_MANUAL_BUY_TICKET',
              domain: 'order',
              riskLevel: 'prefill_only',
              status: 'pending_auth',
              requiresAuth: true,
            ),
          ),
          AgentPlanReviewCard(plan: _plan(status: 'blocked')),
        ]),
      ),
    ));

    expect(find.text('Auth Required'), findsOneWidget);
    expect(find.text('Blocked by backend policy. No action is available.'),
        findsOneWidget);
    expect(find.text('Submit Live Order'), findsNothing);
  });
}

AgentPlan _plan({
  String commandType = 'RUN_SINGLE_SYMBOL_ANALYSIS',
  String domain = 'analysis',
  String riskLevel = 'analysis_only',
  String status = 'ready',
  String side = 'none',
  bool requiresAuth = false,
}) {
  return AgentPlan.fromJson({
    'id': 1,
    'plan_key': 'plan_test',
    'command_type': commandType,
    'domain': domain,
    'intent': 'test',
    'market': 'KR',
    'provider': 'kis',
    'symbol': '005930',
    'side': side,
    'risk_level': riskLevel,
    'status': status,
    'plan_title': 'Plan review',
    'plan_summary': 'Review before action.',
    'user_visible_summary': 'No broker submit was called.',
    'command': {'symbol': '005930', 'side': side},
    'execution_policy': {'allow_live_order': false},
    'safety': {'real_order_submitted': false},
    'requires_auth': requiresAuth,
    'requires_recent_validation': true,
    'requires_confirm_live': true,
    'allow_live_order': false,
    'allow_setting_change': false,
    'allow_scheduler_change': false,
  });
}
