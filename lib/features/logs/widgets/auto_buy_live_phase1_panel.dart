import 'package:flutter/material.dart';

import '../../../core/i18n/app_strings.dart';
import '../../../core/utils/timestamp_formatter.dart';
import '../../../models/auto_buy_live_phase1.dart';
import '../../dashboard/dashboard_controller.dart';

class AutoBuyLivePhase1Panel extends StatelessWidget {
  const AutoBuyLivePhase1Panel({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final strings = controller.strings;
        final result = controller.autoBuyLivePhase1Status ??
            controller.autoBuyLivePhase1Result;
        final loading = controller.autoBuyLivePhase1Loading;
        return Container(
          key: const ValueKey('auto-buy-live-phase1-panel'),
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
                    Icons.lock_open_outlined,
                    color: Colors.amberAccent,
                    size: 20,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          strings.autoBuyPhase1,
                          style: const TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w900,
                          ),
                        ),
                        const SizedBox(height: 3),
                        Text(
                          result == null
                              ? '${strings.limitedLiveAutoBuy} / ${strings.disabledByDefault}'
                              : '${strings.statusLabel(result.resultStatus)} / ${result.selectedSymbol ?? result.primaryBlockReason ?? strings.limitedLiveAutoBuy}',
                          style: const TextStyle(color: Colors.white70),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    key: const ValueKey('refresh-auto-buy-phase1-status'),
                    tooltip: strings.refreshAutoBuyPhase1Status,
                    onPressed: loading
                        ? null
                        : () => _refresh(context, showSnack: true),
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
              _BadgeWrap(badges: strings.autoBuyPhase1Badges),
              if (controller.autoBuyLivePhase1Error != null) ...[
                const SizedBox(height: 10),
                Text(
                  controller.autoBuyLivePhase1Error!,
                  style: const TextStyle(color: Colors.orangeAccent),
                ),
              ],
              if (loading && result == null) ...[
                const SizedBox(height: 12),
                const LinearProgressIndicator(),
              ],
              const SizedBox(height: 12),
              if (result == null)
                _EmptyState(strings: strings)
              else
                _Phase1ResultBlock(result: result, strings: strings),
              const SizedBox(height: 12),
              _ActionRow(
                loading: loading,
                strings: strings,
                onRefresh: () => _refresh(context, showSnack: true),
                onRunOnce: () => _runOnce(context),
              ),
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
    final result = await controller.refreshAutoBuyLivePhase1();
    if (!context.mounted || !showSnack) return;
    _snack(context, result.message);
  }

  Future<void> _runOnce(BuildContext context) async {
    final result = await controller.runAutoBuyLivePhase1Once();
    if (!context.mounted) return;
    _snack(context, result.message);
  }

  void _snack(BuildContext context, String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
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
          detail: strings.noAutoBuyYet,
          color: Colors.white54,
        ),
        const SizedBox(height: 10),
        _DetailRow(
          label: strings.liveOrderConditions,
          value: strings.liveOrderConditionsSummary,
          valueMaxLines: 5,
        ),
        _DetailRow(
          label: strings.noBrokerSubmitTitle,
          value: strings.noBrokerSubmitTitle,
          valueColor: Colors.greenAccent,
        ),
        _DetailRow(
          label: strings.noAutoRetryTitle,
          value: strings.noAutoRetryTitle,
          valueColor: Colors.greenAccent,
        ),
      ],
    );
  }
}

class _Phase1ResultBlock extends StatelessWidget {
  const _Phase1ResultBlock({required this.result, required this.strings});

