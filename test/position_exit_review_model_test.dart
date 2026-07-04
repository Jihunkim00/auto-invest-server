import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/position_exit_review.dart';

void main() {
  test('position exit review parses held position P/L and safety', () {
    final review = PositionExitReview.fromJson(positionExitReviewJson());

    expect(review.provider, 'kis');
    expect(review.market, 'KR');
    expect(review.totalPositionValue, 9800);
    expect(review.totalUnrealizedPl, -200);
    expect(review.totalUnrealizedPlPct, -0.02);
    expect(review.safety['read_only'], isTrue);
    expect(review.positions, hasLength(1));

    final item = review.positions.single;
    expect(item.symbol, '005930');
    expect(item.quantity, 2);
    expect(item.availableQuantity, 2);
    expect(item.costBasis, 10000);
    expect(item.currentValue, 9800);
    expect(item.unrealizedPlPct, -0.02);
    expect(item.stopLossTriggered, isTrue);
    expect(item.exitReviewStatus, 'review_required');
  });

  test('sell preflight parses read-only blocked and allowed states', () {
    final allowed = PositionSellPreflightResult.fromJson(
      positionSellPreflightJson(status: 'allowed'),
    );
    final blocked = PositionSellPreflightResult.fromJson(
      positionSellPreflightJson(
        status: 'blocked',
        primaryBlockReason: 'no_held_position',
      ),
    );

    expect(allowed.isAllowed, isTrue);
    expect(allowed.isReadOnly, isTrue);
    expect(allowed.realOrderSubmitted, isFalse);
    expect(allowed.brokerSubmitCalled, isFalse);
    expect(allowed.manualSubmitCalled, isFalse);
    expect(allowed.orderId, isNull);
    expect(allowed.kisOdno, isNull);
    expect(allowed.estimatedSellNotional, 9800);
    expect(allowed.unrealizedPlPct, -0.02);
    expect(allowed.checklist.first.key, 'position_exists');

    expect(blocked.isBlocked, isTrue);
    expect(blocked.primaryBlockReason, 'no_held_position');
    expect(blocked.canSubmitAfterConfirmation, isFalse);
  });

  test('guarded sell result parses submitted and dry-run states', () {
    final submitted = GuardedPositionSellResult.fromJson(
      guardedSellResultJson(status: 'submitted', submitted: true),
    );
    final dryRun = GuardedPositionSellResult.fromJson(
      guardedSellResultJson(status: 'dry_run_simulated'),
    );

    expect(submitted.isSubmitted, isTrue);
    expect(submitted.realOrderSubmitted, isTrue);
    expect(submitted.brokerSubmitCalled, isTrue);
    expect(submitted.manualSubmitCalled, isTrue);
    expect(submitted.canSync, isTrue);
    expect(submitted.orderId, 42);
    expect(submitted.kisOdno, 'KIS-SELL-1');
    expect(submitted.submittedQuantity, 2);

    expect(dryRun.isDryRunSimulated, isTrue);
    expect(dryRun.realOrderSubmitted, isFalse);
    expect(dryRun.brokerSubmitCalled, isFalse);
    expect(dryRun.canSync, isFalse);
  });
}

Map<String, dynamic> positionExitReviewJson() {
  return {
    'provider': 'kis',
    'market': 'KR',
    'positions': [
      {
        'symbol': '005930',
        'name': 'Samsung',
        'provider': 'kis',
        'market': 'KR',
        'quantity': 2,
        'available_quantity': 2,
        'average_price': 5000,
        'cost_basis': 10000,
        'current_price': 4900,
        'current_value': 9800,
        'unrealized_pl': -200,
        'unrealized_pl_pct': -0.02,
        'day_pl': -20,
        'entry_source': 'manual_live',
        'related_buy_order_id': 12,
        'related_promotion_id': 3,
        'stop_loss_threshold_pct': 2,
        'take_profit_threshold_pct': 2,
        'stop_loss_triggered': true,
        'take_profit_triggered': false,
        'exit_review_status': 'review_required',
        'primary_risk_note': 'Stop-loss condition reached.',
        'risk_flags': ['stop_loss_triggered'],
        'gating_notes': ['Read-only position exit review.'],
        'next_safe_action': 'run_sell_preflight',
      },
    ],
    'total_position_value': 9800,
    'total_unrealized_pl': -200,
    'total_unrealized_pl_pct': -0.02,
    'updated_at': '2026-07-03T00:00:00Z',
    'safety_flags': ['read_only', 'preflight_only'],
    'safety': {
      'read_only': true,
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
    },
  };
}

