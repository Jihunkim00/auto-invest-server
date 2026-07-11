import 'package:flutter/material.dart';

import '../../../core/i18n/app_strings.dart';
import '../../../core/utils/timestamp_formatter.dart';
import '../../../models/broker_sync_watchdog.dart';
import '../../dashboard/dashboard_controller.dart';

class BrokerSyncWatchdogPanel extends StatefulWidget {
  const BrokerSyncWatchdogPanel({super.key, required this.controller});

  final DashboardController controller;

  @override
  State<BrokerSyncWatchdogPanel> createState() =>
      _BrokerSyncWatchdogPanelState();
}

class _BrokerSyncWatchdogPanelState extends State<BrokerSyncWatchdogPanel> {
  bool _detailsExpanded = false;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: widget.controller,
      builder: (context, _) {
        final controller = widget.controller;
        final strings = controller.strings;
        final result =
            controller.brokerSyncWatchdogStatus ?? controller.brokerSyncWatchdogResult;
        final loading = controller.brokerSyncWatchdogLoading;
        final color = _healthColor(result?.syncHealth);
        return Container(
          key: const ValueKey('broker-sync-watchdog-panel'),
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
                  Icon(_healthIcon(result?.syncHealth), color: color, size: 20),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          strings.brokerSyncWatchdog,
                          style: const TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w900,
                          ),
                        ),
                        const SizedBox(height: 3),
                        Text(
                          result == null
                              ? strings.orderPositionSyncHealth
                              : '${strings.brokerName(result.provider)} / ${result.market} / ${_timestamp(result.generatedAt)}',
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
              _BadgeWrap(labels: [
                strings.operatorReadOnly,
                strings.operatorNoLiveOrders,
                strings.noOrderCancel,
                strings.noBrokerSubmitDisplay,
              ]),
              if (controller.brokerSyncWatchdogError != null) ...[
                const SizedBox(height: 10),
                Text(
                  controller.brokerSyncWatchdogError!,
                  style: const TextStyle(color: Colors.orangeAccent),
                ),
              ],
              const SizedBox(height: 12),
              if (result == null)
                _EmptyState(strings: strings)
              else
                _WatchdogSummary(result: result, strings: strings),
              if (_detailsExpanded) ...[
                const SizedBox(height: 10),
                _IssueDetails(result: result, strings: strings),
              ],
              const SizedBox(height: 12),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  OutlinedButton.icon(
                    key: const ValueKey('refresh-broker-sync-watchdog-status'),
                    onPressed: loading ? null : () => _refresh(context),
                    icon: const Icon(Icons.refresh, size: 18),
                    label: Text(strings.refreshWatchdogStatus),
                  ),
                  FilledButton.icon(
                    key: const ValueKey('run-broker-sync-watchdog-once'),
                    onPressed: loading ? null : () => _runOnce(context),
                    icon: const Icon(Icons.play_arrow_outlined, size: 18),
                    label: Text(strings.runWatchdogOnce),
                  ),
                  TextButton.icon(
                    key: const ValueKey(
                      'toggle-broker-sync-watchdog-details',
                    ),
                    onPressed: () {
                      setState(() => _detailsExpanded = !_detailsExpanded);
                    },
                    icon: Icon(
                      _detailsExpanded ? Icons.expand_less : Icons.expand_more,
                    ),
                    label: Text(
                      _detailsExpanded
                          ? strings.collapseIssueDetails
                          : strings.expandIssueDetails,
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
    final action = await widget.controller.refreshBrokerSyncWatchdog();
    if (!context.mounted) return;
    _snack(context, action.message);
  }

  Future<void> _runOnce(BuildContext context) async {
    final action = await widget.controller.runBrokerSyncWatchdogOnce();
    if (!context.mounted) return;
    _snack(context, action.message);
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
    return _StatusBanner(
      icon: Icons.sync_outlined,
      label: strings.orderPositionSyncHealth,
      detail: strings.statusNotLoaded,
      color: Colors.white54,
    );
  }
}

class _WatchdogSummary extends StatelessWidget {
  const _WatchdogSummary({required this.result, required this.strings});

  final BrokerSyncWatchdogResult result;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    final color = _healthColor(result.syncHealth);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _StatusBanner(
          icon: _healthIcon(result.syncHealth),
          label: strings.orderPositionSyncHealth,
          detail: strings.brokerSyncHealthLabel(result.syncHealth),
          color: color,
        ),
        const SizedBox(height: 10),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            _Metric(
              label: strings.status,
              value: result.automationBlockedBySync
                  ? strings.automationBlocked
                  : strings.automationAllowed,
              valueColor: result.automationBlockedBySync
                  ? Colors.orangeAccent
                  : Colors.greenAccent,
            ),
            _Metric(
              label: strings.localOpenOrders,
              value: '${result.openLocalOrderCount}',
            ),
            _Metric(
              label: strings.brokerOpenOrders,
              value: '${result.brokerOpenOrderCount}',
            ),
            _Metric(
              label: strings.staleOrders,
              value: '${result.staleLocalOrderCount}',
              valueColor: _countColor(result.staleLocalOrderCount),
            ),
            _Metric(
              label: strings.pendingSyncOrders,
              value: '${result.pendingSyncOrderCount}',
              valueColor: _countColor(result.pendingSyncOrderCount),
            ),
            _Metric(
              label: strings.missingBrokerId,
              value: '${result.missingBrokerIdCount}',
              valueColor: _countColor(result.missingBrokerIdCount),
            ),
            _Metric(
              label: strings.missingKisOdno,
              value: '${result.missingKisOdnoCount}',
              valueColor: _countColor(result.missingKisOdnoCount),
            ),
            _Metric(
              label: strings.brokerUnmatchedOrders,
              value: '${result.brokerUnmatchedOrderCount}',
              valueColor: _countColor(result.brokerUnmatchedOrderCount),
            ),
            _Metric(
              label: strings.localUnmatchedOrders,
              value: '${result.localUnmatchedOrderCount}',
              valueColor: _countColor(result.localUnmatchedOrderCount),
            ),
            _Metric(
              label: strings.positionQuantityMismatch,
              value: '${result.positionMismatchCount}',
              valueColor: _countColor(result.positionMismatchCount),
            ),
            _Metric(
              label: strings.stalePositionSnapshots,
              value: '${result.stalePositionSnapshotCount}',
              valueColor: _countColor(result.stalePositionSnapshotCount),
            ),
            _Metric(
              label: strings.cashSnapshotStale,
              value: strings.booleanLabel(result.cashSnapshotStale),
              valueColor:
                  result.cashSnapshotStale ? Colors.orangeAccent : null,
            ),
          ],
        ),
        const SizedBox(height: 8),
        if (result.blockingReasons.isNotEmpty)
          _DetailLine(
            label: strings.primaryBlockingReasons,
            value: result.blockingReasons
                .map(strings.automationControlLabel)
                .join(' | '),
            valueColor: Colors.orangeAccent,
          ),
        if (result.warningReasons.isNotEmpty)
          _DetailLine(
            label: strings.warningReasons,
            value: result.warningReasons.map(strings.statusLabel).join(' | '),
            valueColor: Colors.amberAccent,
          ),
        _DetailLine(
          label: strings.nextSafeAction,
          value: strings.automationControlLabel(result.nextSafeAction),
          valueColor: Colors.lightBlueAccent,
        ),
        _DetailLine(
          label: strings.lastSuccessfulSync,
          value: _timestamp(result.lastSuccessfulSyncAt),
        ),
        _DetailLine(
          label: strings.lastWatchdogRun,
          value: _timestamp(result.lastWatchdogRunAt),
        ),
      ],
    );
  }
}

