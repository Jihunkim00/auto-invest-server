import 'package:flutter/material.dart';

import '../../../core/i18n/app_strings.dart';
import '../../../core/utils/timestamp_formatter.dart';
import '../../../core/widgets/section_card.dart';
import '../../../models/automation_release.dart';
import '../../dashboard/dashboard_controller.dart';

class AutomationReleaseControlPanel extends StatefulWidget {
  const AutomationReleaseControlPanel({super.key, required this.controller});

  final DashboardController controller;

  @override
  State<AutomationReleaseControlPanel> createState() =>
      _AutomationReleaseControlPanelState();
}

class _AutomationReleaseControlPanelState
    extends State<AutomationReleaseControlPanel> {
  final _reasonController = TextEditingController();
  bool _acknowledged = false;

  @override
  void dispose() {
    _reasonController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: widget.controller,
      builder: (context, _) {
        final controller = widget.controller;
        final strings = controller.strings;
        final status = controller.automationReleaseStatus;
        final run = controller.automationReleaseCycleResult;
        final loading = controller.automationReleaseLoading;
        final color = _statusColor(status?.effectiveStatus);
        return SectionCard(
          key: const ValueKey('automation-release-control-panel'),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(Icons.admin_panel_settings_outlined,
                      color: color, size: 22),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          strings.controlledFullAutomationRelease,
                          style: const TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w900,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          strings.automationRelease,
                          style: const TextStyle(color: Colors.white70),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    key: const ValueKey('automation-release-refresh-icon'),
                    tooltip: strings.refreshAutomationReleaseStatus,
                    onPressed: loading ? null : () => _refresh(context),
                    icon: loading
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.refresh),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              _BadgeWrap(labels: strings.automationReleaseBadges),
              const SizedBox(height: 10),
              _SafetyNotes(strings: strings),
              if (controller.automationReleaseError != null) ...[
                const SizedBox(height: 10),
                Text(
                  controller.automationReleaseError!,
                  style: const TextStyle(color: Colors.orangeAccent),
                ),
              ],
              const SizedBox(height: 12),
              if (status == null)
                _Banner(
                  icon: Icons.lock_outline,
                  label: strings.releasePreflightRequired,
                  detail: strings.statusNotLoaded,
                  color: Colors.white54,
                )
              else ...[
                _ReleaseSummary(status: status, strings: strings),
                const SizedBox(height: 12),
                _ChecklistPreview(status: status, strings: strings),
              ],
              if (run != null) ...[
                const SizedBox(height: 12),
                _LatestCycle(run: run, strings: strings),
              ],
              const SizedBox(height: 12),
              TextField(
                key: const ValueKey('automation-release-reason-field'),
                controller: _reasonController,
                minLines: 1,
                maxLines: 3,
                decoration: InputDecoration(
                  labelText: strings.optionalReason,
                  border: const OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 8),
              CheckboxListTile(
                key: const ValueKey('automation-release-risk-ack-checkbox'),
                contentPadding: EdgeInsets.zero,
                value: _acknowledged,
                controlAffinity: ListTileControlAffinity.leading,
                onChanged: loading
                    ? null
                    : (value) => setState(() => _acknowledged = value ?? false),
                title: Text(strings.armWithRiskAcknowledgement),
              ),
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  OutlinedButton.icon(
                    key: const ValueKey('automation-release-refresh-button'),
                    onPressed: loading ? null : () => _refresh(context),
                    icon: const Icon(Icons.refresh, size: 18),
                    label: Text(strings.refreshAutomationReleaseStatus),
                  ),
                  OutlinedButton.icon(
                    key: const ValueKey('automation-release-preflight-button'),
                    onPressed: loading ? null : () => _preflight(context),
                    icon: const Icon(Icons.fact_check_outlined, size: 18),
                    label: Text(strings.releasePreflight),
                  ),
                  FilledButton.icon(
                    key: const ValueKey('automation-release-arm-button'),
                    onPressed:
                        loading || !_acknowledged ? null : () => _arm(context),
                    icon: const Icon(Icons.verified_user_outlined, size: 18),
                    label: Text(strings.armRelease),
                  ),
                  OutlinedButton.icon(
                    key: const ValueKey('automation-release-disarm-button'),
                    onPressed: loading ? null : () => _disarm(context),
                    icon: const Icon(Icons.power_settings_new, size: 18),
                    label: Text(strings.disarmRelease),
                  ),
                  OutlinedButton.icon(
                    key: const ValueKey(
                        'automation-release-monitoring-cycle-button'),
                    onPressed:
                        loading ? null : () => _runCycle(context, 'monitoring'),
                    icon: const Icon(Icons.visibility_outlined, size: 18),
                    label: Text(strings.runReleaseMonitoringCycle),
                  ),
                  OutlinedButton.icon(
                    key: const ValueKey(
                        'automation-release-dry-run-cycle-button'),
                    onPressed:
                        loading ? null : () => _runCycle(context, 'dry_run'),
                    icon: const Icon(Icons.play_arrow_outlined, size: 18),
                    label: Text(strings.runReleaseDryRunCycle),
                  ),
                ],
              ),
            ],
          ),
        );
      },
    );
  }

  Future<void> _refresh(BuildContext context) async {
    final result = await widget.controller.refreshAutomationReleaseStatus();
    if (!context.mounted) return;
    _snack(context, result);
  }

  Future<void> _preflight(BuildContext context) async {
    final result = await widget.controller.runAutomationReleasePreflight();
    if (!context.mounted) return;
    _snack(context, result);
  }

  Future<void> _arm(BuildContext context) async {
    final result = await widget.controller.armAutomationRelease(
      operatorAcknowledgedRisks: _acknowledged,
      reason: _reasonController.text,
    );
    if (!context.mounted) return;
    if (result.success) setState(() => _acknowledged = false);
    _snack(context, result);
  }

  Future<void> _disarm(BuildContext context) async {
    final result = await widget.controller.disarmAutomationRelease(
      reason: _reasonController.text,
    );
    if (!context.mounted) return;
    _snack(context, result);
  }

  Future<void> _runCycle(BuildContext context, String mode) async {
    final result = await widget.controller.runAutomationReleaseCycleOnce(
      mode: mode,
    );
    if (!context.mounted) return;
    _snack(context, result);
  }

  void _snack(BuildContext context, ActionResult result) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(result.message),
        backgroundColor: result.success ? Colors.green : Colors.redAccent,
      ),
    );
  }
}

