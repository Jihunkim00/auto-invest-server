import 'package:flutter/material.dart';

import '../../../core/widgets/confirm_action_dialog.dart';
import '../../../core/widgets/section_card.dart';
import '../../dashboard/dashboard_controller.dart';

class OperationRehearsalPanel extends StatelessWidget {
  const OperationRehearsalPanel({
    super.key,
    required this.controller,
  });

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return SectionCard(
      key: const Key('operation_rehearsal_panel'),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.fact_check_outlined, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              'Operation Rehearsal',
              style: Theme.of(context).textTheme.titleMedium,
            ),
          ),
          const _ReadOnlyBadge(text: 'SAFE CHECKS'),
        ]),
        const SizedBox(height: 8),
        const Text(
          'Use existing checks and dry-run paths to verify automation setup.',
          style: TextStyle(color: Colors.white70),
        ),
        const SizedBox(height: 12),
        Wrap(spacing: 8, runSpacing: 8, children: [
          OutlinedButton.icon(
            key: const ValueKey('operation-refresh-monitor'),
            onPressed: controller.automationRuntimeMonitorLoading ||
                    controller.portfolioManagementLoading
                ? null
                : () async {
                    await _showResult(
                      context,
                      controller.refreshAllOperationsOverview(),
                    );
                  },
            icon: const Icon(Icons.refresh, size: 18),
            label: const Text('Refresh Monitor'),
          ),
          OutlinedButton.icon(
            key: const ValueKey('operation-check-kis-sell'),
            onPressed: controller.kisSchedulerGuardedSellLoading
                ? null
                : () async {
                    await _showResult(
                      context,
                      controller.refreshKisSchedulerGuardedSellStatus(),
                    );
                  },
            icon: const Icon(Icons.rule_outlined, size: 18),
            label: const Text('Check KIS Sell Gates'),
          ),
          OutlinedButton.icon(
            key: const ValueKey('operation-check-kis-buy'),
            onPressed: controller.kisSchedulerGuardedBuyLoading
                ? null
                : () async {
                    await _showResult(
                      context,
                      controller.refreshKisSchedulerGuardedBuyStatus(),
                    );
                  },
            icon: const Icon(Icons.rule_folder_outlined, size: 18),
            label: const Text('Check KIS Buy Gates'),
          ),
          OutlinedButton.icon(
            key: const ValueKey('operation-run-kis-dry-run'),
            onPressed: controller.kisSchedulerDryRunOrchestrationLoading
                ? null
                : () async {
                    await _showResult(
                      context,
                      controller.runKisSchedulerDryRunOrchestrationOnce(),
                    );
                  },
            icon: const Icon(Icons.science_outlined, size: 18),
            label: const Text('Run KIS Scheduler Dry-run Orchestration'),
          ),
          OutlinedButton.icon(
            key: const ValueKey('operation-run-alpaca-check'),
            onPressed: controller.runOnceLoading
                ? null
                : () async {
                    await _showResult(
                      context,
                      controller.runAlpacaWatchlistCheck(),
                    );
                  },
            icon: const Icon(Icons.query_stats_outlined, size: 18),
            label: const Text('Run Alpaca Watchlist Check'),
          ),
        ]),
        const SizedBox(height: 8),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _ReadOnlyBadge(text: 'DRY-RUN ONLY'),
          _ReadOnlyBadge(text: 'ALPACA PAPER'),
          _ReadOnlyBadge(text: 'NO NEW SUBMIT PATH'),
        ]),
        const SizedBox(height: 6),
        _AdvancedActions(controller: controller),
      ]),
    );
  }
}

class _AdvancedActions extends StatelessWidget {
  const _AdvancedActions({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return ExpansionTile(
      key: const ValueKey('operation-advanced-actions'),
      tilePadding: EdgeInsets.zero,
      childrenPadding: EdgeInsets.zero,
      title: const Text(
        'Advanced Actions',
        style: TextStyle(fontWeight: FontWeight.w800),
      ),
      subtitle: const Text(
        'Collapsed by default. These use existing guarded endpoints.',
        style: TextStyle(color: Colors.white60),
      ),
      children: [
        const SizedBox(height: 4),
        const Text(
          'These actions may submit real KIS orders if all backend gates pass.',
          style: TextStyle(
            color: Colors.redAccent,
            fontWeight: FontWeight.w800,
          ),
        ),
        const SizedBox(height: 10),
        Wrap(spacing: 8, runSpacing: 8, children: [
          OutlinedButton.icon(
            key: const ValueKey('operation-run-guarded-sell'),
            onPressed: controller.kisSchedulerGuardedSellLoading
                ? null
                : () async {
                    final confirmed = await showConfirmActionDialog(
                      context,
                      title: 'Run KIS Guarded Sell Once?',
                      description:
                          'This may submit a real KIS SELL order if all gates pass.',
                    );
                    if (!confirmed) return;
                    if (!context.mounted) return;
                    await _showResult(
                      context,
                      controller.runKisSchedulerGuardedSellOnce(),
                    );
                  },
            icon: const Icon(Icons.warning_amber_outlined, size: 18),
            label: const Text('Run KIS Guarded Sell Once'),
          ),
          OutlinedButton.icon(
            key: const ValueKey('operation-run-guarded-buy'),
            onPressed: controller.kisSchedulerGuardedBuyLoading
                ? null
                : () async {
                    final confirmed = await showConfirmActionDialog(
                      context,
                      title: 'Run KIS Guarded Buy Once?',
                      description:
                          'This may submit a real KIS BUY order if all gates pass.',
                    );
                    if (!confirmed) return;
                    if (!context.mounted) return;
                    await _showResult(
                      context,
                      controller.runKisSchedulerGuardedBuyOnce(),
                    );
                  },
            icon: const Icon(Icons.dangerous_outlined, size: 18),
            label: const Text('Run KIS Guarded Buy Once'),
          ),
        ]),
      ],
    );
  }
}

class _ReadOnlyBadge extends StatelessWidget {
  const _ReadOnlyBadge({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.18)),
      ),
      child: Text(
        text,
        style: const TextStyle(
          color: Colors.white70,
          fontSize: 10,
          fontWeight: FontWeight.w800,
        ),
      ),
    );
  }
}

Future<void> _showResult(
  BuildContext context,
  Future<ActionResult> future,
) async {
  final result = await future;
  if (!context.mounted) return;
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
    content: Text(result.message),
    backgroundColor: result.success ? Colors.green : Colors.orange,
  ));
}
