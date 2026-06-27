import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/strategy_auto_buy_promotion.dart';

void main() {
  test('strategy auto buy promotion model parses pending item', () {
    final promotions = StrategyAutoBuyPromotions.fromJson(
      autoBuyPromotionsJson(),
    );

    expect(promotions.count, 1);
    expect(promotions.latest, isNotNull);
    final item = promotions.latest!;
    expect(item.id, 1);
    expect(item.symbol, '005930');
    expect(item.status, 'pending');
    expect(item.canRunGuardedLive, isTrue);
    expect(item.reviewStatus, 'pending_review');
    expect(item.reviewRequired, isTrue);
    expect(item.reviewChecklist, isNotEmpty);
    expect(item.sourceDryRunTradeRunId, 22);
    expect(item.finalScore, 82);
    expect(item.proposedNotionalKrw, 30000);
    expect(item.maxNotionalKrw, 50000);
    expect(item.simulatedNotionalKrw, 30000);
    expect(item.simulatedQuantity, 3);
    expect(item.riskFlags, ['dry_run_only']);
    expect(item.liveAttemptId, isNull);
    expect(item.tracePayload['promotion_id'], 1);
    expect(promotions.safety['broker_submit_called'], isFalse);
  });

  test('promotion action result parses local state update', () {
    final result = StrategyAutoBuyPromotionActionResult.fromJson({
      'status': 'acknowledged',
      'promotion': autoBuyPromotionJson(status: 'acknowledged'),
      'safety': {'read_only': true, 'broker_submit_called': false},
    });

    expect(result.status, 'acknowledged');
    expect(result.promotion.status, 'acknowledged');
    expect(result.promotion.reviewStatus, 'reviewed');
    expect(result.promotion.canRunGuardedLive, isTrue);
    expect(result.safety['broker_submit_called'], isFalse);
  });

  test('converted promotion parses audit trace and is not runnable', () {
    final item = StrategyAutoBuyPromotion.fromJson(
      autoBuyPromotionJson(status: 'live_order_created'),
    );

    expect(item.canRunGuardedLive, isFalse);
    expect(item.isConverted, isTrue);
    expect(item.liveAttemptId, 44);
    expect(item.liveOrderId, 55);
    expect(item.conversionStatus, 'live_order_created');
    expect(item.lastSyncStatus, 'filled');
  });

  test('dismissed and expired promotions parse as blocked non-orders', () {
    final dismissed = StrategyAutoBuyPromotion.fromJson(
      autoBuyPromotionJson(status: 'dismissed'),
    );
    final expired = StrategyAutoBuyPromotion.fromJson(
      autoBuyPromotionJson(status: 'expired'),
    );

    expect(dismissed.isDismissed, isTrue);
    expect(dismissed.isConverted, isFalse);
    expect(dismissed.canRunGuardedLive, isFalse);
    expect(dismissed.conversionBlockReason, 'promotion_dismissed');
    expect(expired.isExpired, isTrue);
    expect(expired.canRunGuardedLive, isFalse);
    expect(expired.conversionBlockReason, 'promotion_expired');
  });
}

Map<String, dynamic> autoBuyPromotionsJson({
  String status = 'pending',
}) {
  return {
    'provider': 'kis',
    'market': 'KR',
    'count': 1,
    'items': [autoBuyPromotionJson(status: status)],
    'safety': {
      'read_only': true,
      'validation_called': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
    },
  };
}