class _SafetyNotes extends StatelessWidget {
  const _SafetyNotes({required this.strings});

  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(strings.releaseArmDoesNotChangeDryRun),
        Text(strings.releaseArmDoesNotChangeKillSwitch),
        Text(strings.releaseArmDoesNotEnableRealOrders),
      ],
    );
  }
}

class _ReleaseSummary extends StatelessWidget {
  const _ReleaseSummary({required this.status, required this.strings});

  final AutomationReleaseStatus status;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    final color = _statusColor(status.effectiveStatus);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _Banner(
          icon: status.liveReady
              ? Icons.task_alt
              : Icons.admin_panel_settings_outlined,
          label: strings.effectiveStatus,
          detail: strings.releaseStatusLabel(status.effectiveStatus),
          color: color,
        ),
        const SizedBox(height: 10),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            _Metric(
              label: strings.automationRelease,
              value: status.releaseArmed ? strings.enabled : strings.disabled,
              valueColor:
                  status.releaseArmed ? Colors.greenAccent : Colors.white70,
            ),
            _Metric(
              label: strings.liveOrderEligibility,
              value:
                  status.canSubmitLiveOrder ? strings.ready : strings.blocked,
              valueColor: status.canSubmitLiveOrder
                  ? Colors.greenAccent
                  : Colors.orangeAccent,
            ),
            _Metric(
              label: strings.monitoringReady,
              value: strings.booleanLabel(status.canRunMonitoringCycle),
            ),
            _Metric(
              label: strings.dryRunReadyRelease,
              value: strings.booleanLabel(status.canRunDryRunCycle),
            ),
            _Metric(
              label: strings.phase1LiveReadyRelease,
              value: strings.booleanLabel(status.canRunLivePhase1Cycle),
            ),
            _Metric(
              label: strings.ordersRemaining,
              value: '${status.dailyTradeLimitRemaining}',
            ),
            _Metric(
              label: strings.autoBuySecond,
              value: '${status.dailyAutoBuyRemaining}',
            ),
            _Metric(
              label: strings.autoSellFirst,
              value: '${status.dailyAutoSellRemaining}',
            ),
          ],
        ),
        if (status.releaseArmedAt != null) ...[
          const SizedBox(height: 8),
          _Line(
            label: strings.modeUpdated,
            value: formatTimestampWithKst(
              status.releaseArmedAt!.toIso8601String(),
            ),
          ),
        ],
        if (status.blockingReasons.isNotEmpty) ...[
          const SizedBox(height: 8),
          _ReasonList(
            title: strings.blockingReasons,
            reasons: status.blockingReasons,
            color: Colors.orangeAccent,
            strings: strings,
          ),
        ],
        if (status.warningReasons.isNotEmpty) ...[
          const SizedBox(height: 8),
          _ReasonList(
            title: strings.warningReasons,
            reasons: status.warningReasons,
            color: Colors.amberAccent,
            strings: strings,
          ),
        ],
        const SizedBox(height: 8),
        _Line(
          label: strings.nextSafeAction,
          value: strings.automationControlLabel(status.nextSafeAction),
          valueColor: Colors.lightBlueAccent,
        ),
      ],
    );
  }
}

