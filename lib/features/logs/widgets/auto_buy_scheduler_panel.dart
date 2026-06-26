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
                        const Text(
                          'Auto Buy Scheduler',
                          style: TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w900,
                          ),
                        ),
                        const SizedBox(height: 3),
                        Text(
                          status == null
                              ? 'Status not loaded'
                              : '${status.enabled ? 'ENABLED' : 'DISABLED'} / ${status.primaryBlockReason ?? 'ready'}',
                          style: const TextStyle(color: Colors.white70),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    key: const ValueKey('refresh-auto-buy-scheduler-button'),
                    tooltip: 'Refresh Scheduler Status',
                    onPressed: loading
                        ? null
                        : () => _refresh(context, showSnack: true),
                    icon: const Icon(Icons.refresh),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              const _BadgeWrap(
                badges: [
                  'SCHEDULED DRY RUN',
                  'PROMOTION ONLY',
                  'NO LIVE SCHEDULER',
                  'NO VALIDATION IN SCHEDULER',
                  'NO BROKER SUBMIT IN SCHEDULER',
                  'OPERATOR CONFIRM REQUIRED',
                ],
              ),
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
                  label: 'Dry-run only',
                  value: status.dryRunOnly ? 'YES' : 'NO',
                  valueColor:
                      status.dryRunOnly ? Colors.greenAccent : Colors.redAccent,
                ),
                _InfoRow(
                  label: 'Live orders allowed',
                  value: status.allowLiveOrders ? 'YES' : 'NO',
                  valueColor: status.allowLiveOrders
                      ? Colors.redAccent
                      : Colors.greenAccent,
                ),
                _InfoRow(
                  label: 'Active profile',
                  value: status.activeProfile ?? '-',
                ),
                _InfoRow(
                  label: 'Runs today',
                  value: '${status.runsToday}/${status.maxRunsPerDay}',
                ),
                _InfoRow(
                  label: 'Next allowed run',
                  value: status.nextAllowedRunAt == null
                      ? '-'
                      : formatTimestampWithKst(
                          status.nextAllowedRunAt!.toIso8601String(),
                        ),
                ),
                _InfoRow(
                  label: 'Block reason',
                  value: status.primaryBlockReason ?? '-',
                  valueColor: status.primaryBlockReason == null
                      ? Colors.greenAccent
                      : Colors.orangeAccent,
                ),
                _InfoRow(
                  label: 'Pending promotions',
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
                      label: const Text('Refresh Scheduler Status'),
                    ),
                    FilledButton.icon(
                      key: const ValueKey('run-scheduled-dry-run-once-button'),
                      onPressed: loading ? null : () => _runDryRunOnce(context),
                      icon: const Icon(Icons.science_outlined, size: 18),
                      label: const Text('Run Scheduled Dry-Run Once'),
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
