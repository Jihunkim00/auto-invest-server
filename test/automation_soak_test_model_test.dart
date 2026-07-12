import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/automation_soak_test.dart';

void main() {
  test('automation soak status parses kill rules and safety flags', () {
    final status = AutomationSoakStatus.fromJson(
      automationSoakStatusJson(
        effectiveStatus: 'kill_latched',
        killLatchActive: true,
        killLatchReason: 'broker_sync_unsafe',
        blockingReasons: const ['broker_sync_unsafe'],
        killRules: [
          automationKillRuleJson(
            ruleId: 'broker_sync_unsafe',
            triggered: true,
            severity: 'critical',
          ),
          automationKillRuleJson(
            ruleId: 'unexpected_broker_submit_flag',
            triggered: false,
          ),
        ],
      ),
    );

    expect(status.soakEnabled, isTrue);
    expect(status.killLatchActive, isTrue);
    expect(status.killLatchReason, 'broker_sync_unsafe');
    expect(status.effectiveStatus, 'kill_latched');
    expect(status.triggeredRules, hasLength(1));
    expect(status.triggeredRules.single.ruleId, 'broker_sync_unsafe');
    expect(status.safetyFlags['broker_submit_called'], isFalse);
    expect(status.latestWatchdogStatus['sync_health'], 'healthy');
  });

  test('automation soak run parses blocked safety result', () {
    final run = AutomationSoakRunResult.fromJson(
      automationSoakRunJson(
        resultStatus: 'blocked',
        killLatchActive: true,
        blockingReasons: const ['daily_loss_limit_breached'],
        killRulesTriggered: [
          automationKillRuleJson(
            ruleId: 'daily_loss_limit_breached',
            triggered: true,
          ),
        ],
      ),
    );

    expect(run.completed, isFalse);
    expect(run.killLatchActive, isTrue);
    expect(run.blockingReasons, contains('daily_loss_limit_breached'));
    expect(run.killRulesTriggered.single.triggered, isTrue);
    expect(run.realOrderSubmitted, isFalse);
    expect(run.brokerSubmitCalled, isFalse);
    expect(run.orderCancelCalled, isFalse);
  });
}

Map<String, dynamic> automationKillRuleJson({
  String ruleId = 'broker_sync_unsafe',
  String severity = 'critical',
  bool triggered = true,
}) {
  return {
    'rule_id': ruleId,
    'name': ruleId,
    'severity': severity,
    'triggered': triggered,
    'automation_blocking': triggered,
    'reason': 'test rule',
    'detected_at': '2026-07-12T00:00:00Z',
    'source': 'unit_test',
    'recommended_action': 'manual_review',
  };
}

Map<String, dynamic> automationSoakStatusJson({
  bool soakEnabled = true,
  String soakMode = 'dry_run_monitoring',
  bool allowLivePhase1 = false,
  bool killLatchActive = false,
  String? killLatchReason,
  String effectiveStatus = 'dry_run_ready',
  bool canRunSoakCycle = true,
  bool canAttemptLivePhase1 = false,
  bool canSubmitLiveOrder = false,
  int cycleCountToday = 1,
  int maxCyclesPerDay = 3,
  int actionCountToday = 0,
  int maxActionsPerDay = 1,
  int consecutiveFailureCount = 0,
  int maxConsecutiveFailures = 2,
  String productionReadinessStatus = 'ready',
  String dailyLossStatus = 'ok',
  List<String> blockingReasons = const [],
  List<String> warningReasons = const [],
  List<Map<String, dynamic>> killRules = const [],
}) {
  return {
    'generated_at': '2026-07-12T00:00:00Z',
    'soak_enabled': soakEnabled,
    'soak_mode': soakMode,
    'allow_live_phase1': allowLivePhase1,
    'kill_latch_active': killLatchActive,
    'kill_latch_reason': killLatchReason,
    'kill_latch_triggered_at':
        killLatchActive ? '2026-07-12T00:01:00Z' : null,
    'effective_status': effectiveStatus,
    'can_run_soak_cycle': canRunSoakCycle,
    'can_attempt_live_phase1': canAttemptLivePhase1,
    'can_submit_live_order': canSubmitLiveOrder,
    'cycle_count_today': cycleCountToday,
    'max_cycles_per_day': maxCyclesPerDay,
    'action_count_today': actionCountToday,
    'max_actions_per_day': maxActionsPerDay,
    'consecutive_failure_count': consecutiveFailureCount,
    'max_consecutive_failures': maxConsecutiveFailures,
    'latest_orchestrator_result': {'result_status': 'dry_run_completed'},
    'latest_watchdog_status': {'sync_health': 'healthy'},
    'automation_mode_status': {'effective_status': 'dry_run_ready'},
    'production_readiness_status': productionReadinessStatus,
    'daily_loss_status': dailyLossStatus,
    'kill_rules': killRules,
    'blocking_reasons': blockingReasons,
    'warning_reasons': warningReasons,
    'next_safe_action': blockingReasons.isEmpty
        ? 'review_dry_run_results'
        : 'manual_review',
    'safety_flags': const {
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'order_cancel_called': false,
    },
  };
}

Map<String, dynamic> automationSoakRunJson({
  String resultStatus = 'dry_run_completed',
  bool killLatchActive = false,
  List<String> blockingReasons = const [],
  List<Map<String, dynamic>> killRulesTriggered = const [],
}) {
  return {
    'run_id': 91,
    'generated_at': '2026-07-12T00:02:00Z',
    'provider': 'kis',
    'market': 'KR',
    'soak_mode': 'dry_run_monitoring',
    'trigger_source': 'manual_soak_test',
    'result_status': resultStatus,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'order_cancel_called': false,
    'action_taken': 'none',
    'orchestrator_run_id': 90,
    'broker_sync_health': 'healthy',
    'automation_mode_effective_status': 'dry_run_ready',
    'production_readiness_status': 'ready',
    'kill_rules_evaluated': [
      automationKillRuleJson(triggered: false),
      ...killRulesTriggered,
    ],
    'kill_rules_triggered': killRulesTriggered,
    'kill_latch_active': killLatchActive,
    'cycle_count_today': 2,
    'action_count_today': 0,
    'consecutive_failure_count': killLatchActive ? 1 : 0,
    'risk_flags': const [],
    'gating_notes': const [],
    'blocking_reasons': blockingReasons,
    'warning_reasons': const [],
    'next_safe_action':
        blockingReasons.isEmpty ? 'review_dry_run_results' : 'manual_review',
    'safety_flags': const {
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'order_cancel_called': false,
    },
  };
}
