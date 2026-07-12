import 'package:flutter/material.dart';

import '../../../core/i18n/app_strings.dart';
import '../../../core/utils/timestamp_formatter.dart';
import '../../../models/automation_soak_test.dart';
import '../../dashboard/dashboard_controller.dart';

class AutomationSoakTestPanel extends StatefulWidget {
  const AutomationSoakTestPanel({super.key, required this.controller});

  final DashboardController controller;

  @override
  State<AutomationSoakTestPanel> createState() =>
      _AutomationSoakTestPanelState();
}

class _AutomationSoakTestPanelState extends State<AutomationSoakTestPanel> {
  bool _rulesExpanded = false;
  bool _resetAcknowledged = false;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: widget.controller,
      builder: (context, _) {
        final controller = widget.controller;
        final strings = controller.strings;
        final status = controller.automationSoakStatus;
        final run = controller.automationSoakRunResult;
        final loading = controller.automationSoakLoading;
        final killLatchActive =
            status?.killLatchActive == true || run?.killLatchActive == true;
        final color = _statusColor(status?.effectiveStatus, killLatchActive);
        return Container(
          key: const ValueKey('automation-soak-test-panel'),
          width: double.infinity,
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: Colors.black.withValues(alpha: 0.24),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(Icons.hourglass_top_outlined, color: color, size: 20),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          strings.automationSoakTest,
                          style: const TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w900,
                          ),
                        ),
                        const SizedBox(height: 3),
                        Text(
                          status == null
                              ? strings.longRunStabilityCheck
                              : '${strings.longRunStabilityCheck} / ${_timestamp(status.generatedAt)}',
                          style: const TextStyle(color: Colors.white70),
                        ),
                      ],
                    ),
                  ),
                  if (loading)
                    const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                ],
              ),
              const SizedBox(height: 10),
              _BadgeWrap(labels: strings.automationSoakBadges),
              if (controller.automationSoakError != null) ...[
                const SizedBox(height: 10),
                Text(
                  controller.automationSoakError!,
                  style: const TextStyle(color: Colors.orangeAccent),
                ),
              ],
              const SizedBox(height: 12),
              if (status == null)
                _StatusBanner(
                  icon: Icons.hourglass_empty_outlined,
                  label: strings.longRunStabilityCheck,
                  detail: strings.statusNotLoaded,
                  color: Colors.white54,
                )
              else
                _SoakSummary(status: status, strings: strings),
              if (run != null) ...[
                const SizedBox(height: 10),
                _LatestRun(run: run, strings: strings),
              ],
              if (_rulesExpanded) ...[
                const SizedBox(height: 10),
                _KillRuleDetails(
                  rules: status?.killRules ??
                      run?.killRulesEvaluated ??
                      const <AutomationKillRule>[],
                  strings: strings,
                ),
              ],
              const SizedBox(height: 12),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  OutlinedButton.icon(
                    key: const ValueKey('refresh-automation-soak-status'),
                    onPressed: loading ? null : () => _refresh(context),
                    icon: const Icon(Icons.refresh, size: 18),
                    label: Text(strings.refreshAutomationSoakStatus),
                  ),
                  FilledButton.icon(
                    key: const ValueKey('run-automation-soak-once'),
                    onPressed: loading ? null : () => _runOnce(context),
                    icon: const Icon(Icons.play_arrow_outlined, size: 18),
                    label: Text(strings.runSoakOnce),
                  ),
                  TextButton.icon(
                    key: const ValueKey('toggle-automation-soak-kill-rules'),
                    onPressed: () {
                      setState(() => _rulesExpanded = !_rulesExpanded);
                    },
                    icon: Icon(
                      _rulesExpanded ? Icons.expand_less : Icons.expand_more,
                    ),
                    label: Text(
                      _rulesExpanded
                          ? strings.collapseKillRules
                          : strings.expandKillRules,
                    ),
                  ),
                ],
              ),
              if (killLatchActive) ...[
                const SizedBox(height: 10),
                _ResetLatchControls(
                  acknowledged: _resetAcknowledged,
                  loading: loading,
                  strings: strings,
                  onAcknowledgedChanged: (value) {
                    setState(() => _resetAcknowledged = value);
                  },
                  onReset: () => _resetKillLatch(context),
                ),
              ],
            ],
          ),
        );
      },
    );
  }

  Future<void> _refresh(BuildContext context) async {
    final action = await widget.controller.refreshAutomationSoak();
    if (!context.mounted) return;
    _snack(context, action.message);
  }

  Future<void> _runOnce(BuildContext context) async {
    final action = await widget.controller.runAutomationSoakOnce();
    if (!context.mounted) return;
    _snack(context, action.message);
  }

  Future<void> _resetKillLatch(BuildContext context) async {
    final action = await widget.controller.resetAutomationSoakKillLatch(
      operatorAcknowledgedRisks: _resetAcknowledged,
      reason: 'operator_reset_from_logs_panel',
    );
    if (!context.mounted) return;
    if (action.success) {
      setState(() => _resetAcknowledged = false);
    }
    _snack(context, action.message);
  }

  void _snack(BuildContext context, String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
    );
  }
}

