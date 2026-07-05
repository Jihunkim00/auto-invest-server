import 'package:flutter/material.dart';

import '../../../core/i18n/app_strings.dart';
import '../../../core/utils/timestamp_formatter.dart';
import '../../../models/daily_ops_summary.dart';
import '../../dashboard/dashboard_controller.dart';

class DailyOpsSummaryPanel extends StatelessWidget {
  const DailyOpsSummaryPanel({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final strings = controller.strings;
        final summary = controller.dailyOpsSummary;
        final loading = controller.dailyOpsSummaryLoading;
        return Container(
          key: const ValueKey('daily-ops-summary-panel'),
          width: double.infinity,
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
                  const Icon(Icons.fact_check_outlined,
                      color: Colors.tealAccent, size: 20),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          strings.dailyOperationsSummary,
                          style: const TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w900,
                          ),
                        ),
                        const SizedBox(height: 3),
                        Text(
                          summary == null
                              ? strings.statusNotLoaded
                              : '${strings.brokerName(summary.provider)} / ${summary.market} / ${summary.date}',
                          key: const ValueKey('daily-ops-runtime-status'),
                          style: const TextStyle(color: Colors.white70),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    key: const ValueKey('daily-ops-refresh-button'),
                    tooltip: strings.refreshDailySummary,
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
              _BadgeWrap(labels: _badges(strings, summary)),
              if (controller.dailyOpsSummaryError != null) ...[
                const SizedBox(height: 10),
                Text(
                  controller.dailyOpsSummaryError!,
                  style: const TextStyle(color: Colors.orangeAccent),
                ),
              ],
              if (loading && summary == null) ...[
                const SizedBox(height: 12),
                const LinearProgressIndicator(),
              ],
              const SizedBox(height: 12),
              if (summary == null)
                _EmptyLine(text: strings.statusNotLoaded)
              else ...[
                Container(
                  key: const ValueKey('daily-ops-summary-cards'),
                  child: _SummaryGrid(summary: summary, strings: strings),
                ),
                const SizedBox(height: 12),
                _ReconciliationBlock(summary: summary, strings: strings),
                const SizedBox(height: 8),
                Container(
                  key: const ValueKey('daily-ops-details-section'),
                  child: _DetailsExpansion(summary: summary, strings: strings),
                ),
              ],
            ],
          ),
        );
      },
    );
  }

  List<String> _badges(AppStrings strings, DailyOpsSummary? summary) {
    final labels = <String>[
      strings.readOnly,
      strings.localDbOnly,
      strings.noBrokerSubmit,
      strings.noValidation,
      strings.noSettingsChange,
      strings.noSync,
      strings.noRetry,
    ];
    if (summary == null) {
      labels.add(strings.noLiveOrders);
      return labels;
    }
    if (summary.runtimeState.dryRun) labels.add(strings.dryRunOnly);
    if (!summary.runtimeState.schedulerRealOrdersAllowed) {
      labels.add(strings.schedulerRealOrdersDisabled);
    }
    if (!summary.runtimeState.kisRealOrderEnabled) {
      labels.add(strings.noLiveOrders);
    }
    return labels;
  }

  Future<void> _refresh(
    BuildContext context, {
    required bool showSnack,
  }) async {
    final result = await controller.refreshDailyOpsSummary();
    if (!context.mounted || !showSnack) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(result.message)),
    );
  }
}

class _SummaryGrid extends StatelessWidget {
  const _SummaryGrid({required this.summary, required this.strings});

  final DailyOpsSummary summary;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        _MetricTile(
          label: strings.realizedPl,
          value: _money(summary.pnlSummary.realizedPl,
              summary.pnlSummary.currency, strings),
        ),
        _MetricTile(
          label: strings.unrealizedPl,
          value: _money(summary.pnlSummary.unrealizedPl,
              summary.pnlSummary.currency, strings),
        ),
        _MetricTile(
          label: strings.ordersToday,
          value: '${summary.orderSummary.totalOrdersToday}',
        ),
        _MetricTile(
          label: strings.syncRequired,
          value: '${summary.orderSummary.syncRequiredCount}',
          valueColor: summary.orderSummary.syncRequiredCount > 0
              ? Colors.orangeAccent
              : Colors.greenAccent,
        ),
        _MetricTile(
          label: strings.promotionsPending,
          value: '${summary.promotionSummary.pending}',
        ),
        _MetricTile(
          label: strings.blockedAttempts,
          value: '${summary.tradeActivity.blockedAttemptCount}',
          valueColor: summary.tradeActivity.blockedAttemptCount > 0
              ? Colors.orangeAccent
              : Colors.white,
        ),
      ],
    );
  }
}

class _ReconciliationBlock extends StatelessWidget {
  const _ReconciliationBlock({required this.summary, required this.strings});

