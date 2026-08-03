import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/operation_mode.dart';

void main() {
  test('status parses backend facade fields', () {
    final status = OperationModeStatus.fromJson({
      'requested_mode': 'live',
      'effective_mode': 'paper',
      'display_label': 'Paper - blocked',
      'status': 'blocked',
      'safety_status': 'blocked',
      'can_change_mode': true,
      'can_enter_paper': true,
      'can_enter_live': false,
      'can_enter_paused': true,
      'requires_acknowledgement': {'live': true},
      'mode_drift_detected': true,
      'blocking_reasons': [
        {'code': 'dry_run', 'message': 'dry_run must be false'},
      ],
      'warnings': [
        {'code': 'audit', 'message': 'operator review required'},
      ],
      'underlying_state': {'dry_run': true},
      'last_changed_at': '2026-07-26T09:00:00Z',
      'last_changed_by': 'api',
    });

    expect(status.requestedMode, 'live');
    expect(status.effectiveMode, 'paper');
    expect(status.isBlocked, isTrue);
    expect(status.canEnter('live'), isFalse);
    expect(status.requiresAcknowledgementFor('live'), isTrue);
    expect(status.blockingReasons.single.code, 'dry_run');
    expect(status.underlyingState['dry_run'], isTrue);
  });

  test('unknown mode never normalizes to live', () {
    final status = OperationModeStatus.fromJson({
      'requested_mode': 'full_live_test_mode',
      'effective_mode': null,
      'display_label': '',
      'status': 'active',
      'safety_status': 'ready',
    });

    expect(status.requestedMode, 'paper');
    expect(status.effectiveMode, 'paper');
    expect(OperationModeStatus.normalizeMode(null), 'paper');
    expect(OperationModeStatus.normalizeMode('unexpected'), 'paper');
  });
}
