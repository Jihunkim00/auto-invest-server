import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/position_lifecycle.dart';

void main() {
  test('position lifecycle parses open and closed items safely', () {
    final lifecycle = PositionLifecycle.fromJson(positionLifecycleJson());

    expect(lifecycle.provider, 'kis');
    expect(lifecycle.market, 'KR');
    expect(lifecycle.safety['read_only'], isTrue);
    expect(lifecycle.totals.openPositionCount, 1);
    expect(lifecycle.totals.closedLifecycleCount, 1);
    expect(lifecycle.totals.totalRealizedPl, 800);
    expect(lifecycle.items, hasLength(2));

    final closed = lifecycle.items.firstWhere((item) => item.isClosed);
    expect(closed.symbol, '005930');
    expect(closed.displayName, '005930 Samsung');
    expect(closed.entrySource, 'promotion_conversion');
    expect(closed.entryOrderId, 12);
    expect(closed.exitOrderId, 42);
    expect(closed.realizedPl, 800);
    expect(closed.realizedPlPct, 0.08);
    expect(closed.relatedPromotionId, 3);
    expect(closed.events.map((event) => event.eventType), [
      'promotion_created',
      'guarded_buy_submitted',
      'sell_preflight',
      'guarded_sell_submitted',
      'sell_filled',
      'position_closed',
    ]);

    final open = lifecycle.items.firstWhere((item) => item.isOpen);
    expect(open.currentQuantity, 1);
    expect(open.unrealizedPl, -200);
    expect(open.hasIncompleteCalculation, isFalse);
  });

  test('position lifecycle marks missing realized P/L as incomplete', () {
    final lifecycle = PositionLifecycle.fromJson(
      positionLifecycleJson(realizedMissing: true),
    );

    final closed = lifecycle.items.firstWhere((item) => item.isClosed);
    expect(closed.realizedPl, isNull);
    expect(closed.hasIncompleteCalculation, isTrue);
    expect(closed.auditFlags, contains('calculation_incomplete'));
    expect(lifecycle.totals.incompleteCalculationCount, 1);
  });
}

Map<String, dynamic> positionLifecycleJson({bool realizedMissing = false}) {
  return {
    'provider': 'kis',
    'market': 'KR',
    'generated_at': '2026-07-03T02:00:00Z',
    'totals': {
      'open_position_count': 1,
      'closed_lifecycle_count': 1,
      'total_current_value': 4900,
      'total_unrealized_pl': -200,
      'total_realized_pl': realizedMissing ? 0 : 800,
      'total_realized_pl_pct': realizedMissing ? null : 0.08,
      'incomplete_calculation_count': realizedMissing ? 1 : 0,
    },
    'safety': {
      'read_only': true,
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'submit_service_called': false,
      'sync_called': false,
    },
    'audit_flags': ['read_only_lifecycle'],
    'items': [
      {
        'lifecycle_id': 'kis:KR:005930:buy-12:sell-42:1',
        'symbol': '005930',
        'name': 'Samsung',
        'provider': 'kis',
        'market': 'KR',
        'lifecycle_status': 'closed',
        'entry_source': 'promotion_conversion',
        'entry_order_id': 12,
        'entry_broker_order_id': 'KIS-BUY-1',
        'entry_kis_odno': 'KIS-BUY-1',
        'entry_submitted_at': '2026-07-03T00:00:00Z',
        'entry_filled_at': '2026-07-03T00:01:00Z',
        'entry_quantity': 2,
        'entry_average_price': 5000,
        'entry_notional': 10000,
        'related_promotion_id': 3,
        'related_signal_id': 9,
        'current_quantity': 0,
        'current_price': null,
        'current_value': null,
        'cost_basis': 10000,
        'unrealized_pl': null,
        'unrealized_pl_pct': null,
        'exit_order_id': 42,
        'exit_broker_order_id': 'KIS-SELL-1',
        'exit_kis_odno': 'KIS-SELL-1',
        'exit_submitted_at': '2026-07-03T01:00:00Z',
        'exit_filled_at': '2026-07-03T01:01:00Z',
        'exit_quantity': 2,
        'exit_average_price': realizedMissing ? null : 5400,
        'exit_notional': realizedMissing ? null : 10800,
        'realized_pl': realizedMissing ? null : 800,
        'realized_pl_pct': realizedMissing ? null : 0.08,
        'fees': null,
        'holding_period_minutes': 60,
        'latest_status': 'FILLED',
        'latest_broker_status': 'filled',
        'risk_flags': const [],
        'gating_notes': const ['Guarded sell manual only.'],
        'audit_flags': realizedMissing
            ? ['read_only_lifecycle', 'calculation_incomplete']
            : ['read_only_lifecycle'],
        'next_safe_action': realizedMissing
            ? 'review_missing_lifecycle_data'
            : 'review_audit_trail',
        'events': [
          _event('promotion_created', '2026-07-02T23:50:00Z'),
          _event('guarded_buy_submitted', '2026-07-03T00:00:00Z'),
          _event('sell_preflight', '2026-07-03T00:55:00Z'),
          _event('guarded_sell_submitted', '2026-07-03T01:00:00Z'),
          _event('sell_filled', '2026-07-03T01:01:00Z'),
          _event('position_closed', '2026-07-03T01:01:00Z'),
        ],
      },
      {
        'lifecycle_id': 'kis:KR:000660:buy-13:open',
        'symbol': '000660',
        'name': 'SK Hynix',
        'provider': 'kis',
        'market': 'KR',
        'lifecycle_status': 'open',
        'entry_source': 'manual_live_buy',
        'entry_order_id': 13,
        'entry_quantity': 1,
        'entry_average_price': 5100,
        'entry_notional': 5100,
        'current_quantity': 1,
        'current_price': 4900,
        'current_value': 4900,
        'cost_basis': 5100,
        'unrealized_pl': -200,
        'unrealized_pl_pct': -0.039216,
        'latest_status': 'FILLED',
        'risk_flags': const [],
        'gating_notes': const [],
        'audit_flags': ['read_only_lifecycle'],
        'next_safe_action': 'monitor_or_run_sell_preflight',
        'events': [
          _event('guarded_buy_submitted', '2026-07-03T01:20:00Z'),
          _event('position_opened', '2026-07-03T01:21:00Z'),
        ],
      },
    ],
  };
}

Map<String, dynamic> _event(String type, String timestamp) {
  return {
    'timestamp': timestamp,
    'event_type': type,
    'title': type,
    'status': 'filled',
    'source': 'test',
    'related_id': 'test:1',
    'summary': 'test event',
    'safety_flags': ['read_only_lifecycle'],
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
  };
}
