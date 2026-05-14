import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/kis_auto_readiness.dart';

void main() {
  test('KisAutoReadiness parses safety response null-safely', () {
    final result = KisAutoReadiness.fromJson(const {
      'auto_order_ready': false,
      'future_auto_order_ready': true,
      'live_auto_enabled': true,
      'real_order_submit_allowed': false,
      'reason': 'pr15_no_live_auto_submit_path',
      'checked_at': '2026-05-14T00:00:00Z',
      'preflight': true,
      'checks': {
        'dry_run': false,
        'kill_switch': false,
        'live_auto_buy_enabled': false,
        'live_auto_sell_enabled': true,
      },
      'safety': {
        'real_order_submitted': false,
        'broker_submit_called': false,
        'manual_submit_called': false,
        'requires_manual_confirm': true,
      },
      'blocked_by': ['pr15_no_live_auto_submit_path'],
    });

    expect(result.autoOrderReady, isFalse);
    expect(result.futureAutoOrderReady, isTrue);
    expect(result.liveAutoEnabled, isTrue);
    expect(result.realOrderSubmitAllowed, isFalse);
    expect(result.reason, 'pr15_no_live_auto_submit_path');
    expect(result.checkedAt, '2026-05-14T00:00:00Z');
    expect(result.preflight, isTrue);
    expect(result.check('dry_run'), isFalse);
    expect(result.check('live_auto_sell_enabled'), isTrue);
    expect(result.safetyFlag('real_order_submitted'), isFalse);
    expect(result.safetyFlag('requires_manual_confirm'), isTrue);
    expect(result.blockedBy, contains('pr15_no_live_auto_submit_path'));
  });

  test('KisAutoReadiness missing fields default to blocked', () {
    final result = KisAutoReadiness.fromJson(const {});

    expect(result.autoOrderReady, isFalse);
    expect(result.liveAutoEnabled, isFalse);
    expect(result.realOrderSubmitAllowed, isFalse);
    expect(result.reason, isEmpty);
    expect(result.check('dry_run'), isFalse);
    expect(result.safetyFlag('broker_submit_called'), isFalse);
  });

  test('safe default shows live auto blocked', () {
    final result = KisAutoReadiness.safeDefault();

    expect(result.autoOrderReady, isFalse);
    expect(result.liveAutoEnabled, isFalse);
    expect(result.realOrderSubmitAllowed, isFalse);
    expect(result.reason, 'live_auto_disabled_by_default');
    expect(result.safetyFlag('requires_manual_confirm'), isTrue);
  });
}
