import 'package:flutter/material.dart';

import '../../../core/i18n/app_strings.dart';
import '../../../core/utils/timestamp_formatter.dart';
import '../../../models/position_lifecycle.dart';
import '../../dashboard/dashboard_controller.dart';

class PositionLifecyclePanel extends StatelessWidget {
  const PositionLifecyclePanel({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final strings = controller.strings;
        final lifecycle = controller.positionLifecycle;
        final loading = controller.positionLifecycleLoading;
        return Container(
          key: const ValueKey('position-lifecycle-panel'),
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
                  const Icon(Icons.timeline_outlined,
                      color: Colors.amberAccent, size: 20),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          strings.positionLifecycle,
                          style: const TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w900,
                          ),
                        ),
                        const SizedBox(height: 3),
                        Text(
                          lifecycle == null
                              ? strings.tradeFlowAudit
                              : '${strings.tradeFlowAudit} / ${lifecycle.items.length}',
                          style: const TextStyle(color: Colors.white70),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    key: const ValueKey('refresh-position-lifecycle-button'),
                    tooltip: strings.refreshLifecycle,
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
              _BadgeWrap(labels: [
                strings.readOnly,
                strings.noBrokerSubmitDisplay,
                strings.noAutoSubmit,
              ]),
              if (controller.positionLifecycleError != null) ...[
                const SizedBox(height: 10),
                Text(
                  controller.positionLifecycleError!,
                  style: const TextStyle(color: Colors.orangeAccent),
                ),
              ],
              if (loading && lifecycle == null) ...[
                const SizedBox(height: 12),
                const LinearProgressIndicator(),
              ],
              const SizedBox(height: 12),
              if (lifecycle == null)
                _EmptyLine(text: strings.statusNotLoaded)
              else if (lifecycle.items.isEmpty)
                _EmptyLine(text: strings.noLifecycleItems)
              else ...[
                _SummaryGrid(lifecycle: lifecycle, strings: strings),
                const SizedBox(height: 12),
                for (final item in lifecycle.items) ...[
                  _LifecycleItemTile(item: item, strings: strings),
                  const SizedBox(height: 8),
                ],
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
    final result = await controller.refreshPositionLifecycle();
    if (!context.mounted || !showSnack) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(result.message)),
    );
  }
}

class _SummaryGrid extends StatelessWidget {
  const _SummaryGrid({required this.lifecycle, required this.strings});

  final PositionLifecycle lifecycle;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    final totals = lifecycle.totals;
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        _MetricTile(
          key: const ValueKey('position-lifecycle-open-count'),
          label: strings.lifecycleOpen,
          value: '${totals.openPositionCount}',
        ),
        _MetricTile(
          key: const ValueKey('position-lifecycle-closed-count'),
          label: strings.lifecycleClosed,
          value: '${totals.closedLifecycleCount}',
        ),
        _MetricTile(
          label: strings.unrealizedPl,
          value: _money(totals.totalUnrealizedPl, lifecycle.market),
        ),
        _MetricTile(
          label: strings.realizedPl,
          value:
              '${_money(totals.totalRealizedPl, lifecycle.market)} / ${_percent(totals.totalRealizedPlPct)}',
        ),
      ],
    );
  }
}

class _LifecycleItemTile extends StatelessWidget {
  const _LifecycleItemTile({required this.item, required this.strings});