  final AutoBuyLivePhase1Result result;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    final color = _statusColor(result);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _StatusBanner(
          icon: result.submitted ? Icons.task_alt : Icons.block_outlined,
          label: result.submitted
              ? strings.autoBuySubmitted
              : result.blocked
                  ? strings.autoBuyBlocked
                  : strings.autoBuyResult,
          detail: strings.statusLabel(result.resultStatus),
          color: color,
        ),
        const SizedBox(height: 10),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            _Metric(
              label: strings.selectedSymbol,
              value: result.selectedSymbol ?? '-',
            ),
            _Metric(
              label: strings.selectedPromotion,
              value: result.selectedPromotionId?.toString() ?? '-',
            ),
            _Metric(
              label: strings.dailyLimit,
              value: '${result.dailyAutoBuyCount}/${result.dailyAutoBuyLimit}',
            ),
            _Metric(
              label: strings.maxAllowedNotional,
              value: _money(result.maxAllowedNotional),
            ),
          ],
        ),
        const SizedBox(height: 10),
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: [
            _SmallBadge(
              text: result.realOrderSubmitted
                  ? strings.liveOrderSubmittedTitle
                  : strings.noLiveOrderSubmitted,
              color: result.realOrderSubmitted
                  ? Colors.greenAccent
                  : Colors.white70,
            ),
            _SmallBadge(
              text: result.brokerSubmitCalled
                  ? strings.liveOrderSubmittedTitle
                  : strings.noBrokerSubmitTitle,
              color: result.brokerSubmitCalled
                  ? Colors.greenAccent
                  : Colors.white70,
            ),
            _SmallBadge(text: strings.noAutoRetryTitle),
          ],
        ),
        const SizedBox(height: 10),
        _DetailRow(
          label: strings.liveOrderConditions,
          value: strings.liveOrderConditionsSummary,
          valueMaxLines: 5,
        ),
        _DetailRow(
          label: strings.readiness,
          value: result.productionReadinessStatus == null
              ? '-'
              : strings.statusLabel(result.productionReadinessStatus!),
        ),
        _DetailRow(
          label: strings.preflightResult,
          value: result.preflightStatus == null
              ? '-'
              : strings.statusLabel(result.preflightStatus!),
        ),
        _DetailRow(
          label: strings.score,
          value: _number(result.candidateScore),
        ),
        _DetailRow(
          label: strings.usedRemaining,
          value: '${result.dailyAutoBuyCount} / ${result.dailyRemaining}',
        ),
        if (result.submittedQuantity != null)
          _DetailRow(
            label: strings.submittedQuantity,
            value: _number(result.submittedQuantity),
          ),
        if (result.submittedNotional != null)
          _DetailRow(
            label: strings.estimatedNotional,
            value: _money(result.submittedNotional),
          ),
        if (result.orderId != null)
          _DetailRow(
            label: strings.relatedOrderLog,
            value: result.orderId.toString(),
          ),
        if (result.brokerOrderId != null)
          _DetailRow(
            label: strings.brokerOrderId,
            value: result.brokerOrderId!,
          ),
        if (result.kisOdno != null)
          _DetailRow(
            label: strings.kisOrderNo,
            value: result.kisOdno!,
          ),
        if (result.primaryBlockReason != null)
          _DetailRow(
            label: strings.primaryBlockReason,
            value: result.primaryBlockReason!,
            valueColor: Colors.orangeAccent,
          ),
        _DetailRow(
          label: strings.nextSafeAction,
          value: strings.statusLabel(result.nextSafeAction),
          valueColor: Colors.lightBlueAccent,
        ),
        if (result.riskFlags.isNotEmpty)
          _DetailRow(
            label: strings.riskFlags,
            value: result.riskFlags.join(', '),
            valueMaxLines: 3,
          ),
        if (result.gatingNotes.isNotEmpty)
          _DetailRow(
            label: strings.gatingNotes,
            value: result.gatingNotes.join(' | '),
            valueMaxLines: 4,
          ),
        if (result.latestRun != null) ...[
          const SizedBox(height: 8),
          _LatestRunBlock(latestRun: result.latestRun!, strings: strings),
        ],
        if (result.checklist.isNotEmpty) ...[
          const SizedBox(height: 8),
          _ChecklistBlock(items: result.checklist, strings: strings),
        ],
      ],
    );
  }
}

class _ActionRow extends StatelessWidget {
  const _ActionRow({
    required this.loading,
    required this.strings,
    required this.onRefresh,
    required this.onRunOnce,
  });

  final bool loading;
  final AppStrings strings;
  final VoidCallback onRefresh;
  final VoidCallback onRunOnce;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        OutlinedButton.icon(
          key: const ValueKey('refresh-auto-buy-phase1-status-action'),
          onPressed: loading ? null : onRefresh,
          icon: const Icon(Icons.refresh, size: 18),
          label: Text(strings.refreshAutoBuyPhase1Status),
        ),
        OutlinedButton.icon(
          key: const ValueKey('run-auto-buy-phase1-once'),
          onPressed: loading ? null : onRunOnce,
          icon: const Icon(Icons.play_arrow_outlined, size: 18),
          label: Text(strings.runPhase1AttemptOnce),
        ),
      ],
    );
  }
}

class _LatestRunBlock extends StatelessWidget {
  const _LatestRunBlock({required this.latestRun, required this.strings});

