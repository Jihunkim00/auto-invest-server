import 'package:flutter/material.dart';

import '../../../core/i18n/app_strings.dart';
import '../../../core/utils/timestamp_formatter.dart';
import '../../../models/ops_production_readiness.dart';
import '../../dashboard/dashboard_controller.dart';

class ProductionReadinessPanel extends StatelessWidget {
  const ProductionReadinessPanel({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final strings = controller.strings;
        final readiness = controller.latestOpsProductionReadiness;
        final loading = controller.opsProductionReadinessLoading;
        return Container(
          key: const ValueKey('production-readiness-panel'),
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
                    Icons.health_and_safety_outlined,
                    color: Colors.lightBlueAccent,
                    size: 20,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          strings.productionReadiness,
                          style: const TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w900,
                          ),
                        ),
                        const SizedBox(height: 3),
                        Text(
                          readiness == null
                              ? strings.statusNotLoaded
                              : '${strings.brokerName(readiness.provider)} / ${readiness.market} / ${_timestamp(readiness.generatedAt)}',
                          key: const ValueKey(
                            'production-readiness-runtime-status',
                          ),
                          style: const TextStyle(color: Colors.white70),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    key: const ValueKey('production-readiness-refresh-button'),
                    tooltip: strings.refreshProductionReadiness,
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
                strings.operatorReadOnly,
                strings.operatorNoLiveOrders,
                strings.automationUnlockNotAllowed,
              ]),
              if (controller.opsProductionReadinessError != null) ...[
                const SizedBox(height: 10),
                Text(
                  controller.opsProductionReadinessError!,
                  style: const TextStyle(color: Colors.orangeAccent),
                ),
              ],
              if (loading && readiness == null) ...[
                const SizedBox(height: 12),
                const LinearProgressIndicator(),
              ],
              const SizedBox(height: 12),
              if (readiness == null)
                _EmptyLine(text: strings.statusNotLoaded)
              else ...[
                _StatusBlock(readiness: readiness, strings: strings),
                const SizedBox(height: 12),
                _SummaryGrid(readiness: readiness, strings: strings),
                const SizedBox(height: 12),
                _ReasonBlock(readiness: readiness, strings: strings),
                const SizedBox(height: 12),
                _ChecklistGroups(readiness: readiness, strings: strings),
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
    final result = await controller.refreshOpsProductionReadiness();
    if (!context.mounted || !showSnack) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(result.message)),
    );
  }
}

class _StatusBlock extends StatelessWidget {
  const _StatusBlock({required this.readiness, required this.strings});

  final OpsProductionReadiness readiness;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    final color = _overallColor(readiness.overallStatus);
    return Container(
      key: const ValueKey('production-readiness-status-card'),
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.32)),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  strings.liveReadinessStatus,
                  style: const TextStyle(
                    color: Colors.white70,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  _overallLabel(readiness.overallStatus, strings),
                  style: TextStyle(
                    color: color,
                    fontSize: 22,
                    fontWeight: FontWeight.w900,
                  ),
                ),
              ],
            ),
          ),
          _ScorePill(score: readiness.readinessScore),
        ],
      ),
    );
  }
}

class _SummaryGrid extends StatelessWidget {
  const _SummaryGrid({required this.readiness, required this.strings});

  final OpsProductionReadiness readiness;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        _MetricTile(
          label: strings.blockedChecks,
          value: '${readiness.summary.blockedCount}',
          valueColor: readiness.summary.blockedCount > 0
              ? Colors.redAccent
              : Colors.greenAccent,
        ),
        _MetricTile(
          label: strings.warning,
          value: '${readiness.summary.warningCount}',
          valueColor: readiness.summary.warningCount > 0
              ? Colors.orangeAccent
              : Colors.greenAccent,
        ),
        _MetricTile(
          label: strings.riskAlerts,
          value: '${readiness.summary.activeAlertCount}',
          valueColor: readiness.summary.activeAlertCount > 0
              ? Colors.orangeAccent
              : Colors.greenAccent,
        ),
        _MetricTile(
          label: strings.syncRequired,
          value: '${readiness.summary.syncRequiredAlertCount}',
          valueColor: readiness.summary.syncRequiredAlertCount > 0
              ? Colors.orangeAccent
              : Colors.greenAccent,
        ),
      ],
    );
  }
}

class _ReasonBlock extends StatelessWidget {
  const _ReasonBlock({required this.readiness, required this.strings});

  final OpsProductionReadiness readiness;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          strings.primaryBlockReasons,
          style: const TextStyle(fontWeight: FontWeight.w900),
        ),
        const SizedBox(height: 6),
        _TextList(
          values: readiness.blockingReasons,
          emptyText: strings.none,
          color: readiness.blockingReasons.isEmpty
              ? Colors.white60
              : Colors.orangeAccent,
        ),
        const SizedBox(height: 10),
        Text(
          strings.nextSafeActions,
          style: const TextStyle(fontWeight: FontWeight.w900),
        ),
        const SizedBox(height: 6),
        _TextList(
          values: readiness.nextSafeActions,
          emptyText: strings.none,
          color: Colors.white70,
        ),
      ],
    );
  }
}