class _SoakSummary extends StatelessWidget {
  const _SoakSummary({required this.status, required this.strings});

  final AutomationSoakStatus status;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    final color = _statusColor(status.effectiveStatus, status.killLatchActive);
    final syncHealth = _mapString(status.latestWatchdogStatus, 'sync_health');
    final triggeredRules = status.triggeredRules;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _StatusBanner(
          icon: status.killLatchActive
              ? Icons.lock_outline
              : Icons.verified_outlined,
          label: status.killLatchActive
              ? strings.killLatchActive
              : strings.effectiveStatus,
          detail: strings.automationControlLabel(status.effectiveStatus),
          color: color,
        ),
        const SizedBox(height: 10),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            _Metric(
              label: strings.status,
              value: status.canRunSoakCycle ? strings.ready : strings.blocked,
              valueColor:
                  status.canRunSoakCycle ? Colors.greenAccent : color,
            ),
            _Metric(
              label: strings.soakMode,
              value: strings.automationControlLabel(status.soakMode),
            ),
            _Metric(
              label: strings.cyclesToday,
              value: '${status.cycleCountToday} / ${status.maxCyclesPerDay}',
              valueColor: status.cycleCountToday >= status.maxCyclesPerDay
                  ? Colors.orangeAccent
                  : null,
            ),
            _Metric(
              label: strings.actionsToday,
              value: '${status.actionCountToday} / ${status.maxActionsPerDay}',
              valueColor: status.actionCountToday >= status.maxActionsPerDay
                  ? Colors.orangeAccent
                  : null,
            ),
            _Metric(
              label: strings.consecutiveFailures,
              value:
                  '${status.consecutiveFailureCount} / ${status.maxConsecutiveFailures}',
              valueColor: status.consecutiveFailureCount > 0
                  ? Colors.orangeAccent
                  : null,
            ),
            _Metric(
              label: strings.dailyLossStatusLabel,
              value: strings.automationControlLabel(status.dailyLossStatus),
              valueColor: status.dailyLossStatus == 'ok'
                  ? Colors.greenAccent
                  : Colors.orangeAccent,
            ),
            _Metric(
              label: strings.orderPositionSyncHealth,
              value: strings.brokerSyncHealthLabel(syncHealth),
              valueColor: _syncColor(syncHealth),
            ),
            _Metric(
              label: strings.productionReadiness,
              value: strings.readinessStatusLabel(
                status.productionReadinessStatus,
              ),
            ),
            _Metric(
              label: strings.triggeredRules,
              value: '${triggeredRules.length}',
              valueColor:
                  triggeredRules.isEmpty ? Colors.greenAccent : color,
            ),
          ],
        ),
        const SizedBox(height: 8),
        if (status.killLatchReason != null)
          _DetailLine(
            label: strings.killLatch,
            value: status.killLatchReason!,
            valueColor: Colors.orangeAccent,
          ),
        if (status.blockingReasons.isNotEmpty)
          _DetailLine(
            label: strings.primaryBlockingReasons,
            value: status.blockingReasons
                .map(strings.automationControlLabel)
                .join(' | '),
            valueColor: Colors.orangeAccent,
          ),
        if (status.warningReasons.isNotEmpty)
          _DetailLine(
            label: strings.warningReasons,
            value: status.warningReasons
                .map(strings.automationControlLabel)
                .join(' | '),
            valueColor: Colors.amberAccent,
          ),
        _DetailLine(
          label: strings.nextSafeAction,
          value: strings.automationControlLabel(status.nextSafeAction),
          valueColor: Colors.lightBlueAccent,
        ),
      ],
    );
  }
}