  final DailyOpsSummary summary;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    final reconciliation = summary.reconciliation;
    final statusLabel = _statusLabel(reconciliation.status, strings);
    final generated = summary.generatedAt == null
        ? '-'
        : formatTimestampWithKst(summary.generatedAt!.toIso8601String());
    return Container(
      key: const ValueKey('daily-ops-reconciliation-section'),
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  strings.brokerReconciliation,
                  style: const TextStyle(fontWeight: FontWeight.w900),
                ),
              ),
              _StatusPill(
                key: const ValueKey('daily-ops-reconciliation-status'),
                label: statusLabel,
                color: _statusColor(reconciliation.status),
              ),
            ],
          ),
          const SizedBox(height: 8),
          _InfoRow(label: strings.generatedAt, value: generated),
          _InfoRow(
            label: strings.syncRequired,
            value: '${summary.orderSummary.syncRequiredCount}',
          ),
          _InfoRow(
            label: strings.warning,
            value: reconciliation.warnings.isEmpty
                ? '-'
                : reconciliation.warnings
                    .map((item) => strings.statusLabel(item))
                    .join(' / '),
          ),
          if (reconciliation.nextSafeActions.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(
              strings.nextSafeActions,
              style: const TextStyle(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 4),
            for (final action in reconciliation.nextSafeActions.take(3))
              Padding(
                padding: const EdgeInsets.only(bottom: 3),
                child: Text(
                  action,
                  style: const TextStyle(color: Colors.white70, height: 1.25),
                ),
              ),
          ],
        ],
      ),
    );
  }
}

class _DetailsExpansion extends StatelessWidget {
  const _DetailsExpansion({required this.summary, required this.strings});

  final DailyOpsSummary summary;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    return Theme(
      data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
      child: ExpansionTile(
        key: const ValueKey('daily-ops-summary-details-expansion'),
        tilePadding: EdgeInsets.zero,
        childrenPadding: EdgeInsets.zero,
        title: Text(
          strings.detailsLabel,
          style: const TextStyle(fontWeight: FontWeight.w900),
        ),
        children: [
          _DetailSection(
            title: strings.orderSummary,
            items: summary.details.recentOrders,
            emptyText: strings.none,
          ),
          _DetailSection(
            title: strings.syncRequired,
            items: summary.details.syncRequiredItems,
            emptyText: strings.none,
          ),
          _DetailSection(
            title: strings.blockedAttempts,
            items: summary.details.blockedItems,
            emptyText: strings.none,
          ),
        ],
      ),
    );
  }
}

class _DetailSection extends StatelessWidget {
  const _DetailSection({
    required this.title,
    required this.items,
    required this.emptyText,
  });

  final String title;
  final List<Map<String, dynamic>> items;
  final String emptyText;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(top: 8),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: const TextStyle(fontWeight: FontWeight.w800)),
          const SizedBox(height: 6),
          if (items.isEmpty)
            Text(emptyText, style: const TextStyle(color: Colors.white60))
          else
            for (final item in items.take(5)) ...[
              Text(
                _detailLine(item),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(color: Colors.white70, height: 1.25),
              ),
              const SizedBox(height: 4),
            ],
        ],
      ),
    );
  }

  String _detailLine(Map<String, dynamic> item) {
    final parts = [
      item['symbol'],
      item['side'],
      item['status'] ?? item['internal_status'],
      item['broker_status'],
      item['block_reason'],
    ]
        .where((value) => value != null && value.toString().trim().isNotEmpty)
        .map((value) => value.toString())
        .toList();
    if (parts.isEmpty) return item.toString();
    return parts.join(' / ');
  }
}

class _MetricTile extends StatelessWidget {
  const _MetricTile({
    required this.label,
    required this.value,
    this.valueColor,
  });

  final String label;
  final String value;
  final Color? valueColor;

  @override
  Widget build(BuildContext context) {
    return ConstrainedBox(
      constraints: const BoxConstraints(minWidth: 150, maxWidth: 210),
      child: Container(
        padding: const EdgeInsets.all(12),
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
              style: const TextStyle(fontSize: 12, color: Colors.white70),
            ),
            const SizedBox(height: 4),
            Text(
              value,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.w900,
                color: valueColor ?? Colors.white,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 128,
            child: Text(
              label,
              style: const TextStyle(color: Colors.white60),
            ),
          ),
          Expanded(
            child: Text(
              value,
              style: const TextStyle(fontWeight: FontWeight.w700),
            ),
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
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
            ),
            child: Text(
              label,
              style: const TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w800,
                letterSpacing: 0,
              ),
            ),
          ),
      ],
    );
  }
}

class _StatusPill extends StatelessWidget {
  const _StatusPill({Key? key, required this.label, required this.color})
      : super(key: key);

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.16),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.45)),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: color,
          fontSize: 11,
          fontWeight: FontWeight.w900,
          letterSpacing: 0,
        ),
      ),
    );
  }
}

class _EmptyLine extends StatelessWidget {
  const _EmptyLine({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(text, style: const TextStyle(color: Colors.white60));
  }
}

String _money(double? value, String currency, AppStrings strings) {
  if (value == null) return strings.calculationIncomplete;
  final normalized = currency.toUpperCase();
  if (normalized == 'KRW') {
    return '\u20A9${value.toStringAsFixed(0)}';
  }
  if (normalized == 'USD') {
    return '\$${value.toStringAsFixed(2)}';
  }
  return value.toStringAsFixed(2);
}

String _statusLabel(String value, AppStrings strings) {
  final normalized = value.toLowerCase();
  if (normalized == 'attention_required') return strings.attentionRequired;
  if (normalized == 'ok') return strings.okStatus;
  return strings.statusLabel(value);
}

Color _statusColor(String value) {
  switch (value.toLowerCase()) {
    case 'ok':
      return Colors.greenAccent;
    case 'attention_required':
      return Colors.orangeAccent;
    case 'warning':
      return Colors.amberAccent;
    default:
      return Colors.white70;
  }
}
