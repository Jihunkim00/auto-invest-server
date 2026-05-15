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

  test('TradingLogItem labels KIS exit preflight as preflight only', () {
    final item = TradingLogItem.fromJson({
      'id': 12,
      'run_key': 'kis-exit-preflight',
      'provider': 'kis',
      'market': 'KR',
      'symbol': '005930',
      'trigger_source': 'manual_kis_live_exit_preflight',
      'mode': 'kis_live_exit_preflight',
      'action': 'sell',
      'result': 'exit_candidate',
      'reason': 'stop_loss_triggered',
      'gate_level': 2,
      'created_at': '2026-05-08T00:01:00',
      'preflight': true,
      'simulated': false,
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'source': 'kis_live_exit_preflight',
      'manual_confirm_required': true,
      'auto_sell_enabled': false,
      'scheduler_real_order_enabled': false,
    });

    expect(item.sourceLabel, 'KIS EXIT PREFLIGHT');
    expect(
      item.safetyBadges,
      containsAll([
        'EXIT PREFLIGHT',
        'PREFLIGHT ONLY',
        'NO BROKER SUBMIT',
        'NO AUTO SELL',
        'MANUAL CONFIRMATION REQUIRED',
        'SCHEDULER REAL ORDERS DISABLED',
      ]),
    );
    expect(item.safetyBadges, isNot(contains('MANUAL ONLY')));
    expect(item.isKisManualLive, isFalse);
  });

  test('TradingLogItem labels KIS shadow exit as dry-run no-submit', () {
    final item = TradingLogItem.fromJson({
      'id': 13,
      'run_key': 'kis-exit-shadow',
      'provider': 'kis',
      'market': 'KR',
      'symbol': '005930',
      'trigger_source': 'shadow_exit',
      'mode': 'shadow_exit_dry_run',
      'source': 'kis_exit_shadow_decision',
      'source_type': 'dry_run_sell_simulation',
      'action': 'sell',
      'result': 'would_sell',
      'reason': 'would_sell_stop_loss',
      'gate_level': 2,
      'created_at': '2026-05-08T00:01:00',
      'dry_run': true,
      'simulated': true,
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'real_order_submit_allowed': false,
      'manual_confirm_required': true,
      'auto_sell_enabled': false,
      'scheduler_real_order_enabled': false,
      'exit_trigger': 'stop_loss',
      'exit_trigger_source': 'cost_basis_pl_pct',
      'suggested_quantity': 2,
      'cost_basis': 144000,
      'current_value': 141120,
      'current_price': 70560,
      'unrealized_pl': -2880,
      'unrealized_pl_pct': -0.02,
    });

    expect(item.sourceLabel, 'KIS SHADOW EXIT');
    expect(item.isKisExitShadow, isTrue);
    expect(item.isKisDryRunAuto, isFalse);
    expect(item.exitTrigger, 'stop_loss');
    expect(item.unrealizedPlPct, -0.02);
    expect(
      item.safetyBadges,
      containsAll([
        'SHADOW EXIT',
        'DRY RUN',
        'DRY RUN SELL SIMULATION',
        'WOULD SELL',
        'NO BROKER SUBMIT',
        'NO MANUAL SUBMIT',
        'LIVE AUTO SELL DISABLED',
        'MANUAL CONFIRMATION REQUIRED',
        'SCHEDULER REAL ORDERS DISABLED',
      ]),
    );
    expect(item.safetyBadges, isNot(contains('MANUAL ONLY')));
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

  test('OrderLogItem exposes exit preflight manual sell lifecycle fields', () {
    final item = OrderLogItem.fromJson({
      'id': 32,
      'order_id': 32,
      'provider': 'kis',
      'broker': 'kis',
      'market': 'KR',
      'mode': 'manual_live',
      'source': 'kis_live_exit_preflight',
      'source_type': 'manual_confirm_exit',
      'exit_trigger': 'stop_loss',
      'exit_trigger_source': 'cost_basis_pl_pct',
      'symbol': '005930',
      'side': 'sell',
      'qty': 2,
      'filled_quantity': 1,
      'remaining_quantity': 1,
      'average_fill_price': 72000,
      'internal_status': 'PARTIALLY_FILLED',
      'broker_order_status': 'partial',
      'kis_odno': '0001234567',
      'created_at': '2026-05-08T00:02:00',
      'updated_at': '2026-05-08T00:03:00',
      'last_synced_at': '2026-05-08T00:04:00',
      'real_order_submitted': true,
      'broker_submit_called': true,
      'manual_submit_called': true,
      'manual_confirm_required': true,
      'auto_sell_enabled': false,
      'scheduler_real_order_enabled': false,
      'risk_flags': ['stop_loss_triggered'],
      'gating_notes': ['manual_confirm_required'],
    });

    expect(item.sourceLabel, 'KIS MANUAL LIVE');
    expect(item.source, 'kis_live_exit_preflight');
    expect(item.sourceType, 'manual_confirm_exit');
    expect(item.exitTrigger, 'stop_loss');
    expect(item.exitTriggerSource, 'cost_basis_pl_pct');
    expect(item.filledQuantity, 1);
    expect(item.remainingQuantity, 1);
    expect(item.averageFillPrice, 72000);
    expect(item.lastSyncedAt, '2026-05-08T00:04:00');
    expect(
      item.safetyBadges,
      containsAll([
        'EXIT PREFLIGHT',
        'REAL ORDER SUBMITTED',
        'MANUAL SUBMIT',
        'NO AUTO SELL',
        'MANUAL CONFIRMATION REQUIRED',
        'SCHEDULER REAL ORDERS DISABLED',
      ]),
    );
  });

  test('OrderLogItem distinguishes preflight-only from manual live submit', () {
    final preflightOnly = OrderLogItem.fromJson({
      'id': 33,
      'order_id': 33,
      'provider': 'kis',
      'broker': 'kis',
      'market': 'KR',
      'mode': 'kis_live_exit_preflight',
      'trigger_source': 'manual_kis_live_exit_preflight',
      'source': 'kis_live_exit_preflight',
      'source_type': 'manual_confirm_exit',
      'exit_trigger': 'manual_review',
      'symbol': '005930',
      'side': 'sell',
      'qty': 2,
      'internal_status': 'PREFLIGHT_ONLY',
      'created_at': '2026-05-08T00:02:00',
      'updated_at': '2026-05-08T00:03:00',
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'manual_confirm_required': true,
      'auto_sell_enabled': false,
      'scheduler_real_order_enabled': false,
    });
    final submitted = OrderLogItem.fromJson({
      'id': 34,
      'order_id': 34,
      'provider': 'kis',
      'broker': 'kis',
      'market': 'KR',
      'mode': 'manual_live',
      'source': 'kis_live_exit_preflight',
      'source_type': 'manual_confirm_exit',
      'exit_trigger': 'take_profit',
      'symbol': '005930',
      'side': 'sell',
      'qty': 2,
      'internal_status': 'FILLED',
      'broker_order_status': 'filled',
      'kis_odno': '0001234567',
      'filled_quantity': 2,
      'average_fill_price': 73000,
      'created_at': '2026-05-08T00:04:00',
      'updated_at': '2026-05-08T00:05:00',
      'real_order_submitted': true,
      'broker_submit_called': true,
      'manual_submit_called': true,
      'manual_confirm_required': true,
      'auto_sell_enabled': false,
      'scheduler_real_order_enabled': false,
    });

    expect(preflightOnly.sourceLabel, 'KIS EXIT PREFLIGHT');
    expect(preflightOnly.orderLabel, 'No broker order');
    expect(
      preflightOnly.safetyBadges,
      containsAll([
        'PREFLIGHT ONLY',
        'NO BROKER SUBMIT',
        'MANUAL CONFIRMATION REQUIRED',
      ]),
    );
    expect(preflightOnly.safetyBadges, isNot(contains('MANUAL SUBMIT')));

    expect(submitted.sourceLabel, 'KIS MANUAL LIVE');
    expect(submitted.orderLabel, '0001234567');
    expect(submitted.filledQuantity, 2);
    expect(submitted.averageFillPrice, 73000);
    expect(submitted.safetyBadges, contains('MANUAL SUBMIT'));
    expect(submitted.safetyBadges, isNot(contains('PREFLIGHT ONLY')));
  });

  test('OrderLogItem keeps rejected and canceled lifecycle details', () {
    final rejected = OrderLogItem.fromJson({
      'id': 35,
      'provider': 'kis',
      'broker': 'kis',
      'market': 'KR',
      'symbol': '005930',
      'side': 'sell',
      'qty': 1,
      'internal_status': 'REJECTED',
      'broker_order_status': 'rejected',
      'rejected_reason': 'price band rejected',
      'created_at': '2026-05-08T00:04:00',
      'updated_at': '2026-05-08T00:05:00',
    });
    final canceled = OrderLogItem.fromJson({
      'id': 36,
      'provider': 'kis',
      'broker': 'kis',
      'market': 'KR',
      'symbol': '005930',
      'side': 'sell',
      'qty': 1,
      'internal_status': 'CANCELED',
      'broker_order_status': 'canceled',
      'created_at': '2026-05-08T00:06:00',
      'updated_at': '2026-05-08T00:07:00',
    });

    expect(rejected.statusLabel, 'rejected');
    expect(rejected.rejectedReason, 'price band rejected');
    expect(canceled.statusLabel, 'canceled');
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
