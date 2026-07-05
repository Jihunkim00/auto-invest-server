import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/daily_ops_summary.dart';

void main() {
  test('daily operations summary model parses nested read-only payload', () {
    final summary = DailyOpsSummary.fromJson(dailyOpsSummaryJson());

    expect(summary.date, '2026-07-03');
    expect(summary.provider, 'kis');
    expect(summary.market, 'KR');
    expect(summary.runtimeState.dryRun, isTrue);
    expect(summary.runtimeState.schedulerRealOrdersAllowed, isFalse);
    expect(summary.tradeActivity.guardedBuyAttemptCount, 1);
    expect(summary.tradeActivity.blockedAttemptCount, 2);
    expect(summary.pnlSummary.realizedPl, 800);
    expect(summary.pnlSummary.realizedPlPct, 0.08);
    expect(summary.pnlSummary.unrealizedPl, isNull);
    expect(summary.hasIncompletePnl, isTrue);
    expect(summary.orderSummary.syncRequiredCount, 1);
    expect(summary.promotionSummary.pending, 1);
    expect(summary.schedulerSummary.realOrderSubmitted, isFalse);
    expect(summary.reconciliation.status, 'attention_required');
    expect(summary.isAttentionRequired, isTrue);
    expect(summary.riskSummary.dailyTradeLimitRemaining, 2);
    expect(summary.details.recentOrders.first['symbol'], '005930');
    expect(summary.safety['broker_submit_called'], isFalse);
    expect(summary.safety['sync_called'], isFalse);
  });
}

Map<String, dynamic> dailyOpsSummaryJson({
  String provider = 'kis',
  String market = 'KR',
  String status = 'attention_required',
  double? unrealizedPl,
  int syncRequired = 1,
  int totalOrdersToday = 3,
}) {
  return {
    'date': '2026-07-03',
    'timezone': 'Asia/Seoul',
    'generated_at': '2026-07-03T02:30:00Z',
    'provider': provider,
    'market': market,
    'runtime_state': {
      'dry_run': true,
      'kill_switch': false,
      'kis_enabled': true,
      'kis_real_order_enabled': false,
      'scheduler_enabled': true,
      'scheduler_dry_run_only': true,
      'scheduler_real_orders_allowed': false,
      'bot_enabled': true,
      'active_profile': 'safe',
    },
    'trade_activity': {
      'guarded_buy_attempt_count': 1,
      'guarded_sell_attempt_count': 1,
      'submitted_buy_count': 1,
      'submitted_sell_count': 1,
      'filled_buy_count': 1,
      'filled_sell_count': 1,
      'blocked_attempt_count': 2,
      'dry_run_simulated_count': 1,
      'manual_live_count': 1,
    },
    'pnl_summary': {
      'currency': market == 'KR' ? 'KRW' : 'USD',
      'realized_pl': 800,
      'realized_pl_pct': 0.08,
      'unrealized_pl': unrealizedPl,
      'total_position_value': null,
      'cash': null,
      'closed_trade_count': 1,
      'open_position_count': 1,
      'incomplete_calculation_count': unrealizedPl == null ? 1 : 0,
      'audit_flags': unrealizedPl == null
          ? ['unrealized_pnl_unavailable_local_only']
          : const [],
      'data_source': 'local_order_logs_and_cached_snapshots',
    },
    'order_summary': {
      'total_orders_today': totalOrdersToday,
      'status_buckets': {
        'submitted': 1,
        'filled': 1,
        'partially_filled': 0,
        'rejected': 0,
        'canceled': 0,
        'pending_sync': syncRequired,
        'unknown': 0,
      },
      'sync_required_count': syncRequired,
      'stale_order_count': syncRequired,
      'latest_order_status_at': '2026-07-03T02:10:00Z',
    },
    'promotion_summary': {
      'created_today': 1,
      'pending': 1,
      'reviewed': 0,
      'acknowledged': 0,
      'dismissed': 0,
      'converted': 0,
      'expired_or_stale': 0,
      'blocked_conversion_count': 1,
    },
    'scheduler_summary': {
      'scheduler_enabled': true,
      'dry_run_only': true,
      'run_count_today': 1,
      'would_buy_count': 1,
      'hold_count': 0,
      'skipped_count': 0,
      'promotion_created_count': 1,
      'real_order_submitted': false,
    },
    'reconciliation': {
      'status': status,
      'broker_read_available': false,
      'open_order_mismatch_count': 0,
      'local_pending_without_broker_status_count': syncRequired,
      'broker_order_without_local_link_count': 0,
      'missing_kis_odno_count': syncRequired,
      'missing_broker_order_id_count': syncRequired,
      'stale_sync_count': syncRequired,
      'warnings': [
        'local_summary_only_no_broker_read',
        if (syncRequired > 0) 'local_orders_require_status_sync',
      ],
      'next_safe_actions': [
        'Review local orders and KIS order status in the Operations logs.',
        'Use existing explicit sync controls outside this summary if operator review confirms it is safe.',
      ],
    },
    'risk_summary': {
      'daily_trade_limit_used': 1,
      'daily_trade_limit_remaining': 2,
      'daily_loss_limit_status': 'ok',
      'kill_switch_status': 'off',
      'duplicate_order_risk_count': 0,
      'open_position_count': 1,
      'max_position_warning': null,
      'no_new_entry_window_status': 'not_active',
    },
    'details': {
      'recent_orders': [
        {
          'id': 12,
          'provider': provider,
          'market': market,
          'symbol': '005930',
          'side': 'buy',
          'internal_status': 'SUBMITTED',
          'broker_status': 'submitted',
          'needs_sync': syncRequired > 0,
          'dry_run': false,
        }
      ],
      'recent_promotions': [
        {
          'id': 7,
          'symbol': '005930',
          'status': 'pending',
          'dry_run_action': 'would_buy',
        }
      ],
      'recent_guarded_buy_attempts': [
        {
          'id': 3,
          'symbol': '005930',
          'status': 'submitted',
        }
      ],
      'recent_guarded_sell_attempts': [
        {
          'id': 4,
          'symbol': '005930',
          'status': 'blocked',
          'block_reason': 'target_risk_rejected',
        }
      ],
      'sync_required_items': [
        {
          'id': 12,
          'symbol': '005930',
          'side': 'buy',
          'internal_status': 'SUBMITTED',
        }
      ],
      'blocked_items': [
        {
          'id': 4,
          'side': 'sell',
          'symbol': '005930',
          'status': 'blocked',
          'block_reason': 'target_risk_rejected',
        }
      ],
      'lifecycle_summary_references': [
        {
          'source': 'local_orders',
          'status': status,
          'broker_read_available': false,
        }
      ],
    },
    'safety': {
      'read_only': true,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'validation_called': false,
      'sync_called': false,
      'setting_changed': false,
      'scheduler_changed': false,
      'order_state_mutated': false,
    },
  };
}