  final AutoBuyLivePhase1LatestRun latestRun;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Divider(color: Colors.white.withValues(alpha: 0.14)),
        Text(
          strings.latestRun,
          style: const TextStyle(fontWeight: FontWeight.w900),
        ),
        const SizedBox(height: 6),
        _DetailRow(
          label: strings.latestRun,
          value: latestRun.generatedAt == null
              ? '-'
              : formatTimestampWithKst(
                  latestRun.generatedAt!.toIso8601String()),
        ),
        _DetailRow(
          label: strings.status,
          value: latestRun.resultStatus == null
              ? '-'
              : strings.statusLabel(latestRun.resultStatus!),
        ),
        _DetailRow(
          label: strings.selectedSymbol,
          value: latestRun.selectedSymbol ?? '-',
        ),
        if (latestRun.primaryBlockReason != null)
          _DetailRow(
            label: strings.primaryBlockReason,
            value: latestRun.primaryBlockReason!,
          ),
        if (latestRun.orderId != null)
          _DetailRow(
            label: strings.relatedOrderLog,
            value: latestRun.orderId.toString(),
          ),
        if (latestRun.brokerOrderId != null)
          _DetailRow(
            label: strings.brokerOrderId,
            value: latestRun.brokerOrderId!,
          ),
      ],
    );
  }
}

class _ChecklistBlock extends StatelessWidget {
  const _ChecklistBlock({required this.items, required this.strings});

  final List<AutoBuyLivePhase1ChecklistItem> items;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Divider(color: Colors.white.withValues(alpha: 0.14)),
        Text(
          strings.preflightChecklist,
          style: const TextStyle(fontWeight: FontWeight.w900),
        ),
        const SizedBox(height: 6),
        for (final item in items.take(12))
          Padding(
            padding: const EdgeInsets.only(bottom: 4),
            child: Text(
              '${strings.preflightChecklistStatus(item.status)} ${strings.preflightChecklistLabel(item.key)}'
              '${item.reason == null ? '' : ' / ${item.reason}'}',
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: item.failed ? Colors.orangeAccent : Colors.white70,
                fontSize: 12,
              ),
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
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.32)),
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
                  style: TextStyle(
                    color: color,
                    fontSize: 16,
                    fontWeight: FontWeight.w900,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  detail,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: Colors.white70),
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
    return Container(
      constraints: const BoxConstraints(minWidth: 132, maxWidth: 210),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(color: Colors.white60, fontSize: 11),
          ),
          const SizedBox(height: 3),
          Text(
            value,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontWeight: FontWeight.w900),
          ),
        ],
      ),
    );
  }
}

class _DetailRow extends StatelessWidget {
  const _DetailRow({
    required this.label,
    required this.value,
    this.valueColor,
    this.valueMaxLines = 2,
  });

  final String label;
  final String value;
  final Color? valueColor;
  final int valueMaxLines;

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
            flex: 2,
            child: Text(
              value,
              maxLines: valueMaxLines,
              overflow: TextOverflow.ellipsis,
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

class _SmallBadge extends StatelessWidget {
  const _SmallBadge({required this.text, this.color = Colors.lightBlueAccent});

  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
      style: TextStyle(
        color: color,
        fontSize: 11,
        fontWeight: FontWeight.w900,
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
              color: Colors.amberAccent.withValues(alpha: 0.10),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(
                color: Colors.amberAccent.withValues(alpha: 0.28),
              ),
            ),
            child: Text(
              badge,
              style: const TextStyle(
                color: Colors.amberAccent,
                fontSize: 11,
                fontWeight: FontWeight.w800,
              ),
            ),
          ),
      ],
    );
  }
}

Color _statusColor(AutoBuyLivePhase1Result result) {
  if (result.submitted) return Colors.greenAccent;
  if (result.resultStatus == 'disabled') return Colors.white54;
  if (result.resultStatus == 'pending_sync') return Colors.amberAccent;
  if (result.blocked) return Colors.orangeAccent;
  return Colors.lightBlueAccent;
}

String _number(num? value) {
  if (value == null) return '-';
  return value.toStringAsFixed(value % 1 == 0 ? 0 : 2);
}

String _money(num? value) {
  if (value == null) return '-';
  final fixed = value.toStringAsFixed(0);
  final buffer = StringBuffer();
  for (var i = 0; i < fixed.length; i += 1) {
    final remaining = fixed.length - i;
    buffer.write(fixed[i]);
    if (remaining > 1 && remaining % 3 == 1) {
      buffer.write(',');
    }
  }
  return '\u20A9${buffer.toString()}';
}