class _LatestRun extends StatelessWidget {
  const _LatestRun({required this.run, required this.strings});

  final AutomationSoakRunResult run;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    final color = run.completed ? Colors.greenAccent : Colors.orangeAccent;
    return _DetailBox(
      keyName: 'automation-soak-latest-run',
      children: [
        Text(
          strings.latestRun,
          style: const TextStyle(fontWeight: FontWeight.w900),
        ),
        const SizedBox(height: 8),
        _DetailLine(
          label: strings.status,
          value: strings.statusLabel(run.resultStatus),
          valueColor: color,
        ),
        _DetailLine(
          label: strings.actionTaken,
          value: strings.statusLabel(run.actionTaken),
        ),
        _DetailLine(
          label: strings.orderPositionSyncHealth,
          value: strings.brokerSyncHealthLabel(run.brokerSyncHealth),
          valueColor: _syncColor(run.brokerSyncHealth),
        ),
        _DetailLine(
          label: strings.rulesEvaluated,
          value: '${run.killRulesEvaluated.length}',
        ),
        _DetailLine(
          label: strings.triggeredRules,
          value: '${run.killRulesTriggered.length}',
          valueColor: run.killRulesTriggered.isEmpty
              ? Colors.greenAccent
              : Colors.orangeAccent,
        ),
        _DetailLine(
          label: strings.nextSafeAction,
          value: strings.automationControlLabel(run.nextSafeAction),
          valueColor: Colors.lightBlueAccent,
        ),
      ],
    );
  }
}

class _KillRuleDetails extends StatelessWidget {
  const _KillRuleDetails({required this.rules, required this.strings});

  final List<AutomationKillRule> rules;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    return _DetailBox(
      keyName: 'automation-soak-kill-rules',
      children: [
        Text(
          strings.killRules,
          style: const TextStyle(fontWeight: FontWeight.w900),
        ),
        const SizedBox(height: 8),
        if (rules.isEmpty)
          Text(strings.none, style: const TextStyle(color: Colors.white70))
        else
          for (final rule in rules)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: _RuleTile(rule: rule, strings: strings),
            ),
      ],
    );
  }
}

class _RuleTile extends StatelessWidget {
  const _RuleTile({required this.rule, required this.strings});

  final AutomationKillRule rule;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    final color = rule.triggered
        ? rule.critical
            ? Colors.redAccent
            : Colors.orangeAccent
        : Colors.white54;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: 6,
            runSpacing: 6,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              _SmallBadge(
                label: strings.statusLabel(rule.severity),
                color: color,
              ),
              Text(
                strings.automationControlLabel(rule.ruleId),
                style: const TextStyle(fontWeight: FontWeight.w900),
              ),
            ],
          ),
          const SizedBox(height: 6),
          _DetailLine(label: strings.reason, value: rule.reason),
          _DetailLine(
            label: strings.recommendedAction,
            value: strings.automationControlLabel(rule.recommendedAction),
            valueColor: Colors.lightBlueAccent,
          ),
          _DetailLine(
            label: strings.status,
            value: strings.booleanLabel(rule.triggered),
            valueColor: rule.triggered ? color : Colors.greenAccent,
          ),
          _DetailLine(label: strings.stage, value: rule.source),
          _DetailLine(
            label: strings.generatedAt,
            value: _timestamp(rule.detectedAt),
          ),
        ],
      ),
    );
  }
}

class _ResetLatchControls extends StatelessWidget {
  const _ResetLatchControls({
    required this.acknowledged,
    required this.loading,
    required this.strings,
    required this.onAcknowledgedChanged,
    required this.onReset,
  });

