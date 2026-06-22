import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/agent_chat_live_order_readiness.dart';

void main() {
  test('readiness model parses checks limits capabilities and safety', () {
    final readiness = AgentChatLiveOrderReadiness.fromJson(_readinessJson());

    expect(readiness.status, 'blocked');
    expect(readiness.ready, isFalse);
    expect(readiness.readyForChatConfirmedLiveOrder, isFalse);
    expect(readiness.provider, 'kis');
    expect(readiness.market, 'KR');
    expect(readiness.checks, hasLength(3));
    expect(readiness.blockingChecks.map((check) => check.key), [
      'dry_run',
      'agent_chat_live_order_enabled',
    ]);
    expect(readiness.limits.maxOrdersPerDay, 1);
    expect(readiness.limits.ordersUsedToday, 0);
    expect(readiness.limits.ordersRemainingToday, 1);
    expect(readiness.limits.maxNotionalKrw, 50000);
    expect(readiness.limits.maxNotionalPct, 0.03);
    expect(readiness.capabilities.buyEnabled, isFalse);
    expect(readiness.capabilities.sellEnabled, isTrue);
    expect(readiness.capabilities.marketOrderEnabled, isTrue);
    expect(readiness.safety['read_only'], isTrue);
    expect(readiness.safety['manual_submit_called'], isFalse);
  });

  test('settings apply result parses nested readiness', () {
    final result = AgentChatLiveOrderSettingsApplyResult.fromJson({
      'status': 'updated',
      'applied': true,
      'preset': 'chat_confirmed_buy_only',
      'changed_keys': ['agent_chat_live_order_buy_enabled'],
      'unchanged_keys': ['agent_chat_live_order_requires_confirm'],
      'audit_id': 12,
      'readiness': _readinessJson(ready: true),
      'settings': {'agent_chat_live_order_buy_enabled': true},
      'safety': {
        'real_order_submitted': false,
        'validation_called': false,
      },
      'warning_message': 'No order was submitted.',
    });

    expect(result.applied, isTrue);
    expect(result.preset, 'chat_confirmed_buy_only');
    expect(result.auditId, 12);
    expect(result.changedKeys, ['agent_chat_live_order_buy_enabled']);
    expect(result.readiness?.ready, isTrue);
    expect(result.safety['validation_called'], isFalse);
  });
}

Map<String, dynamic> _readinessJson({bool ready = false}) {
  return {
    'status': ready ? 'ready' : 'blocked',
    'ready': ready,
    'ready_for_chat_confirmed_live_order': ready,
    'provider': 'kis',
    'market': 'KR',
    'summary': ready ? 'Ready.' : 'Blocked.',
    'checks': [
      {
        'key': 'dry_run',
        'label': 'Dry Run',
        'ok': ready,
        'value': !ready,
        'severity': ready ? 'ok' : 'blocking',
        'message': ready ? 'OK.' : 'dry_run is ON.',
      },
      {
        'key': 'agent_chat_live_order_enabled',
        'label': 'Agent Chat Live Order',
        'ok': ready,
        'value': ready,
        'severity': ready ? 'ok' : 'blocking',
        'message': ready ? 'OK.' : 'Agent Chat live order is OFF.',
      },
      {
        'key': 'scheduler_real_orders_disabled',
        'label': 'Scheduler Real Orders Disabled',
        'ok': true,
        'value': true,
        'severity': 'ok',
        'message': 'OK.',
      },
    ],
    'blocking_reasons': ready
        ? const []
        : const [
            {'key': 'dry_run', 'message': 'dry_run is ON.'},
          ],
    'limits': {
      'max_orders_per_day': 1,
      'orders_used_today': 0,
      'orders_remaining_today': 1,
      'max_notional_krw': 50000,
      'max_notional_pct': 0.03,
    },
    'capabilities': {
      'buy_enabled': false,
      'sell_enabled': true,
      'market_order_enabled': true,
      'limit_order_enabled': false,
    },
    'runtime': {
      'dry_run': !ready,
      'kill_switch': false,
    },
    'market_session': {'available': true},
    'safety': {
      'read_only': true,
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'validation_called': false,
      'setting_changed': false,
      'scheduler_changed': false,
    },
  };
}
