import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/kis_shadow_exit_review_queue.dart';

void main() {
  test('parses KIS shadow exit review queue summary and items', () {
    final queue = KisShadowExitReviewQueue.fromJson(_queueJson());

    expect(queue.status, 'ok');
    expect(queue.mode, 'shadow_exit_review_queue');
    expect(queue.reviewWindowDays, 30);
    expect(queue.summary.openCount, 2);
    expect(queue.summary.reviewedCount, 3);
    expect(queue.summary.dismissedCount, 1);
    expect(queue.summary.wouldSellOpenCount, 1);
    expect(queue.summary.manualReviewOpenCount, 1);
    expect(queue.summary.repeatedSymbolCount, 1);
    expect(queue.summary.latestOpenAt, '2026-05-15T01:03:00+00:00');

    final item = queue.items.first;
    expect(item.queueId, '005930:take_profit:cost_basis_pl_pct');
    expect(item.symbol, '005930');
    expect(item.decision, 'would_sell');
    expect(item.action, 'sell');
    expect(item.trigger, 'take_profit');
    expect(item.triggerSource, 'cost_basis_pl_pct');
    expect(item.severity, 'review');
    expect(item.occurrenceCount, 3);
    expect(item.latestUnrealizedPl, 2500);
    expect(item.latestUnrealizedPlPct, 0.031);
    expect(item.latestCostBasis, 70000);
    expect(item.latestCurrentValue, 72170);
    expect(item.latestCurrentPrice, 72170);
    expect(item.suggestedQuantity, 1);
    expect(item.riskFlags, contains('take_profit_triggered'));
    expect(item.gatingNotes, contains('no_broker_submit'));
    expect(item.sourceRunId, 10);
    expect(item.sourceRunKey, 'shadow-linked');
    expect(item.sourceSignalId, 3);
    expect(item.linkedManualOrderId, 44);
    expect(item.linkedManualOrderStatus, 'FILLED');
    expect(item.linkedManualOrderFilledQuantity, 1);
    expect(item.linkedManualOrderAverageFillPrice, 72170);
    expect(item.status, 'open');
    expect(item.isOpen, isTrue);
    expect(item.realOrderSubmitted, isFalse);
    expect(item.brokerSubmitCalled, isFalse);
    expect(item.manualSubmitCalled, isFalse);
    expect(queue.safety.readOnly, isTrue);
    expect(queue.safety.operatorStateOnly, isTrue);
    expect(queue.safety.createsOrders, isFalse);
  });

  test('parsing is null-safe and tolerant of missing fields', () {
    final queue = KisShadowExitReviewQueue.fromJson({
      'summary': {
        'open_count': '1',
      },
      'items': [
        {
          'queue_id': '035420:manual_review:unknown',
          'symbol': '035420',
          'decision': 'manual_review',
          'latest_unrealized_pl_pct': null,
          'status': 'dismissed',
        }
      ],
    });

    expect(queue.status, 'ok');
    expect(queue.mode, 'shadow_exit_review_queue');
    expect(queue.summary.openCount, 1);
    expect(queue.summary.reviewedCount, 0);
    expect(queue.items.single.latestUnrealizedPlPct, isNull);
    expect(queue.items.single.isDismissed, isTrue);
    expect(queue.items.single.linkedManualOrderStatus, isNull);
    expect(queue.safety.readOnly, isTrue);
    expect(queue.safety.brokerSubmitCalled, isFalse);
  });
}

Map<String, dynamic> _queueJson() {
  return {
    'status': 'ok',
    'mode': 'shadow_exit_review_queue',
    'review_window_days': 30,
    'summary': {
      'open_count': 2,
      'reviewed_count': 3,
      'dismissed_count': 1,
      'would_sell_open_count': 1,
      'manual_review_open_count': 1,
      'repeated_symbol_count': 1,
      'latest_open_at': '2026-05-15T01:03:00+00:00',
    },
    'items': [
      {
        'queue_id': '005930:take_profit:cost_basis_pl_pct',
        'symbol': '005930',
        'decision': 'would_sell',
        'action': 'sell',
        'trigger': 'take_profit',
        'trigger_source': 'cost_basis_pl_pct',
        'severity': 'review',
        'occurrence_count': 3,
        'first_seen_at': '2026-05-15T01:00:00+00:00',
        'latest_seen_at': '2026-05-15T01:03:00+00:00',
        'latest_unrealized_pl': 2500,
        'latest_unrealized_pl_pct': 0.031,
        'latest_cost_basis': 70000,
        'latest_current_value': 72170,
        'latest_current_price': 72170,
        'suggested_quantity': 1,
        'reason':
            'Repeated shadow exit candidate. Manual operator review recommended.',
        'risk_flags': ['take_profit_triggered'],
        'gating_notes': ['shadow_exit_only', 'no_broker_submit'],
        'source_run_id': 10,
        'source_run_key': 'shadow-linked',
        'source_signal_id': 3,
        'linked_manual_order_id': 44,
        'linked_manual_order_status': 'FILLED',
        'linked_manual_order_created_at': '2026-05-15T01:05:00+00:00',
        'linked_manual_order_filled_quantity': 1,
        'linked_manual_order_average_fill_price': 72170,
        'status': 'open',
        'operator_note': null,
        'real_order_submitted': false,
        'broker_submit_called': false,
        'manual_submit_called': false,
      }
    ],
    'safety': {
      'read_only': true,
      'operator_state_only': true,
      'creates_orders': false,
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'auto_buy_enabled': false,
      'auto_sell_enabled': false,
      'scheduler_real_order_enabled': false,
    },
    'created_at': '2026-05-15T01:05:00+00:00',
  };
}
