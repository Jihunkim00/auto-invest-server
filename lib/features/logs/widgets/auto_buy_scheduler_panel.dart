import 'package:flutter/material.dart';

import '../../../core/utils/timestamp_formatter.dart';
import '../../dashboard/dashboard_controller.dart';

class AutoBuySchedulerPanel extends StatelessWidget {
  const AutoBuySchedulerPanel({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final strings = controller.strings;
        final status = controller.strategyAutoBuySchedulerStatus;
        final loading = controller.strategyAutoBuySchedulerLoading;
        return Container(
          key: const ValueKey('auto-buy-scheduler-panel'),
          width: double.infinity,
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: Colors.black.withValues(alpha: 0.20),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(Icons.event_repeat_outlined,
                      color: Colors.lightGreenAccent, size: 20),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          strings.autoBuyScheduler,
                          style: const TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w900,
                          ),
                        ),
                        const SizedBox(height: 3),
                        Text(
                          status == null
                              ? strings.statusNotLoaded
                              : '${status.enabled ? strings.enabled : strings.disabled} / ${status.primaryBlockReason ?? strings.ready}',
                          style: const TextStyle(color: Colors.white70),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    key: const ValueKey('refresh-auto-buy-scheduler-button'),
                    tooltip: strings.refreshSchedulerStatus,
                    onPressed: loading
                        ? null
                        : () => _refresh(context, showSnack: true),
                    icon: const Icon(Icons.refresh),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              _BadgeWrap(badges: strings.schedulerSafetyBadges),
              if (controller.strategyAutoBuySchedulerError != null) ...[
                const SizedBox(height: 10),
                Text(
                  controller.strategyAutoBuySchedulerError!,
                  style: const TextStyle(color: Colors.orangeAccent),
                ),
              ],
              if (loading && status == null) ...[
                const SizedBox(height: 12),
                const LinearProgressIndicator(),
              ],
              if (status != null) ...[
                const SizedBox(height: 12),
                _InfoRow(
                  label: strings.dryRunOnly,
                  value: strings.booleanLabel(status.dryRunOnly),
                  valueColor:
                      status.dryRunOnly ? Colors.greenAccent : Colors.redAccent,
                ),
                _InfoRow(
                  label: strings.liveOrdersAllowed,
                  value: strings.booleanLabel(status.allowLiveOrders),
                  valueColor: status.allowLiveOrders
                      ? Colors.redAccent
                      : Colors.greenAccent,
                ),
                _InfoRow(
                  label: strings.realOrderSubmitAllowed,
                  value: strings.booleanLabel(status.realOrderSubmitAllowed),
                  valueColor: status.realOrderSubmitAllowed
                      ? Colors.redAccent
                      : Colors.greenAccent,
                ),
                _InfoRow(
                  label: strings.promotionQueueOnly,
                  value: strings.booleanLabel(status.promotionQueueOnly),
                  valueColor: status.promotionQueueOnly
                      ? Colors.greenAccent
                      : Colors.redAccent,
                ),
                _InfoRow(
                  label: strings.activeProfile,
                  value: status.activeProfile ?? '-',
                ),
                _InfoRow(
                  label: strings.runsToday,
                  value: '${status.runsToday}/${status.maxRunsPerDay}',
                ),
                _InfoRow(
                  label: strings.nextAllowedRun,
                  value: status.nextAllowedRunAt == null
                      ? '-'
                      : formatTimestampWithKst(
                          status.nextAllowedRunAt!.toIso8601String(),
                        ),
                ),
                _InfoRow(
                  label: strings.blockReason,
                  value: status.primaryBlockReason ?? '-',
                  valueColor: status.primaryBlockReason == null
                      ? Colors.greenAccent
                      : Colors.orangeAccent,
                ),
                _InfoRow(
                  label: strings.pendingPromotions,
                  value: '${status.pendingPromotionCount}',
                ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    OutlinedButton.icon(
                      key: const ValueKey('refresh-scheduler-status-action'),
                      onPressed: loading
                          ? null
                          : () => _refresh(context, showSnack: true),
                      icon: const Icon(Icons.refresh, size: 18),
                      label: Text(strings.refreshSchedulerStatus),
                    ),
                    if (!status.enabled)
                      FilledButton.icon(
                        key: const ValueKey('enable-dry-run-scheduler-button'),
                        onPressed: loading
                            ? null
                            : () => _setSchedulerEnabled(context, true),
                        icon: const Icon(Icons.play_circle_outline, size: 18),
                        label: Text(strings.enableDryRunScheduler),
                      )
                    else
                      OutlinedButton.icon(
                        key: const ValueKey('disable-scheduler-button'),
                        onPressed: loading
                            ? null
                            : () => _setSchedulerEnabled(context, false),
                        icon: const Icon(Icons.pause_circle_outline, size: 18),
                        label: Text(strings.disableScheduler),
                      ),
                    FilledButton.icon(
                      key: const ValueKey('run-scheduled-dry-run-once-button'),
                      onPressed: loading ? null : () => _runDryRunOnce(context),
                      icon: const Icon(Icons.science_outlined, size: 18),
                      label: Text(strings.runDryRunOnce),
                    ),
                  ],
                ),
              ],
            ],
          ),
        );
      },
    );
  }

  Future<void> _refresh(
    BuildContext context, {
    required bool showSnack,
  }) async {
    final result = await controller.refreshStrategyAutoBuyScheduler();
    if (!context.mounted || !showSnack) return;
    _snack(context, result.message);
  }

  Future<void> _runDryRunOnce(BuildContext context) async {
    final result = await controller.runStrategyAutoBuySchedulerDryRunOnce();
    if (!context.mounted) return;
    _snack(context, result.message);
  }

  Future<void> _setSchedulerEnabled(
    BuildContext context,
    bool enabled,
  ) async {
    final result = await controller.updateStrategyAutoBuySchedulerEnabled(
      enabled,
    );
    if (!context.mounted) return;
    _snack(context, result.message);
  }

  void _snack(BuildContext context, String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
    );
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({
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
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Text(
              label,
              style: const TextStyle(color: Colors.white60, fontSize: 12),
            ),
          ),
          const SizedBox(width: 10),
          Flexible(
            child: Text(
              value,
              textAlign: TextAlign.right,
              style: TextStyle(
                color: valueColor,
                fontWeight:
                    valueColor == null ? FontWeight.w500 : FontWeight.w900,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _BadgeWrap extends StatelessWidget {
  const _BadgeWrap({required this.badges});

  final List<String> badges;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 6,
      runSpacing: 6,
      children: [
        for (final badge in badges)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
            decoration: BoxDecoration(
              color: Colors.lightGreenAccent.withValues(alpha: 0.10),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(
                color: Colors.lightGreenAccent.withValues(alpha: 0.28),
              ),
            ),
            child: Text(
              badge,
              style: const TextStyle(
                color: Colors.lightGreenAccent,
                fontSize: 10,
                fontWeight: FontWeight.w900,
              ),
            ),
          ),
      ],
    );
  }
}