Map<String, dynamic> autoBuyPromotionJson({
  String status = 'pending',
}) {
  final converted =
      status.startsWith('converted') || status.startsWith('live_order');
  final reviewStatus = status == 'pending'
      ? 'pending_review'
      : status == 'acknowledged' || status == 'reviewed'
          ? 'reviewed'
          : status == 'dismissed' || status == 'expired'
              ? status
              : converted
                  ? 'converted'
                  : status;
  final conversionBlockReason = status == 'dismissed'
      ? 'promotion_dismissed'
      : status == 'expired'
          ? 'promotion_expired'
          : converted
              ? 'promotion_already_converted'
              : null;
  return {
    'id': 1,
    'provider': 'kis',
    'market': 'KR',
    'active_profile': 'safe',
    'symbol': '005930',
    'symbol_name': 'Samsung Electronics',
    'status': status,
    'raw_status': status,
    'review_status': reviewStatus,
    'review_required': status == 'pending',
    'review_checklist': [
      {
        'key': 'promotion_only',
        'ok': true,
        'label': 'Promotion item is not an order.'
      },
      {
        'key': 'final_confirmation_required',
        'ok': true,
        'label': 'Live conversion still requires final operator confirmation.'
      },
    ],
    'review_summary':
        '005930 was promoted from would_buy evidence for operator review.',
    'primary_risk_note': 'dry_run_only',
    'score_summary': {
      'score': 82,
      'final_score': 82,
      'buy_score': 80,
      'sell_score': 15,
      'confidence': 0.8,
      'label': 'score 82 / confidence 0.8',
    },
    'dry_run_evidence': {
      'action': 'would_buy',
      'source_signal_id': 11,
      'source_trade_run_id': 22,
      'source_order_id': 33,
    },
    'target_risk_summary': {
      'approved': true,
      'risk_flags': ['dry_run_only'],
      'gating_notes': ['promotion only'],
      'proposed_notional_krw': 30000,
      'max_notional_krw': 50000,
    },
    'proposed_notional_krw': 30000,
    'max_notional_krw': 50000,
    'promotion_age_minutes': 10,
    'expired': status == 'expired',
    'stale': status == 'expired',
    'conversion_allowed_by_state':
        status == 'pending' || status == 'acknowledged' || status == 'reviewed',
    'conversion_block_reason': conversionBlockReason,
    'promotion_reason': 'target_aware_risk_approved',
    'source_dry_run_signal_id': 11,
    'source_dry_run_trade_run_id': 22,
    'source_dry_run_order_id': 33,
    'dry_run_action': 'would_buy',
    'buy_score': 80,
    'sell_score': 15,
    'final_score': 82,
    'confidence': 0.8,
    'recommended_notional_krw': 30000,
    'simulated_quantity': 3,
    'simulated_price': 10000,
    'simulated_notional_krw': 30000,
    'target_risk_result': {'approved': true},
    'block_reason': null,
    'risk_flags': ['dry_run_only'],
    'gating_notes': ['promotion only'],
    'expires_at': '2026-06-26T01:45:00Z',
    'acknowledged_at': status == 'acknowledged' || status == 'reviewed'
        ? '2026-06-26T01:10:00Z'
        : null,
    'reviewed_at': status == 'acknowledged' || status == 'reviewed'
        ? '2026-06-26T01:10:00Z'
        : null,
    'dismissed_at': null,
    'promoted_to_live_attempt_id': converted ? 44 : null,
    'related_live_order_id': converted ? 55 : null,
    'converted_live_attempt_id': converted ? 44 : null,
    'converted_order_id': converted ? 55 : null,
    'converted_at': converted ? '2026-06-26T01:20:00Z' : null,
    'conversion_status': converted ? 'live_order_created' : null,
    'last_sync_at': converted ? '2026-06-26T01:25:00Z' : null,
    'last_sync_status': converted ? 'filled' : null,
    'trace_payload': {
      'promotion_id': 1,
      'source_dry_run_id': 22,
      'source_signal_id': 11,
      'source_trade_run_id': 22,
      'promotion_symbol': '005930',
      'promotion_profile': 'safe',
      'promotion_score': 82,
      'promotion_reason': 'target_aware_risk_approved',
      'converted_live_attempt_id': converted ? 44 : null,
      'converted_order_id': converted ? 55 : null,
      'last_sync_status': converted ? 'filled' : null,
    },
    'request_payload': {
      'scheduler_mode': 'strategy_auto_buy_scheduler_dry_run'
    },
    'response_payload': {'action': 'would_buy'},
    'created_at': '2026-06-26T01:00:00Z',
    'updated_at': '2026-06-26T01:00:00Z',
  };
}