class _ChecklistGroups extends StatelessWidget {
  const _ChecklistGroups({required this.readiness, required this.strings});

  final OpsProductionReadiness readiness;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    final grouped = readiness.groupedChecklist;
    final orderedKeys = [
      'runtime',
      'broker',
      'scheduler',
      'orders',
      'positions',
      'pnl',
      'alerts',
      'database',
      'agent_chat',
      'guarded_buy',
      'guarded_sell',
    ].where(grouped.containsKey).toList();
    return Theme(
      data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
      child: Column(
        key: const ValueKey('production-readiness-checklist-groups'),
        children: [
          for (final key in orderedKeys)
            ExpansionTile(
              key: ValueKey('production-readiness-group-$key'),
              tilePadding: EdgeInsets.zero,
              childrenPadding: EdgeInsets.zero,
              initiallyExpanded: key == 'runtime' || key == 'broker',
              title: Text(
                _categoryLabel(key, strings),
                style: const TextStyle(fontWeight: FontWeight.w900),
              ),
              children: [
                for (final item in grouped[key]!)
                  _ChecklistRow(item: item, strings: strings),
              ],
            ),
        ],
      ),
    );
  }
}

class _ChecklistRow extends StatelessWidget {
  const _ChecklistRow({required this.item, required this.strings});

  final OpsReadinessChecklistItem item;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    final color = _checkColor(item.status);
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.045),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.30)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Wrap(
          spacing: 8,
          runSpacing: 8,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            _StatusPill(label: _checkLabel(item.status, strings), color: color),
            Text(
              item.title,
              style: const TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.w800,
              ),
            ),
          ],
        ),
        const SizedBox(height: 6),
        Text(
          item.detail,
          style: const TextStyle(color: Colors.white70, height: 1.25),
        ),
        if (item.nextSafeAction.isNotEmpty) ...[
          const SizedBox(height: 5),
          Text(
            item.nextSafeAction,
            style: const TextStyle(color: Colors.white38, fontSize: 12),
          ),
        ],
      ]),
    );
  }
}

class _TextList extends StatelessWidget {
  const _TextList({
    required this.values,
    required this.emptyText,
    required this.color,
  });

  final List<String> values;
  final String emptyText;
  final Color color;

  @override
  Widget build(BuildContext context) {
    if (values.isEmpty) {
      return Text(emptyText, style: TextStyle(color: color));
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final value in values.take(6))
          Padding(
            padding: const EdgeInsets.only(bottom: 4),
            child: Text(value, style: TextStyle(color: color, height: 1.25)),
          ),
      ],
    );
  }
}

class _MetricTile extends StatelessWidget {
  const _MetricTile({
    required this.label,
    required this.value,
    required this.valueColor,
  });

  final String label;
  final String value;
  final Color valueColor;

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
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
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
              color: valueColor,
            ),
          ),
        ]),
      ),
    );
  }
}

class _ScorePill extends StatelessWidget {
  const _ScorePill({required this.score});

  final int score;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.16)),
      ),
      child: Text(
        '$score / 100',
        style: const TextStyle(fontWeight: FontWeight.w900),
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
  const _StatusPill({required this.label, required this.color});

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

String _overallLabel(String value, AppStrings strings) {
  switch (value) {
    case 'ready':
      return strings.readinessReady;
    case 'warning':
      return strings.readinessWarning;
    case 'blocked':
      return strings.readinessBlocked;
    default:
      return strings.readinessUnknown;
  }
}

Color _overallColor(String value) {
  switch (value) {
    case 'ready':
      return Colors.greenAccent;
    case 'warning':
      return Colors.orangeAccent;
    case 'blocked':
      return Colors.redAccent;
    default:
      return Colors.lightBlueAccent;
  }
}

String _checkLabel(String value, AppStrings strings) {
  switch (value) {
    case 'pass':
      return strings.readinessReady;
    case 'warn':
      return strings.readinessWarning;
    case 'fail':
      return strings.readinessBlocked;
    default:
      return strings.readinessUnknown;
  }
}

Color _checkColor(String value) {
  switch (value) {
    case 'pass':
      return Colors.greenAccent;
    case 'warn':
      return Colors.orangeAccent;
    case 'fail':
      return Colors.redAccent;
    default:
      return Colors.lightBlueAccent;
  }
}

String _categoryLabel(String value, AppStrings strings) {
  switch (value) {
    case 'runtime':
      return strings.runtimeSettings;
    case 'broker':
      return strings.brokerStatus;
    case 'scheduler':
      return strings.schedulerSafety;
    case 'orders':
      return strings.orderReconciliation;
    case 'positions':
    case 'pnl':
      return strings.positionsPnl;
    case 'alerts':
      return strings.alertStatus;
    case 'agent_chat':
      return strings.agentChatSafety;
    case 'guarded_buy':
      return strings.guardedBuy;
    case 'guarded_sell':
      return strings.guardedSell;
    case 'database':
      return strings.databaseStatus;
  }
  return value.replaceAll('_', ' ');
}

String _timestamp(DateTime? value) {
  if (value == null) return '-';
  return formatTimestampWithKst(value.toIso8601String());
}