  final bool acknowledged;
  final bool loading;
  final AppStrings strings;
  final ValueChanged<bool> onAcknowledgedChanged;
  final VoidCallback onReset;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.orangeAccent.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: Colors.orangeAccent.withValues(alpha: 0.30),
        ),
      ),
      child: Wrap(
        spacing: 8,
        runSpacing: 8,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          SizedBox(
            width: 320,
            child: Row(
              children: [
                Checkbox(
                  key: const ValueKey('automation-soak-reset-ack'),
                  value: acknowledged,
                  onChanged: loading
                      ? null
                      : (value) => onAcknowledgedChanged(value == true),
                ),
                Expanded(
                  child: Text(
                    strings.resetWithRiskAcknowledgement,
                    style: const TextStyle(fontWeight: FontWeight.w800),
                  ),
                ),
              ],
            ),
          ),
          OutlinedButton.icon(
            key: const ValueKey('reset-automation-soak-kill-latch'),
            onPressed: loading || !acknowledged ? null : onReset,
            icon: const Icon(Icons.lock_open_outlined, size: 18),
            label: Text(strings.resetKillLatch),
          ),
        ],
      ),
    );
  }
}

class _BadgeWrap extends StatelessWidget {
  const _BadgeWrap({required this.labels});

  final List<String> labels;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 6,
      runSpacing: 6,
      children: [
        for (final label in labels)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(999),
              border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
            ),
            child: Text(
              label,
              style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w800),
            ),
          ),
      ],
    );
  }
}

class _StatusBanner extends StatelessWidget {
  const _StatusBanner({
    required this.icon,
    required this.label,
    required this.detail,
    required this.color,
  });

  final IconData icon;
  final String label;
  final String detail;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 9),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.36)),
      ),
      child: Row(
        children: [
          Icon(icon, color: color, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  style: TextStyle(color: color, fontWeight: FontWeight.w900),
                ),
                const SizedBox(height: 2),
                Text(
                  detail,
                  style: TextStyle(color: color.withValues(alpha: 0.88)),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Metric extends StatelessWidget {
  const _Metric({
    required this.label,
    required this.value,
    this.valueColor,
  });

  final String label;
  final String value;
  final Color? valueColor;

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(minWidth: 132),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            label,
            style: const TextStyle(color: Colors.white60, fontSize: 11),
          ),
          const SizedBox(height: 3),
          Text(
            value,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: valueColor ?? Colors.white,
              fontWeight: FontWeight.w900,
            ),
          ),
        ],
      ),
    );
  }
}

class _DetailBox extends StatelessWidget {
  const _DetailBox({required this.children, required this.keyName});

  final List<Widget> children;
  final String keyName;

  @override
  Widget build(BuildContext context) {
    return Container(
      key: ValueKey(keyName),
      width: double.infinity,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: children,
      ),
    );
  }
}

class _SmallBadge extends StatelessWidget {
  const _SmallBadge({required this.label, required this.color});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.28)),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: color,
          fontSize: 11,
          fontWeight: FontWeight.w900,
        ),
      ),
    );
  }
}

class _DetailLine extends StatelessWidget {
  const _DetailLine({
    required this.label,
    required this.value,
    this.valueColor,
  });

  final String label;
  final String value;
  final Color? valueColor;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 150,
            child: Text(
              label,
              style: const TextStyle(color: Colors.white60),
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              value,
              style: TextStyle(
                color: valueColor ?? Colors.white70,
                height: 1.25,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

Color _statusColor(String? status, bool killLatchActive) {
  if (killLatchActive) return Colors.orangeAccent;
  switch (status?.trim().toLowerCase()) {
    case 'dry_run_ready':
    case 'live_phase1_ready':
      return Colors.greenAccent;
    case 'monitoring':
      return Colors.lightBlueAccent;
    case 'unsafe':
    case 'live_phase1_blocked':
    case 'kill_latched':
      return Colors.orangeAccent;
    case 'disabled':
    default:
      return Colors.white54;
  }
}

Color _syncColor(String health) {
  switch (health.trim().toLowerCase()) {
    case 'healthy':
      return Colors.greenAccent;
    case 'warning':
      return Colors.amberAccent;
    case 'unsafe':
      return Colors.orangeAccent;
    case 'unknown':
    default:
      return Colors.white54;
  }
}

String _timestamp(DateTime? value) {
  if (value == null) return '-';
  return formatTimestampWithKst(value.toIso8601String());
}

String _mapString(Map<String, dynamic> value, String key) {
  final raw = value[key]?.toString().trim();
  if (raw == null || raw.isEmpty || raw == 'null') return 'unknown';
  return raw;
}
