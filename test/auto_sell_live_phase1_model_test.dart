import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/auto_sell_live_phase1.dart';

void main() {
  test('phase one sell model parses disabled status as blocked and read-only',
      () {
    final result = AutoSellLivePhase1Result.fromJson(
      autoSellLivePhase1Json(),
    );

    expect(result.provider, 'kis');
    expect(result.market, 'KR');
    expect(result.autoSellLiveEnabled, isFalse);
    expect(result.resultStatus, 'disabled');
    expect(result.blocked, isTrue);
    expect(result.submitted, isFalse);
    expect(result.dailyRemaining, 1);
    expect(result.primaryBlockReason, 'auto_sell_live_phase1_disabled');
    expect(result.checklist.single.key, 'auto_sell_live_phase1_enabled');
    expect(result.safety['broker_submit_called'], isFalse);
  });

  test('phase one sell model parses submitted run and latest audit summary',
      () {
    final result = AutoSellLivePhase1Result.fromJson(
      autoSellLivePhase1Json(
        enabled: true,
        status: 'submitted',
        realOrderSubmitted: true,
        brokerSubmitCalled: true,
        selectedCandidateId: 'exit-005930-stop',
        selectedSymbol: '005930',
        orderId: 55,
        brokerOrderId: 'KIS-SELL-1',
        dailyCount: 1,
      ),
    );

    expect(result.blocked, isFalse);
    expect(result.submitted, isTrue);
    expect(result.dailyRemaining, 0);
    expect(result.selectedCandidateId, 'exit-005930-stop');
    expect(result.selectedSymbol, '005930');
    expect(result.candidateType, 'stop_loss');
    expect(result.candidateSeverity, 'critical');
    expect(result.availableQuantity, 3);
    expect(result.orderId, 55);
    expect(result.brokerOrderId, 'KIS-SELL-1');
    expect(result.latestRun, isNotNull);
    expect(result.latestRun!.realOrderSubmitted, isTrue);
    expect(result.latestRun!.brokerOrderId, 'KIS-SELL-1');
  });
}

Map<String, dynamic> autoSellLivePhase1Json({
  bool enabled = false,
  String status = 'disabled',
  bool realOrderSubmitted = false,
  bool brokerSubmitCalled = false,
  String? selectedCandidateId,
  String? selectedSymbol,
  int? orderId,
  String? brokerOrderId,
  int dailyCount = 0,
}) {
  return {
    'run_id': realOrderSubmitted ? 44 : null,
    'generated_at': '2026-07-09T01:00:00Z',
    'provider': 'kis',
    'market': 'KR',
    'trigger_source': 'status',
    'automation_phase': 'phase1_auto_sell',
    'auto_sell_live_enabled': enabled,
    'result_status': status,
    'real_order_submitted': realOrderSubmitted,
    'broker_submit_called': brokerSubmitCalled,
    'manual_submit_called': false,
    'selected_candidate_id': selectedCandidateId,
    'selected_symbol': selectedSymbol,
    'candidate_type': selectedSymbol == null ? null : 'stop_loss',
    'candidate_severity': selectedSymbol == null ? null : 'critical',
    'production_readiness_status': enabled ? 'ready' : 'blocked',
    'sell_preflight_status': enabled ? 'allowed' : null,
    'order_id': orderId,
    'broker_order_id': brokerOrderId,
    'kis_odno': brokerOrderId,
    'submitted_quantity': realOrderSubmitted ? 3 : null,
    'submitted_notional': realOrderSubmitted ? 210000 : null,
    'available_quantity': selectedSymbol == null ? null : 3,
    'daily_auto_sell_count': dailyCount,
    'daily_auto_sell_limit': 1,
    'risk_flags': enabled ? const ['risk_reduction_only'] : const [],
    'gating_notes': enabled
        ? const ['No retry is attempted by phase-one auto-sell.']
        : const [],
    'checklist': [
      {
        'key': 'auto_sell_live_phase1_enabled',
        'status': enabled ? 'pass' : 'fail',
        'ok': enabled,
        'blocking': !enabled,
        'reason': enabled ? null : 'auto_sell_live_phase1_disabled',
        'detail': 'Phase-one auto-sell live mode is explicitly enabled.',
      },
    ],
    'primary_block_reason': enabled ? null : 'auto_sell_live_phase1_disabled',
    'next_safe_action':
        enabled ? 'review_order_status' : 'enable_phase1_explicitly',
    'latest_run': {
      'run_id': realOrderSubmitted ? 44 : 22,
      'generated_at': '2026-07-09T01:00:00Z',
      'trigger_source': 'manual_phase1_test',
      'result_status': status,
      'selected_candidate_id': selectedCandidateId,
      'selected_symbol': selectedSymbol,
      'candidate_type': selectedSymbol == null ? null : 'stop_loss',
      'candidate_severity': selectedSymbol == null ? null : 'critical',
      'primary_block_reason': enabled ? null : 'auto_sell_live_phase1_disabled',
      'real_order_submitted': realOrderSubmitted,
      'broker_submit_called': brokerSubmitCalled,
      'order_id': orderId,
      'broker_order_id': brokerOrderId,
    },
    'safety': {
      'phase1_auto_sell': true,
      'real_order_submitted': realOrderSubmitted,
      'broker_submit_called': brokerSubmitCalled,
      'manual_submit_called': false,
      'retry_attempted': false,
      'buy_submit_called': false,
      'setting_changed': false,
    },
  };
}
