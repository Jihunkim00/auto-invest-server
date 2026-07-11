import 'package:flutter/material.dart';

import '../../../core/i18n/app_strings.dart';
import '../../../core/utils/timestamp_formatter.dart';
import '../../../models/portfolio_orchestrator.dart';
import '../../dashboard/dashboard_controller.dart';

class PortfolioOrchestratorPanel extends StatefulWidget {
  const PortfolioOrchestratorPanel({
    super.key,
    required this.controller,
  });

  final DashboardController controller;

  @override
  State<PortfolioOrchestratorPanel> createState() =>
      _PortfolioOrchestratorPanelState();
}

class _PortfolioOrchestratorPanelState
    extends State<PortfolioOrchestratorPanel> {
  bool _detailsExpanded = false;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: widget.controller,
      builder: (context, _) {
        final controller = widget.controller;
        final strings = controller.strings;
        final result = controller.portfolioOrchestratorStatus ??
            controller.portfolioOrchestratorResult;
        final loading = controller.portfolioOrchestratorLoading;
        return Container(
          key: const ValueKey('portfolio-orchestrator-panel'),
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
                    Icons.account_tree_outlined,
                    color: Colors.lightBlueAccent,
                    size: 20,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          strings.portfolioOrchestrator,
                          style: const TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w900,
                          ),
                        ),
                        const SizedBox(height: 3),
                        Text(
                          strings.unifiedAutomationLoop,
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
              _BadgeWrap(labels: strings.portfolioOrchestratorBadges),
              const SizedBox(height: 10),
              _FlowRow(strings: strings),
              if (controller.portfolioOrchestratorError != null) ...[
                const SizedBox(height: 10),
                Text(
                  controller.portfolioOrchestratorError!,
                  style: const TextStyle(color: Colors.orangeAccent),
                ),
              ],
              const SizedBox(height: 12),
              if (result == null)
                _EmptyState(strings: strings)
              else
                _ResultSummary(result: result, strings: strings),
              if (_detailsExpanded) ...[
                const SizedBox(height: 10),
                _Details(result: result, strings: strings),
              ],
              const SizedBox(height: 12),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  OutlinedButton.icon(
                    key: const ValueKey(
                      'refresh-portfolio-orchestrator-status',
                    ),
                    onPressed: loading ? null : () => _refresh(context),
                    icon: const Icon(Icons.refresh, size: 18),
                    label: Text(strings.refreshPortfolioOrchestratorStatus),
                  ),
                  FilledButton.icon(
                    key: const ValueKey('run-portfolio-orchestrator-once'),
                    onPressed: loading ? null : () => _runOnce(context),
                    icon: const Icon(Icons.play_arrow_outlined, size: 18),
                    label: Text(strings.runPortfolioOrchestratorOnce),
                  ),
                  TextButton.icon(
                    key: const ValueKey(
                      'toggle-portfolio-orchestrator-details',
                    ),
                    onPressed: () {
                      setState(() => _detailsExpanded = !_detailsExpanded);
                    },
                    icon: Icon(
                      _detailsExpanded ? Icons.expand_less : Icons.expand_more,
                    ),
                    label: Text(
                      _detailsExpanded
                          ? strings.collapseOrchestratorDetails
                          : strings.expandOrchestratorDetails,
                    ),
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
    final action = await widget.controller.refreshPortfolioOrchestrator();
    if (!context.mounted) return;
    _snack(context, action.message);
  }

  Future<void> _runOnce(BuildContext context) async {
    final action = await widget.controller.runPortfolioOrchestratorOnce();
    if (!context.mounted) return;
    _snack(context, action.message);
  }

  void _snack(BuildContext context, String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
    );
  }
}

class _FlowRow extends StatelessWidget {
  const _FlowRow({required this.strings});

  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 6,
      runSpacing: 6,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        _StageChip(index: 1, label: strings.checkPositionsFirst),
        const Icon(Icons.arrow_forward, size: 14, color: Colors.white38),
        _StageChip(index: 2, label: strings.autoSellFirst),
        const Icon(Icons.arrow_forward, size: 14, color: Colors.white38),
        _StageChip(index: 3, label: strings.autoBuySecond),
      ],
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState({required this.strings});

  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _StatusBanner(
          icon: Icons.lock_outline,
          label: strings.disabledByDefault,
          detail: strings.noBrokerSubmitTitle,
          color: Colors.white54,
        ),
        const SizedBox(height: 10),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            _Metric(label: strings.dailyActionLimit, value: '0 / 1'),
            _Metric(
              label: strings.actionTaken,
              value: strings.noActionTaken,
            ),
          ],
        ),
        const SizedBox(height: 8),
        _DetailLine(
          label: strings.blockedWhenSyncRequired,
          value: strings.yes,
        ),
        _DetailLine(
          label: strings.nextSafeAction,
          value: strings.refreshPortfolioOrchestratorStatus,
          valueColor: Colors.lightBlueAccent,
        ),
      ],
    );
  }
}

