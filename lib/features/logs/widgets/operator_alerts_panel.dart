import 'package:flutter/material.dart';

import '../../../core/i18n/app_strings.dart';
import '../../../core/utils/timestamp_formatter.dart';
import '../../../models/operator_alerts.dart';
import '../../dashboard/dashboard_controller.dart';

class OperatorAlertsPanel extends StatelessWidget {
  const OperatorAlertsPanel({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final strings = controller.strings;
        final alerts = controller.operatorAlerts;
        final loading = controller.operatorAlertsLoading;
        return Container(
          key: const ValueKey('operator-alerts-panel'),
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
                  const Icon(Icons.notification_important_outlined,
                      color: Colors.orangeAccent, size: 20),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          strings.operatorAlertCenter,
                          style: const TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w900,
                          ),
                        ),
                        const SizedBox(height: 3),
                        Text(
                          alerts == null
                              ? strings.statusNotLoaded
                              : '${strings.brokerName(alerts.provider)} / ${alerts.market} / ${_timestamp(alerts.generatedAt)}',
                          key: const ValueKey('operator-alerts-runtime-status'),
                          style: const TextStyle(color: Colors.white70),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    key: const ValueKey('operator-alerts-refresh-button'),
                    tooltip: strings.refreshAlerts,
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
              _BadgeWrap(labels: _badges(strings, alerts)),
              if (controller.operatorAlertsError != null) ...[
                const SizedBox(height: 10),
                Text(
                  controller.operatorAlertsError!,
                  style: const TextStyle(color: Colors.orangeAccent),
                ),
              ],
              if (loading && alerts == null) ...[
                const SizedBox(height: 12),
                const LinearProgressIndicator(),
              ],
              const SizedBox(height: 12),
              if (alerts == null)
                _EmptyLine(text: strings.statusNotLoaded)
              else ...[
                Container(
                  key: const ValueKey('operator-alerts-summary-cards'),
                  child: _SummaryGrid(alerts: alerts, strings: strings),
                ),
                const SizedBox(height: 12),
                _AlertList(alerts: alerts, strings: strings),
              ],
            ],
          ),
        );
      },
    );
  }

  List<String> _badges(AppStrings strings, OperatorAlerts? alerts) {
    final labels = <String>[
      strings.operatorReadOnly,
      strings.operatorNoLiveOrders,
      strings.schedulerDryRunOnly,
      strings.localDbOnly,
      strings.noSync,
      strings.noRetry,
      strings.noBrokerSubmit,
      strings.noSettingsChange,
    ];
    if (alerts?.safetyFlags['validation_called'] == false) {
      labels.add(strings.noValidation);
    }
    return labels;
  }

  Future<void> _refresh(
    BuildContext context, {
    required bool showSnack,
  }) async {
    final result = await controller.refreshOperatorAlerts();
    if (!context.mounted || !showSnack) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(result.message)),
    );
  }
}

class _SummaryGrid extends StatelessWidget {
  const _SummaryGrid({required this.alerts, required this.strings});

  final OperatorAlerts alerts;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    final summary = alerts.summary;
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        _MetricTile(
          label: strings.critical,
          value: '${summary.criticalCount}',
          valueColor:
              summary.criticalCount > 0 ? Colors.redAccent : Colors.greenAccent,
        ),
        _MetricTile(
          label: strings.warning,
          value: '${summary.warningCount}',
          valueColor: summary.warningCount > 0
              ? Colors.orangeAccent
              : Colors.greenAccent,
        ),
        _MetricTile(
          label: strings.syncRequired,
          value: '${summary.syncRequiredCount}',
          valueColor: summary.syncRequiredCount > 0
              ? Colors.orangeAccent
              : Colors.greenAccent,
        ),
        _MetricTile(
          label: strings.rejectedOrder,
          value: '${summary.rejectedOrderCount}',
          valueColor: summary.rejectedOrderCount > 0
              ? Colors.orangeAccent
              : Colors.greenAccent,
        ),
      ],
    );
  }
}

class _AlertList extends StatelessWidget {
  const _AlertList({required this.alerts, required this.strings});