class _IssueDetails extends StatelessWidget {
  const _IssueDetails({required this.result, required this.strings});

  final BrokerSyncWatchdogResult? result;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    final issues = result?.issues ?? const <BrokerSyncWatchdogIssue>[];
    return _DetailBox(
      children: [
        Text(
          strings.issueDetails,
          style: const TextStyle(fontWeight: FontWeight.w900),
        ),
        const SizedBox(height: 8),
        if (issues.isEmpty)
          Text(
            strings.noSyncIssues,
            style: const TextStyle(color: Colors.white70),
          )
        else
          for (final issue in issues)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: _IssueTile(issue: issue, strings: strings),
            ),
      ],
    );
  }
}

class _IssueTile extends StatelessWidget {
  const _IssueTile({required this.issue, required this.strings});

  final BrokerSyncWatchdogIssue issue;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    final color = issue.critical
        ? Colors.redAccent
        : issue.warning
            ? Colors.orangeAccent
            : Colors.lightBlueAccent;
    final contextEntries = _safeContextEntries(issue.sanitizedContext);
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: 6,
            runSpacing: 6,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              _SmallBadge(
                label: strings.statusLabel(issue.severity),
                color: color,
              ),
              Text(
                strings.statusLabel(issue.issueType),
                style: const TextStyle(fontWeight: FontWeight.w900),
              ),
            ],
          ),
          const SizedBox(height: 6),
          _DetailLine(label: strings.reason, value: issue.reason),
          _DetailLine(
            label: strings.recommendedAction,
            value: strings.statusLabel(issue.recommendedAction),
            valueColor: Colors.lightBlueAccent,
          ),
          if (issue.symbol != null)
            _DetailLine(label: strings.selectedSymbol, value: issue.symbol!),
          if (issue.orderId != null)
            _DetailLine(label: strings.order, value: '${issue.orderId}'),
          if (issue.brokerOrderId != null)
            _DetailLine(
              label: strings.brokerOrderId,
              value: issue.brokerOrderId!,
            ),
          if (issue.kisOdno != null)
            _DetailLine(label: strings.kisOrderNo, value: issue.kisOdno!),
          if (issue.localStatus != null)
            _DetailLine(
              label: strings.internalStatus,
              value: strings.statusLabel(issue.localStatus!),
            ),
          if (issue.brokerStatus != null)
            _DetailLine(
              label: strings.brokerStatus,
              value: strings.statusLabel(issue.brokerStatus!),
            ),
          if (issue.ageMinutes != null)
            _DetailLine(
              label: strings.age,
              value: '${issue.ageMinutes!.toStringAsFixed(1)}m',
            ),
          if (issue.localQuantity != null)
            _DetailLine(
              label: strings.submittedQuantity,
              value: _number(issue.localQuantity!),
            ),
          if (issue.brokerQuantity != null)
            _DetailLine(
              label: strings.filledQuantity,
              value: _number(issue.brokerQuantity!),
            ),
          if (contextEntries.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(
              strings.sanitizedContext,
              style: const TextStyle(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 3),
            for (final entry in contextEntries)
              Text(
                '${strings.statusLabel(entry.key)}: ${entry.value}',
                style: const TextStyle(color: Colors.white70, height: 1.25),
              ),
          ],
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
      constraints: const BoxConstraints(minWidth: 132),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            label,
            style: const TextStyle(color: Colors.white60, fontSize: 11),
          ),
          const SizedBox(height: 3),
          Text(
            value,
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

class _DetailBox extends StatelessWidget {
  const _DetailBox({required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Container(
      key: const ValueKey('broker-sync-watchdog-details'),
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

class _SmallBadge extends StatelessWidget {
  const _SmallBadge({required this.label, required this.color});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.28)),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: color,
          fontSize: 11,
          fontWeight: FontWeight.w900,
        ),
      ),
    );
  }
}