class _ResultSummary extends StatelessWidget {
  const _ResultSummary({required this.result, required this.strings});

  final PortfolioOrchestratorResult result;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    final submitted = result.sellSubmitted || result.buySubmitted;
    final actionLabel = result.sellSubmitted
        ? strings.sellSubmitted
        : result.buySubmitted
            ? strings.buySubmitted
            : strings.noActionTaken;
    final color = submitted
        ? Colors.greenAccent
        : result.blocked || result.disabled
            ? Colors.orangeAccent
            : Colors.lightBlueAccent;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _StatusBanner(
          icon: submitted
              ? Icons.task_alt
              : result.blocked || result.disabled
                  ? Icons.block_outlined
                  : Icons.fact_check_outlined,
          label: strings.runResult,
          detail: strings.statusLabel(result.resultStatus),
          color: color,
        ),
        const SizedBox(height: 10),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            _Metric(label: strings.actionTaken, value: actionLabel),
            _Metric(
              label: strings.dailyActionLimit,
              value:
                  '${result.dailyTradeLimitUsed} / ${result.dailyTradeLimitUsed + result.dailyTradeLimitRemaining}',
            ),
          ],
        ),
        const SizedBox(height: 8),
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: [
            _SmallBadge(
              label: result.realOrderSubmitted
                  ? strings.liveOrderSubmitted
                  : result.brokerSubmitCalled
                      ? strings.brokerSubmitCalledTitle
                      : strings.noBrokerSubmitTitle,
              color: result.realOrderSubmitted
                  ? Colors.greenAccent
                  : result.brokerSubmitCalled
                      ? Colors.orangeAccent
                      : Colors.white70,
            ),
            _SmallBadge(
              label: strings.blockedWhenSyncRequired,
              color: Colors.lightBlueAccent,
            ),
          ],
        ),
        const SizedBox(height: 8),
        if (result.primaryBlockReason != null)
          _DetailLine(
            label: strings.primaryBlockReason,
            value: strings.statusLabel(result.primaryBlockReason!),
            valueColor: Colors.orangeAccent,
          ),
        if (result.skippedBuyReason != null)
          _DetailLine(
            label: strings.skippedBuyReason,
            value: strings.statusLabel(result.skippedBuyReason!),
          ),
        _DetailLine(
          label: strings.nextSafeAction,
          value: strings.statusLabel(result.nextSafeAction),
          valueColor: Colors.lightBlueAccent,
        ),
      ],
    );
  }
}

class _Details extends StatelessWidget {
  const _Details({required this.result, required this.strings});