class _ChecklistPreview extends StatelessWidget {
  const _ChecklistPreview({required this.status, required this.strings});

  final AutomationReleaseStatus status;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    final visible = status.checklist.take(8).toList(growable: false);
    return _DetailBox(
      keyName: 'automation-release-checklist',
      children: [
        Text(
          strings.checklist,
          style: const TextStyle(fontWeight: FontWeight.w900),
        ),
        const SizedBox(height: 8),
        for (final item in visible)
          _ChecklistLine(item: item, strings: strings),
      ],
    );
  }
}

class _LatestCycle extends StatelessWidget {
  const _LatestCycle({required this.run, required this.strings});

  final AutomationReleaseCycleResult run;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    return _DetailBox(
      keyName: 'automation-release-latest-cycle',
      children: [
        Text(
          strings.latestRun,
          style: const TextStyle(fontWeight: FontWeight.w900),
        ),
        const SizedBox(height: 8),
        _Line(
          label: strings.status,
          value: strings.statusLabel(run.resultStatus),
          valueColor: run.completed ? Colors.greenAccent : Colors.orangeAccent,
        ),
        _Line(label: strings.actionTaken, value: run.actionTaken),
        _Line(
          label: strings.noBrokerSubmitRelease,
          value: strings.booleanLabel(!run.brokerSubmitCalled),
        ),
        _Line(
          label: strings.noOrderCancelRelease,
          value: strings.booleanLabel(!run.orderCancelCalled),
        ),
      ],
    );
  }
}

class _ChecklistLine extends StatelessWidget {
  const _ChecklistLine({required this.item, required this.strings});

  final AutomationReleaseChecklistItem item;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    final color = item.passed
        ? Colors.greenAccent
        : item.blocking
            ? Colors.orangeAccent
            : Colors.amberAccent;
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Icon(
          item.passed ? Icons.check_circle_outline : Icons.error_outline,
          color: color,
          size: 17,
        ),
        const SizedBox(width: 7),
        Expanded(
          child: Text(
            item.reason == null
                ? item.label
                : '${item.label}: ${strings.automationControlLabel(item.reason!)}',
            style: const TextStyle(color: Colors.white70),
          ),
        ),
      ]),
    );
  }
}

class _ReasonList extends StatelessWidget {
  const _ReasonList({
    required this.title,
    required this.reasons,
    required this.color,
    required this.strings,
  });

  final String title;
  final List<String> reasons;
  final Color color;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    return _DetailBox(
      keyName: 'automation-release-$title',
      children: [
        Text(title,
            style: TextStyle(color: color, fontWeight: FontWeight.w900)),
        const SizedBox(height: 6),
        if (reasons.isEmpty)
          Text(strings.none, style: const TextStyle(color: Colors.white60))
        else
          for (final reason in reasons)
            Text(
              strings.automationControlLabel(reason),
              style: const TextStyle(color: Colors.white70),
            ),
      ],
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

class _Banner extends StatelessWidget {
  const _Banner({
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
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.30)),
      ),
      child: Row(children: [
        Icon(icon, color: color, size: 20),
        const SizedBox(width: 8),
        Expanded(
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(label, style: const TextStyle(fontWeight: FontWeight.w800)),
            const SizedBox(height: 3),
            Text(
              detail,
              style: TextStyle(
                color: color,
                fontSize: 18,
                fontWeight: FontWeight.w900,
              ),
            ),
          ]),
        ),
      ]),
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
      width: 172,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label,
            style: const TextStyle(color: Colors.white60, fontSize: 12)),
        const SizedBox(height: 4),
        Text(
          value,
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            color: valueColor ?? Colors.white,
            fontWeight: FontWeight.w900,
          ),
        ),
      ]),
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

class _Line extends StatelessWidget {
  const _Line({
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
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SizedBox(
          width: 150,
          child: Text(label, style: const TextStyle(color: Colors.white60)),
        ),
        Expanded(
          child: Text(
            value,
            style: TextStyle(
              color: valueColor ?? Colors.white70,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
      ]),
    );
  }
}

Color _statusColor(String? status) {
  switch (status?.trim().toLowerCase()) {
    case 'live_ready':
    case 'dry_run_ready':
    case 'monitoring_ready':
      return Colors.greenAccent;
    case 'live_ready_blocked':
    case 'preflight_required':
    case 'kill_latched':
    case 'unsafe':
      return Colors.orangeAccent;
    case 'disabled':
    default:
      return Colors.white54;
  }
}
