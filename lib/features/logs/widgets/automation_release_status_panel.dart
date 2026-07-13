import 'package:flutter/material.dart';

import '../../../core/i18n/app_strings.dart';
import '../../../core/utils/timestamp_formatter.dart';
import '../../../models/automation_release.dart';
import '../../dashboard/dashboard_controller.dart';

class AutomationReleaseStatusPanel extends StatelessWidget {
  const AutomationReleaseStatusPanel({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final strings = controller.strings;
        final status = controller.automationReleaseStatus;
        final run = controller.automationReleaseCycleResult;
        final loading = controller.automationReleaseLoading;
        final color = _statusColor(status?.effectiveStatus);
        return Container(
          key: const ValueKey('automation-release-status-panel'),
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
              Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Icon(Icons.admin_panel_settings_outlined,
                    color: color, size: 20),
                const SizedBox(width: 8),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        strings.automationRelease,
                        style: const TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.w900,
                        ),
                      ),
                      const SizedBox(height: 3),
                      Text(
                        status == null
                            ? strings.controlledFullAutomationRelease
                            : '${strings.controlledFullAutomationRelease} / ${_timestamp(status.generatedAt)}',
                        style: const TextStyle(color: Colors.white70),
                      ),
                    ],
                  ),
                ),
                IconButton(
                  key: const ValueKey('automation-release-status-refresh'),
                  tooltip: strings.refreshAutomationReleaseStatus,
                  onPressed: loading
                      ? null
                      : () async {
                          final result =
                              await controller.refreshAutomationReleaseStatus();
                          if (!context.mounted) return;
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(content: Text(result.message)),
                          );
                        },
                  icon: loading
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.refresh),
                ),
              ]),
              const SizedBox(height: 10),
              _BadgeWrap(labels: strings.automationReleaseBadges),
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
                  label: strings.releasePreflightRequired,
                  detail: strings.statusNotLoaded,
                  color: Colors.white54,
                )
              else
                _StatusSummary(status: status, strings: strings),
              if (run != null) ...[
                const SizedBox(height: 10),
                _LatestCycle(run: run, strings: strings),
              ],
            ],
          ),
        );
      },
    );
  }
}

class _StatusSummary extends StatelessWidget {
  const _StatusSummary({required this.status, required this.strings});

  final AutomationReleaseStatus status;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    final color = _statusColor(status.effectiveStatus);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      _Banner(
        label: strings.effectiveStatus,
        detail: strings.releaseStatusLabel(status.effectiveStatus),
        color: color,
      ),
      const SizedBox(height: 10),
      Wrap(spacing: 8, runSpacing: 8, children: [
        _Metric(
          label: strings.automationRelease,
          value: status.releaseEnabled ? strings.enabled : strings.disabled,
          valueColor:
              status.releaseEnabled ? Colors.greenAccent : Colors.white70,
        ),
        _Metric(
          label: strings.liveOrderEligibility,
          value: status.canSubmitLiveOrder ? strings.ready : strings.blocked,
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
      ]),
      const SizedBox(height: 10),
      if (status.blockingReasons.isNotEmpty)
        _ReasonBlock(
          title: strings.blockingReasons,
          reasons: status.blockingReasons,
          color: Colors.orangeAccent,
          strings: strings,
        ),
      if (status.warningReasons.isNotEmpty) ...[
        const SizedBox(height: 8),
        _ReasonBlock(
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
      const SizedBox(height: 10),
      _Checklist(status: status, strings: strings),
    ]);
  }
}

class _Checklist extends StatelessWidget {
  const _Checklist({required this.status, required this.strings});

  final AutomationReleaseStatus status;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    return _Box(
      keyName: 'automation-release-status-checklist',
      children: [
        Text(strings.checklist,
            style: const TextStyle(fontWeight: FontWeight.w900)),
        const SizedBox(height: 8),
        if (status.checklist.isEmpty)
          Text(strings.none, style: const TextStyle(color: Colors.white70))
        else
          for (final item in status.checklist)
            Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child:
                  Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Icon(
                  item.passed
                      ? Icons.check_circle_outline
                      : Icons.error_outline,
                  color: item.passed
                      ? Colors.greenAccent
                      : item.blocking
                          ? Colors.orangeAccent
                          : Colors.amberAccent,
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
            ),
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
    return _Box(
      keyName: 'automation-release-status-latest-cycle',
      children: [
        Text(strings.latestRun,
            style: const TextStyle(fontWeight: FontWeight.w900)),
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

class _ReasonBlock extends StatelessWidget {
  const _ReasonBlock({
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
    return _Box(
      keyName: 'automation-release-status-$title',
      children: [
        Text(title,
            style: TextStyle(color: color, fontWeight: FontWeight.w900)),
        const SizedBox(height: 6),
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
    required this.label,
    required this.detail,
    required this.color,
  });

  final String label;
  final String detail;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.36)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label,
            style: TextStyle(color: color, fontWeight: FontWeight.w900)),
        const SizedBox(height: 2),
        Text(detail, style: TextStyle(color: color.withValues(alpha: 0.88))),
      ]),
    );
  }
}

class _Metric extends StatelessWidget {
  const _Metric({required this.label, required this.value, this.valueColor});

  final String label;
  final String value;
  final Color? valueColor;

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(minWidth: 136),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label,
            style: const TextStyle(color: Colors.white60, fontSize: 11)),
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
      ]),
    );
  }
}

class _Box extends StatelessWidget {
  const _Box({required this.children, required this.keyName});

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
  const _Line({required this.label, required this.value, this.valueColor});

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
              height: 1.25,
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

String _timestamp(DateTime value) {
  return formatTimestampWithKst(value.toIso8601String());
}
