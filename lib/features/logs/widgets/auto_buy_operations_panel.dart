import 'package:flutter/material.dart';

import '../../../core/utils/timestamp_formatter.dart';
import '../../dashboard/dashboard_controller.dart';
import '../../../models/strategy_auto_buy_operations.dart';

class AutoBuyOperationsPanel extends StatelessWidget {
  const AutoBuyOperationsPanel({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final status = controller.strategyAutoBuyOperationsStatus;
        final loading = controller.strategyAutoBuyOperationsLoading ||
            controller.strategyDryRunAutoBuyLoading ||
            controller.strategyLiveAutoBuyLoading;
        return Container(
          key: const ValueKey('auto-buy-operations-panel'),
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: Colors.black.withValues(alpha: 0.22),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(Icons.tune_outlined,
                      color: Colors.lightBlueAccent, size: 20),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'Auto Buy Operations',
                          style: TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w900,
                          ),
                        ),
                        const SizedBox(height: 3),
                        Text(
                          status == null
                              ? 'Status not loaded'
                              : '${_label(status.autoBuyStage)} / ${_label(status.nextOperatorAction)}',
                          style: const TextStyle(color: Colors.white70),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    key: const ValueKey('refresh-auto-buy-status-button'),
                    tooltip: 'Refresh Auto Buy Status',
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
                  'AUTO BUY OPS',
                  'DRY RUN EVIDENCE REQUIRED',
                  'TARGET RISK GATED',
                  'KIS VALIDATION REQUIRED',
                  'ONE SHOT LIVE BUY',
                  'SCHEDULED DRY RUN',
                  'PROMOTION ONLY',
                  'NO LIVE SCHEDULER',
                  'NO AUTO RETRY',
                ],
              ),
              if (controller.strategyAutoBuyOperationsError != null) ...[
                const SizedBox(height: 10),
                Text(
                  controller.strategyAutoBuyOperationsError!,
                  style: const TextStyle(color: Colors.orangeAccent),
                ),
              ],
              if (loading && status == null) ...[
                const SizedBox(height: 12),
                const LinearProgressIndicator(),
              ],
              if (status != null) ...[
                const SizedBox(height: 12),
                _StatusGrid(status: status),
                const SizedBox(height: 12),
                _ActionRow(
                  loading: loading,
                  status: status,
                  onRefresh: () => _refresh(context, showSnack: true),
                  onDryRun: () => _runDryRun(context),
                  onLiveRun: () => _confirmLiveRun(context, status),
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
    final result = await controller.refreshStrategyAutoBuyOperations();
    if (!context.mounted || !showSnack) return;
    _snack(context, result.message);
  }

  Future<void> _runDryRun(BuildContext context) async {
    final result = await controller.runStrategyDryRunAutoBuy();
    await controller.refreshStrategyAutoBuyOperations(silent: true);
    if (!context.mounted) return;
    _snack(context, result.message);
  }

  Future<void> _confirmLiveRun(
    BuildContext context,
    StrategyAutoBuyOperationsStatus status,
  ) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        key: const ValueKey('auto-buy-live-confirm-dialog'),
        title: const Text('Confirm Guarded Live Auto Buy'),
        content: Text(
          'Profile ${status.activeProfile ?? '-'} is ready for a one-shot guarded live buy.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton.icon(
            onPressed: () => Navigator.of(context).pop(true),
            icon: const Icon(Icons.check_circle_outline),
            label: const Text('Run Guarded Live Auto Buy Once'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    final readiness = await controller.refreshStrategyLiveAutoBuy(silent: true);
    final result = readiness.success
        ? await controller.runStrategyLiveAutoBuyOnce()
        : readiness;
    await controller.refreshStrategyAutoBuyOperations(silent: true);
    if (!context.mounted) return;
    _snack(context, result.message);
  }

  void _snack(BuildContext context, String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
    );
  }
}

class _StatusGrid extends StatelessWidget {
  const _StatusGrid({required this.status});

  final StrategyAutoBuyOperationsStatus status;