  final OperatorAlerts alerts;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    if (alerts.alerts.isEmpty) {
      return _EmptyLine(text: strings.noOperatorAlerts);
    }
    return Column(
      key: const ValueKey('operator-alerts-list'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          strings.riskAlerts,
          style: const TextStyle(fontWeight: FontWeight.w900),
        ),
        const SizedBox(height: 8),
        for (final alert in alerts.alerts)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: _AlertTile(alert: alert, strings: strings),
          ),
        if (alerts.nextSafeActions.isNotEmpty) ...[
          const SizedBox(height: 4),
          Text(
            strings.nextSafeActions,
            style: const TextStyle(fontWeight: FontWeight.w900),
          ),
          const SizedBox(height: 4),
          for (final action in alerts.nextSafeActions.take(4))
            Padding(
              padding: const EdgeInsets.only(bottom: 3),
              child: Text(
                action,
                style: const TextStyle(color: Colors.white70, height: 1.25),
              ),
            ),
        ],
      ],
    );
  }
}

class _AlertTile extends StatelessWidget {
  const _AlertTile({required this.alert, required this.strings});

  final OperatorAlert alert;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    final color = _severityColor(alert.severity);
    final related = [
      alert.relatedType,
      if (alert.relatedId != null) alert.relatedId,
    ].join(' #');
    return Container(
      key: ValueKey('operator-alert-${alert.alertId}'),
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.35)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _StatusPill(
                label: _severityLabel(alert.severity, strings), color: color),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                strings.statusLabel(alert.category),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  color: Colors.white60,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 8),
        Text(
          alert.title,
          style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w900),
        ),
        const SizedBox(height: 4),
        Text(
          alert.message,
          style: const TextStyle(color: Colors.white70, height: 1.25),
        ),
        const SizedBox(height: 8),
        if (alert.symbol != null)
          _InfoRow(label: strings.symbolLabel, value: alert.symbol!),
        _InfoRow(label: strings.relatedItem, value: related),
        _InfoRow(label: strings.primaryReason, value: alert.reasonCode),
        _InfoRow(label: strings.nextSafeAction, value: alert.nextSafeAction),
        if (alert.riskFlags.isNotEmpty || alert.gatingNotes.isNotEmpty)
          Theme(
            data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
            child: ExpansionTile(
              tilePadding: EdgeInsets.zero,
              childrenPadding: EdgeInsets.zero,
              title: Text(
                strings.detailsLabel,
                style: const TextStyle(fontWeight: FontWeight.w800),
              ),
              children: [
                if (alert.riskFlags.isNotEmpty)
                  _InfoRow(
                    label: strings.riskFlags,
                    value: alert.riskFlags.join(' / '),
                  ),
                if (alert.gatingNotes.isNotEmpty)
                  _InfoRow(
                    label: strings.gatingNotes,
                    value: alert.gatingNotes.join(' / '),
                  ),
                _InfoRow(label: strings.status, value: alert.status),
                _InfoRow(label: strings.action, value: alert.actionType),
                _InfoRow(
                    label: strings.generatedAt,
                    value: _timestamp(alert.updatedAt)),
              ],
            ),
          ),
      ]),
    );
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
            width: 132,
            child: Text(
              label,
              style: const TextStyle(color: Colors.white60),
            ),
          ),
          Expanded(
            child: Text(
              value.trim().isEmpty ? '-' : value,
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

String _severityLabel(String value, AppStrings strings) {
  switch (value.toLowerCase()) {
    case 'critical':
      return strings.critical;
    case 'warning':
      return strings.warning;
    case 'info':
      return strings.info;
  }
  return strings.statusLabel(value);
}

Color _severityColor(String value) {
  switch (value.toLowerCase()) {
    case 'critical':
      return Colors.redAccent;
    case 'warning':
      return Colors.orangeAccent;
    case 'info':
      return Colors.lightBlueAccent;
  }
  return Colors.white70;
}

String _timestamp(DateTime? value) {
  if (value == null) return '-';
  return formatTimestampWithKst(value.toIso8601String());
}