  final PositionLifecycleItem item;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    final statusLabel = item.isOpen
        ? strings.lifecycleOpen
        : (item.isClosed
            ? strings.lifecycleClosed
            : strings.statusLabel(item.lifecycleStatus));
    final plLabel = item.isClosed
        ? _plLabel(item.realizedPl, item.realizedPlPct, item.market, strings)
        : _plLabel(
            item.unrealizedPl,
            item.unrealizedPlPct,
            item.market,
            strings,
          );
    return Container(
      key: ValueKey('position-lifecycle-item-${item.lifecycleId}'),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: ExpansionTile(
        key: ValueKey('position-lifecycle-expansion-${item.lifecycleId}'),
        tilePadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
        childrenPadding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
        title: Row(
          children: [
            Expanded(
              child: Text(
                item.displayName,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontWeight: FontWeight.w900),
              ),
            ),
            const SizedBox(width: 8),
            _StatusPill(label: statusLabel, closed: item.isClosed),
          ],
        ),
        subtitle: Padding(
          padding: const EdgeInsets.only(top: 6),
          child: Text(
            '${strings.statusLabel(item.entrySource)} / $plLabel',
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(color: Colors.white70),
          ),
        ),
        children: [
          _LifecycleDetails(item: item, strings: strings),
          if (item.auditFlags.isNotEmpty) ...[
            const SizedBox(height: 8),
            _FlagWrap(
              values: item.auditFlags,
              highlight: item.hasIncompleteCalculation,
              strings: strings,
            ),
          ],
          const SizedBox(height: 10),
          Align(
            alignment: Alignment.centerLeft,
            child: Text(
              strings.auditTrace,
              style: const TextStyle(fontWeight: FontWeight.w800),
            ),
          ),
          const SizedBox(height: 6),
          if (item.events.isEmpty)
            _EmptyLine(text: strings.insufficientData)
          else
            for (final event in item.events)
              _TimelineEventRow(event: event, strings: strings),
        ],
      ),
    );
  }
}

class _LifecycleDetails extends StatelessWidget {
  const _LifecycleDetails({required this.item, required this.strings});

  final PositionLifecycleItem item;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 12,
      runSpacing: 8,
      children: [
        _DetailChip(
          label: strings.entryLabel,
          value: _moneyOrIncomplete(item.entryNotional, item.market, strings),
        ),
        _DetailChip(
          label: strings.exitLabel,
          value: _moneyOrIncomplete(item.exitNotional, item.market, strings),
        ),
        _DetailChip(
          label: strings.averageEntryPrice,
          value:
              _moneyOrIncomplete(item.entryAveragePrice, item.market, strings),
        ),
        _DetailChip(
          label: strings.averageExitPrice,
          value:
              _moneyOrIncomplete(item.exitAveragePrice, item.market, strings),
        ),
        _DetailChip(
          label: strings.holdingPeriod,
          value: _holdingPeriod(item.holdingPeriodMinutes),
        ),
        _DetailChip(
          label: strings.relatedPromotion,
          value: item.relatedPromotionId?.toString() ?? '-',
        ),
        _DetailChip(
          label: strings.relatedOrder,
          value: [
            if (item.entryOrderId != null) '#${item.entryOrderId}',
            if (item.exitOrderId != null) '#${item.exitOrderId}',
          ].join(' / ').trim().isEmpty
              ? '-'
              : [
                  if (item.entryOrderId != null) '#${item.entryOrderId}',
                  if (item.exitOrderId != null) '#${item.exitOrderId}',
                ].join(' / '),
        ),
      ],
    );
  }
}

class _TimelineEventRow extends StatelessWidget {
  const _TimelineEventRow({required this.event, required this.strings});

  final PositionLifecycleEvent event;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    final time = event.timestamp == null
        ? '-'
        : formatTimestampWithKst(event.timestamp!.toIso8601String());
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 92,
            child: Text(
              time,
              style: const TextStyle(color: Colors.white54, fontSize: 12),
            ),
          ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  strings.lifecycleEventLabel(event.eventType),
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
                const SizedBox(height: 2),
                Text(
                  [
                    if (event.status?.trim().isNotEmpty == true)
                      strings.statusLabel(event.status!),
                    if (event.source?.trim().isNotEmpty == true) event.source!,
                  ].join(' / '),
                  style: const TextStyle(color: Colors.white60, fontSize: 12),
                ),
                if (event.summary?.trim().isNotEmpty == true) ...[
                  const SizedBox(height: 2),
                  Text(
                    event.summary!,
                    style: const TextStyle(color: Colors.white70, fontSize: 12),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _MetricTile extends StatelessWidget {
  const _MetricTile({
    super.key,
    required this.label,
    required this.value,
  });

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(minWidth: 138, maxWidth: 220),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: const TextStyle(color: Colors.white60)),
          const SizedBox(height: 4),
          Text(
            value,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800),
          ),
        ],
      ),
    );
  }
}

