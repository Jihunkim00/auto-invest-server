import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/log_items.dart';

void main() {
  test('TradingLogItem labels KIS dry-run auto as simulated no-submit', () {
    final item = TradingLogItem.fromJson({
      'id': 10,
      'run_key': 'kis-dry-run',
      'provider': 'kis',
      'market': 'KR',
      'symbol': '005930',
      'trigger_source': 'manual_kis_dry_run_auto',
      'mode': 'kis_dry_run_auto',
      'action': 'buy',
      'result': 'simulated_order_created',
      'reason': 'dry_run_risk_approved',
      'order_id': 22,
      'signal_id': 21,
      'gate_level': 2,
      'created_at': '2026-05-08T00:00:00',
      'dry_run': true,
      'simulated': true,
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
    });

    expect(item.sourceLabel, 'KIS DRY-RUN AUTO');
    expect(item.safetyBadges, containsAll(['SIMULATED', 'NO BROKER SUBMIT']));
    expect(item.realOrderSubmitted, isFalse);
    expect(item.brokerSubmitCalled, isFalse);
    expect(item.manualSubmitCalled, isFalse);
  });

  test('TradingLogItem labels KIS preview as preview only', () {
    final item = TradingLogItem.fromJson({
      'id': 11,
      'run_key': 'kis-preview',
      'provider': 'kis',
      'market': 'KR',
      'symbol': 'WATCHLIST',
      'trigger_source': 'manual_kis_preview',
      'mode': 'kis_watchlist_preview',
      'action': 'hold',
      'result': 'preview_only',
      'reason': 'kr_trading_disabled',
      'gate_level': 2,
      'created_at': '2026-05-08T00:01:00',
      'dry_run': true,
      'preview_only': true,
      'real_order_submitted': false,
      'broker_submit_called': false,
    });

    expect(item.sourceLabel, 'KIS PREVIEW');
    expect(
        item.safetyBadges, containsAll(['PREVIEW ONLY', 'NO BROKER SUBMIT']));
    expect(item.previewOnly, isTrue);
    expect(item.realOrderSubmitted, isFalse);
  });

  test('OrderLogItem labels KIS manual live order as manual only', () {
    final item = OrderLogItem.fromJson({
      'id': 30,
      'order_id': 30,
      'provider': 'kis',
      'broker': 'kis',
      'market': 'KR',
      'symbol': '005930',
      'side': 'buy',
      'qty': 1,
      'internal_status': 'SUBMITTED',
      'broker_order_status': 'submitted',
      'kis_odno': '0001234567',
      'created_at': '2026-05-08T00:02:00',
      'updated_at': '2026-05-08T00:03:00',
      'real_order_submitted': true,
      'broker_submit_called': true,
      'manual_submit_called': true,
    });

    expect(item.sourceLabel, 'KIS MANUAL LIVE');
    expect(item.safetyBadges,
        containsAll(['REAL ORDER SUBMITTED', 'MANUAL ONLY']));
    expect(item.realOrderSubmitted, isTrue);
    expect(item.orderLabel, '0001234567');
    expect(item.currency, 'KRW');
  });

  test('OrderLogItem keeps explicit KRW currency for display', () {
    final item = OrderLogItem.fromJson({
      'id': 31,
      'order_id': 31,
      'provider': 'alpaca',
      'broker': 'alpaca',
      'market': 'US',
      'currency': 'KRW',
      'symbol': '005930',
      'side': 'buy',
      'qty': 1,
      'notional': 9801,
      'internal_status': 'submitted',
      'created_at': '2026-05-08T00:04:00',
      'updated_at': '2026-05-08T00:05:00',
    });

    expect(item.currency, 'KRW');
  });
}
