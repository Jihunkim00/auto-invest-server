import 'package:flutter_test/flutter_test.dart';
import 'package:auto_invest_dashboard/models/scheduler_status.dart';

void main() {
  test('fresh heartbeat cannot hide stalled or degraded scheduler progress', () {
    for (final health in ['stalled', 'stopped', 'degraded', 'unknown']) {
      final status = SchedulerStatus.fromJson({
        'scheduler_engine_running': true,
        'scheduler_health_status': health,
        'scheduler_last_heartbeat_at': DateTime.now().toUtc().toIso8601String(),
      });
      expect(status.schedulerHeartbeatHealthy, isFalse);
    }
    final healthy = SchedulerStatus.fromJson({
      'scheduler_engine_running': true,
      'scheduler_health_status': 'healthy',
      'scheduler_last_heartbeat_at': DateTime.now().toUtc().toIso8601String(),
    });
    expect(healthy.schedulerHeartbeatHealthy, isTrue);
  });
}