  @override
  Widget build(BuildContext context) {
    final latestTime = status.dryRun.latestTime;
    return Column(
      children: [
        _InfoRow(
          label: 'Stage',
          value: _label(status.autoBuyStage),
          valueColor: _stageColor(status.autoBuyStage),
        ),
        _InfoRow(
          label: 'Latest dry-run',
          value:
              '${status.dryRun.latestAction ?? 'none'} / ${status.dryRun.latestSymbol ?? '-'}',
        ),
        _InfoRow(
          label: 'Dry-run score',
          value: status.dryRun.latestScore?.toStringAsFixed(1) ?? '-',
        ),
        _InfoRow(
          label: 'Dry-run time',
          value: latestTime == null
              ? '-'
              : formatTimestampWithKst(latestTime.toIso8601String()),
        ),
        _InfoRow(
          label: 'Readiness',
          value: status.liveReadiness.ready
              ? 'READY'
              : status.liveReadiness.primaryBlockReason ?? 'BLOCKED',
          valueColor: status.liveReadiness.ready
              ? Colors.greenAccent
              : Colors.orangeAccent,
        ),
        _InfoRow(
          label: 'Orders remaining',
          value: '${status.liveReadiness.ordersRemainingToday}',
        ),
        _InfoRow(
          label: 'Latest live attempt',
          value: status.liveAttempts.latestStatus ?? 'none',
        ),
        _InfoRow(
          label: 'Scheduler',
          value:
              '${status.scheduler.enabled ? 'ENABLED' : 'DISABLED'} / ${status.scheduler.runsToday}/${status.scheduler.maxRunsPerDay}',
        ),
        _InfoRow(
          label: 'Promotions',
          value:
              '${status.promotions.pendingCount} pending / ${status.promotions.latestStatus ?? 'none'}',
        ),
        _InfoRow(
          label: 'Next action',
          value: _label(status.nextOperatorAction),
          valueColor: Colors.lightBlueAccent,
        ),
      ],
    );
  }
}

class _ActionRow extends StatelessWidget {
  const _ActionRow({
    required this.loading,
    required this.status,
    required this.onRefresh,
    required this.onDryRun,
    required this.onLiveRun,
  });

  final bool loading;
  final StrategyAutoBuyOperationsStatus status;
  final VoidCallback onRefresh;
  final VoidCallback onDryRun;
  final VoidCallback onLiveRun;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        OutlinedButton.icon(
          key: const ValueKey('auto-buy-status-refresh-action'),
          onPressed: loading ? null : onRefresh,
          icon: const Icon(Icons.refresh, size: 18),
          label: const Text('Refresh Auto Buy Status'),
        ),
        OutlinedButton.icon(
          key: const ValueKey('run-dry-run-auto-buy-once-button'),
          onPressed: loading ? null : onDryRun,
          icon: const Icon(Icons.science_outlined, size: 18),
          label: const Text('Run Dry-Run Auto Buy Once'),
        ),
        FilledButton.icon(
          key: const ValueKey('run-guarded-live-auto-buy-once-button'),
          onPressed: loading || !status.liveReadiness.ready ? null : onLiveRun,
          icon: const Icon(Icons.verified_user_outlined, size: 18),
          label: const Text('Run Guarded Live Auto Buy Once'),
        ),
      ],
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
              color: Colors.lightBlueAccent.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(999),
              border: Border.all(
                color: Colors.lightBlueAccent.withValues(alpha: 0.28),
              ),
            ),
            child: Text(
              badge,
              style: const TextStyle(
                color: Colors.lightBlueAccent,
                fontSize: 10,
                fontWeight: FontWeight.w900,
              ),
            ),
          ),
      ],
    );
  }
}

String _label(String value) {
  return value.replaceAll('_', ' ').toUpperCase();
}

Color _stageColor(String stage) {
  if (stage == 'ready_for_operator_confirm') {
    return Colors.greenAccent;
  }
  if (stage == 'submitted_today') {
    return Colors.lightBlueAccent;
  }
  if (stage == 'sync_required') {
    return Colors.deepOrangeAccent;
  }
  return Colors.orangeAccent;
}
