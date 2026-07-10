import 'package:flutter/material.dart';

import '../../../core/i18n/app_strings.dart';
import '../../../models/automation_mode_control.dart';
import '../../dashboard/dashboard_controller.dart';

class AutomationModeStatusPanel extends StatelessWidget {
  const AutomationModeStatusPanel({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final strings = controller.strings;
        final status = controller.automationModeStatus;
        final loading = controller.automationModeLoading;
        return Container(
          key: const ValueKey('automation-mode-status-panel'),
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
                  const Icon(
                    Icons.tune_outlined,
                    color: Colors.lightBlueAccent,
                    size: 20,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          strings.automationModeControl,
                          style: const TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w900,
                          ),
                        ),
                        const SizedBox(height: 3),
                        Text(
                          strings.liveOrdersRemainBlocked,
                          style: const TextStyle(color: Colors.white70),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    key: const ValueKey('automation-mode-status-refresh'),
                    tooltip: strings.refresh,
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
              _BadgeWrap(labels: [
                strings.disabledByDefault,
                strings.noBrokerSubmitModeControl,
                strings.independentSafetyGatesRequired,
              ]),
              if (controller.automationModeError != null) ...[
                const SizedBox(height: 10),
                Text(
                  controller.automationModeError!,
                  style: const TextStyle(color: Colors.orangeAccent),
                ),
              ],
              const SizedBox(height: 12),
              if (status == null)
                Text(
                  strings.automationModeNotLoaded,
                  style: const TextStyle(color: Colors.white70),
                )
              else
                _StatusSummary(status: status, strings: strings),
            ],
          ),
        );
      },
    );
  }

  Future<void> _refresh(BuildContext context) async {
    final action = await controller.refreshAutomationModeStatus();
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(action.message)),
    );
  }
}

class _StatusSummary extends StatelessWidget {
  const _StatusSummary({required this.status, required this.strings});

  final AutomationModeControlStatus status;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    final color = status.canSubmitLiveOrder
        ? Colors.greenAccent
        : status.liveBlocked
            ? Colors.orangeAccent
            : Colors.lightBlueAccent;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _Banner(
          label: strings.liveOrderEligibility,
          value: status.canSubmitLiveOrder ? strings.ready : strings.blocked,
          color: color,
        ),
        const SizedBox(height: 10),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            _Metric(label: strings.currentMode, value: status.modeLabel),
            _Metric(
              label: strings.effectiveStatus,
              value: strings.automationControlLabel(status.effectiveStatus),
              valueColor: color,
            ),
            _Metric(
              label: strings.blockingReasons,
              value: '${status.blockingReasons.length}',
              valueColor: status.blockingReasons.isEmpty
                  ? Colors.greenAccent
                  : Colors.orangeAccent,
            ),
            _Metric(
              label: strings.warningReasons,
              value: '${status.warningReasons.length}',
              valueColor: status.warningReasons.isEmpty
                  ? Colors.greenAccent
                  : Colors.amberAccent,
            ),
          ],
        ),
        const SizedBox(height: 10),
        _Line(
          label: strings.nextSafeAction,
          value: strings.automationControlLabel(status.nextSafeAction),
          color: Colors.lightBlueAccent,
        ),
        const SizedBox(height: 8),
        _Line(
          label: strings.dryRunIsSeparate,
          value: status.dryRun ? strings.enabled : strings.disabled,
          color: status.dryRun ? Colors.orangeAccent : Colors.greenAccent,
        ),
        _Line(
          label: strings.killSwitchIsSeparate,
          value: status.killSwitch ? strings.enabled : strings.disabled,
          color: status.killSwitch ? Colors.orangeAccent : Colors.greenAccent,
        ),
        _Line(
          label: strings.kisRealOrdersAreSeparate,
          value:
              status.kisRealOrderEnabled ? strings.enabled : strings.disabled,
          color: status.kisRealOrderEnabled
              ? Colors.lightBlueAccent
              : Colors.orangeAccent,
        ),
        if (status.blockingReasons.isNotEmpty) ...[
          const SizedBox(height: 8),
          for (final reason in status.blockingReasons.take(4))
            Text(
              strings.automationControlLabel(reason),
              style: const TextStyle(color: Colors.white70),
            ),
        ],
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
    required this.value,
    required this.color,
  });

  final String label;
  final String value;
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
      child: Row(
        children: [
          Icon(Icons.shield_outlined, color: color, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  style: const TextStyle(
                    color: Colors.white70,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  value,
                  style: TextStyle(
                    color: color,
                    fontSize: 18,
                    fontWeight: FontWeight.w900,
                  ),
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
      width: 170,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(color: Colors.white60, fontSize: 12),
          ),
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
        ],
      ),
    );
  }
}

class _Line extends StatelessWidget {
  const _Line({
    required this.label,
    required this.value,
    required this.color,
  });

  final String label;
  final String value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 190,
            child: Text(
              label,
              style: const TextStyle(color: Colors.white60),
            ),
          ),
          Expanded(
            child: Text(
              value,
              style: TextStyle(color: color, fontWeight: FontWeight.w800),
            ),
          ),
        ],
      ),
    );
  }
}
