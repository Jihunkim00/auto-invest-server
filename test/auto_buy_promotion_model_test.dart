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
    expect(item.sourceDryRunTradeRunId, 22);
    expect(item.finalScore, 82);
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
    expect(result.promotion.canRunGuardedLive, isFalse);
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
  return {
    'id': 1,
    'provider': 'kis',
    'market': 'KR',
    'active_profile': 'safe',
    'symbol': '005930',
    'symbol_name': 'Samsung Electronics',
    'status': status,
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
    'acknowledged_at': status == 'acknowledged' ? '2026-06-26T01:10:00Z' : null,
    'dismissed_at': null,
    'promoted_to_live_attempt_id':
        status == 'pending' || status == 'acknowledged' ? null : 44,
    'related_live_order_id':
        status == 'pending' || status == 'acknowledged' ? null : 55,
    'converted_live_attempt_id':
        status == 'pending' || status == 'acknowledged' ? null : 44,
    'converted_order_id':
        status == 'pending' || status == 'acknowledged' ? null : 55,
    'converted_at': status == 'pending' || status == 'acknowledged'
        ? null
        : '2026-06-26T01:20:00Z',
    'conversion_status': status == 'pending' || status == 'acknowledged'
        ? null
        : 'live_order_created',
    'last_sync_at': status == 'pending' || status == 'acknowledged'
        ? null
        : '2026-06-26T01:25:00Z',
    'last_sync_status':
        status == 'pending' || status == 'acknowledged' ? null : 'filled',
    'trace_payload': {
      'promotion_id': 1,
      'source_dry_run_id': 22,
      'source_signal_id': 11,
      'source_trade_run_id': 22,
      'promotion_symbol': '005930',
      'promotion_profile': 'safe',
      'promotion_score': 82,
      'promotion_reason': 'target_aware_risk_approved',
      'converted_live_attempt_id':
          status == 'pending' || status == 'acknowledged' ? null : 44,
      'converted_order_id':
          status == 'pending' || status == 'acknowledged' ? null : 55,
      'last_sync_status':
          status == 'pending' || status == 'acknowledged' ? null : 'filled',
    },
    'request_payload': {
      'scheduler_mode': 'strategy_auto_buy_scheduler_dry_run'
    },
    'response_payload': {'action': 'would_buy'},
    'created_at': '2026-06-26T01:00:00Z',
    'updated_at': '2026-06-26T01:00:00Z',
  };
}