Map<String, dynamic> positionSellPreflightJson({
  String status = 'allowed',
  String? primaryBlockReason,
}) {
  final blocked = status == 'blocked';
  return {
    'symbol': '005930',
    'provider': 'kis',
    'market': 'KR',
    'preflight_status': status,
    'can_submit_after_confirmation': !blocked && status == 'allowed',
    'final_confirmation_required': true,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'order_id': null,
    'broker_order_id': null,
    'kis_odno': null,
    'position_exists': !blocked,
    'quantity_held': blocked ? null : 2,
    'available_quantity': blocked ? null : 2,
    'requested_quantity': blocked ? null : 2,
    'estimated_sell_notional': blocked ? null : 9800,
    'current_price': 4900,
    'average_price': 5000,
    'cost_basis': 10000,
    'current_value': 9800,
    'unrealized_pl': -200,
    'unrealized_pl_pct': -0.02,
    'stop_loss_threshold_pct': 2,
    'take_profit_threshold_pct': 2,
    'stop_loss_triggered': !blocked,
    'take_profit_triggered': false,
    'kill_switch': false,
    'dry_run': false,
    'kis_real_order_enabled': true,
    'market_session_allowed': true,
    'no_new_entry_window_allowed': true,
    'risk_flags': blocked ? [primaryBlockReason] : ['stop_loss_triggered'],
    'gating_notes': ['Sell preflight is read-only.'],
    'checklist': [
      {
        'key': 'position_exists',
        'status': blocked ? 'fail' : 'pass',
        'label_key': 'position_exists',
        'detail': blocked ? 'No held position.' : 'Held position was found.',
        'blocking': blocked,
      },
    ],
    'primary_block_reason': primaryBlockReason,
    'next_required_action': blocked
        ? 'resolve_no_held_position'
        : 'final_operator_confirmation_required',
    'safety': {
      'read_only': true,
      'preflight_only': true,
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
    },
  };
}

Map<String, dynamic> guardedSellResultJson({
  String status = 'submitted',
  bool submitted = false,
}) {
  return {
    'symbol': '005930',
    'provider': 'kis',
    'market': 'KR',
    'action': 'sell',
    'result_status': status,
    'attempt_id': 7,
    'confirm_live': true,
    'final_confirmation_required': true,
    'real_order_submitted': submitted,
    'broker_submit_called': submitted,
    'manual_submit_called': submitted,
    'order_id': submitted ? 42 : null,
    'broker_order_id': submitted ? 'KIS-SELL-1' : null,
    'kis_odno': submitted ? 'KIS-SELL-1' : null,
    'requested_quantity': 2,
    'submitted_quantity': submitted ? 2 : null,
    'estimated_sell_notional': 9800,
    'current_price': 4900,
    'average_price': 5000,
    'cost_basis': 10000,
    'unrealized_pl': -200,
    'unrealized_pl_pct': -0.02,
    'risk_flags': status == 'dry_run_simulated'
        ? ['dry_run_enabled']
        : ['stop_loss_triggered'],
    'gating_notes': ['Guarded sell manual only.'],
    'checklist': [
      {
        'key': 'final_confirmation_received',
        'status': 'pass',
        'label_key': 'final_confirmation_received',
        'detail': 'Final confirmation was received.',
        'blocking': false,
      },
    ],
    'primary_block_reason':
        status == 'dry_run_simulated' ? 'dry_run_enabled' : null,
    'next_safe_action':
        submitted ? 'sync_order_status' : 'review_dry_run_result',
    'submitted_at': submitted ? '2026-07-03T01:00:00Z' : null,
    'last_synced_at': null,
    'broker_status': submitted ? 'submitted' : null,
    'internal_status': submitted ? 'SUBMITTED' : null,
    'safety': {
      'manual_only': true,
      'real_order_submitted': submitted,
      'broker_submit_called': submitted,
      'manual_submit_called': submitted,
    },
  };
}