class _DetailChip extends StatelessWidget {
  const _DetailChip({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(minWidth: 148, maxWidth: 250),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(color: Colors.white54, fontSize: 12),
          ),
          const SizedBox(height: 3),
          Text(
            value,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontWeight: FontWeight.w700),
          ),
        ],
      ),
    );
  }
}

class _StatusPill extends StatelessWidget {
  const _StatusPill({required this.label, required this.closed});

  final String label;
  final bool closed;

  @override
  Widget build(BuildContext context) {
    final color = closed ? Colors.blueAccent : Colors.greenAccent;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.35)),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: color,
          fontSize: 12,
          fontWeight: FontWeight.w800,
        ),
      ),
    );
  }
}

class _FlagWrap extends StatelessWidget {
  const _FlagWrap({
    required this.values,
    required this.highlight,
    required this.strings,
  });

  final List<String> values;
  final bool highlight;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 6,
      runSpacing: 6,
      children: [
        for (final value in values)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: (highlight ? Colors.orangeAccent : Colors.white)
                  .withValues(alpha: 0.10),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(
                color: (highlight ? Colors.orangeAccent : Colors.white)
                    .withValues(alpha: 0.20),
              ),
            ),
            child: Text(
              value == 'calculation_incomplete'
                  ? strings.calculationIncomplete
                  : strings.statusLabel(value),
              style: TextStyle(
                color: highlight ? Colors.orangeAccent : Colors.white70,
                fontSize: 12,
              ),
            ),
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
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: Colors.white12),
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

class _EmptyLine extends StatelessWidget {
  const _EmptyLine({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(text, style: const TextStyle(color: Colors.white70));
  }
}

String _plLabel(
  double? value,
  double? pct,
  String market,
  AppStrings strings,
) {
  if (value == null) return strings.calculationIncomplete;
  return '${_money(value, market)} / ${_percent(pct)}';
}

String _moneyOrIncomplete(
  double? value,
  String market,
  AppStrings strings,
) {
  return value == null ? strings.calculationIncomplete : _money(value, market);
}

String _money(num? value, String market) {
  if (value == null) return '-';
  final isKr = market.trim().toUpperCase() == 'KR';
  final decimals = isKr ? 0 : 2;
  final sign = value < 0 ? '-' : '';
  final symbol = isKr ? '\u20A9' : r'$';
  return '$sign$symbol${_grouped(value.abs(), decimals)}';
}

String _percent(num? value) {
  if (value == null) return '-';
  final percent = value * 100;
  final sign = percent > 0 ? '+' : '';
  return '$sign${percent.toStringAsFixed(2)}%';
}

String _holdingPeriod(int? minutes) {
  if (minutes == null) return '-';
  if (minutes < 60) return '${minutes}m';
  final hours = minutes ~/ 60;
  final remaining = minutes % 60;
  return remaining == 0 ? '${hours}h' : '${hours}h ${remaining}m';
}

String _grouped(num value, int decimals) {
  final fixed = value.toStringAsFixed(decimals);
  final parts = fixed.split('.');
  final whole = parts.first;
  final buffer = StringBuffer();
  for (var i = 0; i < whole.length; i += 1) {
    final remaining = whole.length - i;
    buffer.write(whole[i]);
    if (remaining > 1 && remaining % 3 == 1) {
      buffer.write(',');
    }
  }
  if (decimals == 0) return buffer.toString();
  return '${buffer.toString()}.${parts.last}';
}