class _DetailLine extends StatelessWidget {
  const _DetailLine({
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
      padding: const EdgeInsets.only(top: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 150,
            child: Text(
              label,
              style: const TextStyle(color: Colors.white60),
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              value,
              style: TextStyle(
                color: valueColor ?? Colors.white70,
                height: 1.25,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

Color _healthColor(String? health) {
  switch (health?.trim().toLowerCase()) {
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

IconData _healthIcon(String? health) {
  switch (health?.trim().toLowerCase()) {
    case 'healthy':
      return Icons.verified_outlined;
    case 'warning':
      return Icons.warning_amber_outlined;
    case 'unsafe':
      return Icons.block_outlined;
    case 'unknown':
    default:
      return Icons.help_outline;
  }
}

Color? _countColor(int count) {
  return count > 0 ? Colors.orangeAccent : null;
}

String _timestamp(DateTime? value) {
  if (value == null) return '-';
  return formatTimestampWithKst(value.toIso8601String());
}

String _number(double value) {
  if (value == value.roundToDouble()) return value.toStringAsFixed(0);
  return value.toStringAsFixed(4);
}

List<MapEntry<String, String>> _safeContextEntries(
  Map<String, dynamic> context,
) {
  const blockedFragments = [
    'account',
    'approval',
    'appkey',
    'app_key',
    'secret',
    'token',
  ];
  final entries = <MapEntry<String, String>>[];
  for (final entry in context.entries) {
    final key = entry.key.trim();
    if (key.isEmpty) continue;
    final normalized = key.toLowerCase();
    if (blockedFragments.any(normalized.contains)) continue;
    final value = entry.value;
    if (value is Map || value is List) continue;
    final text = value?.toString().trim() ?? '';
    if (text.isEmpty || text == 'null') continue;
    entries.add(MapEntry(key, text));
  }
  return entries.take(8).toList(growable: false);
}