  final PortfolioOrchestratorResult? result;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    if (result == null) {
      return _DetailBox(
        children: [
          _DetailLine(
            label: strings.status,
            value: strings.statusNotLoaded,
          ),
        ],
      );
    }
    final value = result!;
    return _DetailBox(
      children: [
        _DetailLine(
          label: strings.latestPositionManagementResult,
          value: _stepStatus(value.positionManagementResult, strings),
        ),
        _DetailLine(
          label: strings.orchestratorAutoSellResult,
          value: _stepStatus(value.autoSellPhase1Result, strings),
        ),
        _DetailLine(
          label: strings.orchestratorAutoBuyResult,
          value: _stepStatus(value.autoBuyPhase1Result, strings),
        ),
        if (value.skippedSellReason != null)
          _DetailLine(
            label: strings.skippedSellReason,
            value: strings.statusLabel(value.skippedSellReason!),
          ),
        _DetailLine(
          label: strings.productionReadiness,
          value: value.productionReadinessStatus == null
              ? '-'
              : strings.statusLabel(value.productionReadinessStatus!),
        ),
        _DetailLine(
          label: strings.orderPositionSyncHealth,
          value: strings.brokerSyncHealthLabel(value.brokerSyncHealth),
          valueColor: _brokerSyncColor(value.brokerSyncHealth),
        ),
        _DetailLine(
          label: strings.issueDetails,
          value: value.brokerSyncIssueCount.toString(),
          valueColor: value.brokerSyncIssueCount > 0
              ? Colors.orangeAccent
              : Colors.greenAccent,
        ),
        if (value.brokerSyncBlockingReasons.isNotEmpty)
          _DetailLine(
            label: strings.primaryBlockingReasons,
            value: value.brokerSyncBlockingReasons
                .map(strings.automationControlLabel)
                .join(' | '),
            valueColor: Colors.orangeAccent,
          ),
        _DetailLine(
          label: strings.pendingOrderConflicts,
          value: value.pendingOrderConflictCount.toString(),
        ),
        _DetailLine(
          label: strings.syncRequiredCount,
          value: value.syncRequiredCount.toString(),
        ),
        _DetailLine(
          label: strings.criticalExitCandidateCount,
          value: value.criticalExitCandidateCount.toString(),
        ),
        _DetailLine(
          label: strings.positionsFirst,
          value: strings.booleanLabel(value.positionsFirst),
        ),
        _DetailLine(
          label: strings.generatedAt,
          value: formatTimestampWithKst(value.generatedAt.toIso8601String()),
        ),
        if (value.riskFlags.isNotEmpty)
          _DetailLine(
            label: strings.riskFlags,
            value: value.riskFlags.join(', '),
          ),
        if (value.gatingNotes.isNotEmpty)
          _DetailLine(
            label: strings.gatingNotes,
            value: value.gatingNotes.join(' | '),
          ),
        if (value.checklist.isNotEmpty)
          _DetailLine(
            label: strings.checklist,
            value: value.checklist
                .map(
                  (item) =>
                      '${strings.statusLabel(item.key)}: ${strings.statusLabel(item.status)}',
                )
                .join(' | '),
          ),
      ],
    );
  }
}

class _DetailBox extends StatelessWidget {
  const _DetailBox({required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Container(
      key: const ValueKey('portfolio-orchestrator-details'),
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
  const _Metric({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return ConstrainedBox(
      constraints: const BoxConstraints(minWidth: 145, maxWidth: 250),
      child: Container(
        padding: const EdgeInsets.all(9),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.055),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              label,
              style: const TextStyle(fontSize: 11, color: Colors.white70),
            ),
            const SizedBox(height: 3),
            Text(
              value,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontWeight: FontWeight.w900),
            ),
          ],
        ),
      ),
    );
  }
}

class _StageChip extends StatelessWidget {
  const _StageChip({required this.index, required this.label});

  final int index;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
      decoration: BoxDecoration(
        color: Colors.lightBlueAccent.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: Colors.lightBlueAccent.withValues(alpha: 0.30),
        ),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            '$index.',
            style: const TextStyle(
              color: Colors.lightBlueAccent,
              fontSize: 11,
              fontWeight: FontWeight.w900,
            ),
          ),
          const SizedBox(width: 4),
          Text(
            label,
            style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w800),
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
      children: [for (final label in labels) _SmallBadge(label: label)],
    );
  }
}

class _SmallBadge extends StatelessWidget {
  const _SmallBadge({required this.label, this.color = Colors.white70});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.28)),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: color,
          fontSize: 11,
          fontWeight: FontWeight.w800,
        ),
      ),
    );
  }
}

class _DetailLine extends StatelessWidget {
  const _DetailLine({
    required this.label,
    required this.value,
    this.valueColor = Colors.white70,
  });

  final String label;
  final String value;
  final Color valueColor;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 5),
      child: Wrap(
        spacing: 5,
        runSpacing: 2,
        children: [
          Text(label, style: const TextStyle(fontWeight: FontWeight.w800)),
          const Text('—', style: TextStyle(color: Colors.white38)),
          Text(value, style: TextStyle(color: valueColor)),
        ],
      ),
    );
  }
}

String _stepStatus(
  PortfolioOrchestratorStepResult? result,
  AppStrings strings,
) {
  if (result == null) return '-';
  final status = result.resultStatus ?? result.reason;
  return status == null ? '-' : strings.statusLabel(status);
}

Color _brokerSyncColor(String health) {
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
