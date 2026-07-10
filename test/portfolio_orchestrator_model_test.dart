import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/portfolio_orchestrator.dart';

void main() {
  test('orchestrator model parses disabled safe default', () {
    final result = PortfolioOrchestratorResult.fromJson(
      portfolioOrchestratorJson(),
    );

    expect(result.runId, isNull);
    expect(result.provider, 'kis');
    expect(result.market, 'KR');
    expect(result.orchestratorEnabled, isFalse);
    expect(result.allowLiveOrders, isFalse);
    expect(result.mode, 'dry_run_monitoring');
    expect(result.positionsFirst, isTrue);
    expect(result.disabled, isTrue);
    expect(result.noAction, isTrue);
    expect(result.realOrderSubmitted, isFalse);
    expect(result.brokerSubmitCalled, isFalse);
    expect(result.manualSubmitCalled, isFalse);
    expect(result.maxActionsPerRun, 1);
    expect(result.checklist.single.failed, isTrue);
  });

  test('orchestrator model parses sell submission and skipped buy', () {
    final result = PortfolioOrchestratorResult.fromJson(
      portfolioOrchestratorJson(
        enabled: true,
        status: 'sell_submitted',
        action: 'auto_sell_phase1',
        realOrderSubmitted: true,
        brokerSubmitCalled: true,
        skippedBuyReason: 'sell_submitted',
      ),
    );

    expect(result.sellSubmitted, isTrue);
    expect(result.buySubmitted, isFalse);
    expect(result.completed, isTrue);
    expect(result.skippedBuyReason, 'sell_submitted');
    expect(result.positionManagementResult!.resultStatus, 'dry_run_completed');
    expect(result.autoSellPhase1Result!.selectedSymbol, '005930');
    expect(result.autoBuyPhase1Result, isNull);
    expect(result.selectedCandidateId, 'exit-7');
    expect(result.orderId, 42);
    expect(result.brokerOrderId, 'KIS-42');
  });

  test('broker call without confirmed real submission is not submitted action',
      () {
    final result = PortfolioOrchestratorResult.fromJson(
      portfolioOrchestratorJson(
        enabled: true,
        status: 'blocked',
        action: 'auto_buy_phase1',
        brokerSubmitCalled: true,
      ),
    );

    expect(result.brokerSubmitCalled, isTrue);
    expect(result.realOrderSubmitted, isFalse);
    expect(result.buySubmitted, isFalse);
    expect(result.noAction, isTrue);
  });
}

Map<String, dynamic> portfolioOrchestratorJson({
  bool enabled = false,
  String status = 'disabled',
  String action = 'none',
  bool realOrderSubmitted = false,
  bool brokerSubmitCalled = false,
  String? skippedBuyReason,
  String? skippedSellReason,
}) {
  final submitted = realOrderSubmitted && action != 'none';
  final selling = action == 'auto_sell_phase1';
  final buying = action == 'auto_buy_phase1';
  return {
    'run_id': submitted ? 96 : null,
    'generated_at': '2026-07-10T01:00:00Z',
    'provider': 'kis',
    'market': 'KR',
    'trigger_source': 'manual_orchestrator_test',
    'orchestrator_enabled': enabled,
    'allow_live_orders': enabled,
    'mode': 'dry_run_monitoring',
    'positions_first': true,
    'result_status': status,
    'real_order_submitted': realOrderSubmitted,
    'broker_submit_called': brokerSubmitCalled,
    'manual_submit_called': false,
    'action_taken': action,
    'position_management_result': enabled
        ? {
            'result_status': 'dry_run_completed',
            'primary_reason': 'positions_checked',
            'real_order_submitted': false,
            'broker_submit_called': false,
            'manual_submit_called': false,
          }
        : null,
    'auto_sell_phase1_result': selling
        ? {
            'result_status': 'submitted',
            'selected_symbol': '005930',
            'real_order_submitted': realOrderSubmitted,
            'broker_submit_called': brokerSubmitCalled,
            'manual_submit_called': false,
          }
        : null,
    'auto_buy_phase1_result': buying
        ? {
            'result_status': 'submitted',
            'selected_symbol': '000660',
            'real_order_submitted': realOrderSubmitted,
            'broker_submit_called': brokerSubmitCalled,
            'manual_submit_called': false,
          }
        : null,
    'skipped_buy_reason': skippedBuyReason,
    'skipped_sell_reason': skippedSellReason,
    'max_actions_per_run': 1,
    'daily_trade_limit_used': submitted ? 1 : 0,
    'daily_trade_limit_remaining': submitted ? 0 : 1,
    'sync_required_count': 0,
    'critical_exit_candidate_count': selling ? 1 : 0,
    'pending_order_conflict_count': 0,
    'production_readiness_status': enabled ? 'ready' : 'blocked',
    'risk_flags': enabled ? const ['positions_first'] : const [],
    'gating_notes': const ['No automatic retry is attempted.'],
    'checklist': [
      {
        'key': 'orchestrator_enabled',
        'status': enabled ? 'pass' : 'fail',
        'ok': enabled,
        'reason': enabled ? null : 'portfolio_orchestrator_disabled',
        'detail': 'Portfolio orchestration requires explicit enablement.',
      },
    ],
    'primary_block_reason': enabled ? null : 'portfolio_orchestrator_disabled',
    'next_safe_action': enabled ? 'review_result' : 'review_runtime_settings',
    'selected_symbol': submitted ? (selling ? '005930' : '000660') : null,
    'selected_candidate_id': selling ? 'exit-7' : null,
    'selected_promotion_id': buying ? 11 : null,
    'order_id': submitted ? 42 : null,
    'broker_order_id': submitted ? 'KIS-42' : null,
    'kis_odno': submitted ? '0000000042' : null,
    'safety': {
      'positions_first': true,
      'real_order_submitted': realOrderSubmitted,
      'broker_submit_called': brokerSubmitCalled,
      'manual_submit_called': false,
    },
  };
}
