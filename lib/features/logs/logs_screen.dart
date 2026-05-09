import 'package:flutter/material.dart';

import '../../core/utils/timestamp_formatter.dart';
import '../../core/widgets/status_badge.dart';
import '../../models/log_items.dart';
import '../dashboard/dashboard_controller.dart';

class LogsScreen extends StatefulWidget {
  const LogsScreen({super.key, required this.controller});

  final DashboardController controller;

  @override
  State<LogsScreen> createState() => _LogsScreenState();
}

class _LogsScreenState extends State<LogsScreen> {
  int _section = 0;
  bool _loading = true;
  String? _error;
  List<TradingLogItem> _runs = const [];
  List<OrderLogItem> _orders = const [];
  List<SignalLogItem> _signals = const [];
  LogsSummary? _summary;

  @override
  void initState() {
    super.initState();
    _loadLogs();
  }

  Future<void> _loadLogs() async {
    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final results = await Future.wait([
        widget.controller.apiClient.fetchRecentRuns(limit: 50),
        widget.controller.apiClient.fetchRecentOrders(limit: 50),
        widget.controller.apiClient.fetchRecentSignals(limit: 50),
        widget.controller.apiClient.fetchLogsSummary(),
      ]);

      if (!mounted) return;
      setState(() {
        _runs = results[0] as List<TradingLogItem>;
        _orders = results[1] as List<OrderLogItem>;
        _signals = results[2] as List<SignalLogItem>;
        _summary = results[3] as LogsSummary;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
      });
    } finally {
      if (!mounted) return;
      setState(() {
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: RefreshIndicator(
        onRefresh: _loadLogs,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Row(
              children: [
                const Expanded(
                  child: Text(
                    'Logs',
                    style: TextStyle(fontSize: 28, fontWeight: FontWeight.w700),
                  ),
                ),
                IconButton(
                  tooltip: 'Refresh logs',
                  onPressed: _loading ? null : _loadLogs,
                  icon: const Icon(Icons.refresh),
                ),
              ],
            ),
            const SizedBox(height: 12),
            _SummaryStrip(summary: _summary),
            const SizedBox(height: 14),
            SegmentedButton<int>(
              segments: const [
                ButtonSegment(value: 0, label: Text('Runs')),
                ButtonSegment(value: 1, label: Text('Orders')),
                ButtonSegment(value: 2, label: Text('Signals')),
              ],
              selected: {_section},
              onSelectionChanged: (value) =>
                  setState(() => _section = value.first),
            ),
            const SizedBox(height: 14),
            if (_loading) const _LoadingState(),
            if (!_loading && _error != null)
              _StatePanel(
                icon: Icons.cloud_off_outlined,
                title: 'Unable to load live logs',
                body: _error!,
                actionLabel: 'Retry',
                onAction: _loadLogs,
              ),
            if (!_loading && _error == null) ..._sectionWidgets(),
          ],
        ),
      ),
    );
  }

  List<Widget> _sectionWidgets() {
    if (_section == 0) {
      if (_runs.isEmpty) {
        return const [
          _StatePanel(
            icon: Icons.receipt_long_outlined,
            title: 'No runs yet',
            body: 'Manual, scheduler, and watchlist runs will appear here.',
          ),
        ];
      }
      return _runs.map((run) => _RunHistoryCard(run: run)).toList();
    }

    if (_section == 1) {
      if (_orders.isEmpty) {
        return const [
          _StatePanel(
            icon: Icons.inventory_2_outlined,
            title: 'No orders created',
            body:
                'HOLD and skipped decisions are expected to leave this empty.',
          ),
        ];
      }
      return _orders.map((order) => _OrderHistoryCard(order: order)).toList();
    }

    if (_signals.isEmpty) {
      return const [
        _StatePanel(
          icon: Icons.query_stats_outlined,
          title: 'No signals yet',
          body: 'Signal decisions will appear after analysis or trading runs.',
        ),
      ];
    }
    return _signals
        .map((signal) => _SignalHistoryCard(signal: signal))
        .toList();
  }
}

class _SummaryStrip extends StatelessWidget {
  const _SummaryStrip({required this.summary});

  final LogsSummary? summary;

  @override
  Widget build(BuildContext context) {
    final counts = summary?.counts ?? const <String, int>{};
    return Row(
      children: [
        Expanded(child: _CountTile(label: 'Runs', value: counts['runs'] ?? 0)),
        const SizedBox(width: 8),
        Expanded(
            child: _CountTile(label: 'Orders', value: counts['orders'] ?? 0)),
        const SizedBox(width: 8),
        Expanded(
            child: _CountTile(label: 'Signals', value: counts['signals'] ?? 0)),
      ],
    );
  }
}

class _CountTile extends StatelessWidget {
  const _CountTile({required this.label, required this.value});

  final String label;
  final int value;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
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
            '$value',
            style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700),
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
    final unique = <String>[];
    for (final label in labels) {
      final text = label.trim();
      if (text.isNotEmpty && !unique.contains(text)) unique.add(text);
    }
    if (unique.isEmpty) return const SizedBox.shrink();
    return Wrap(
      spacing: 6,
      runSpacing: 6,
      children: [
        for (final label in unique) _SafetyChip(label: label),
      ],
    );
  }
}

class _SafetyChip extends StatelessWidget {
  const _SafetyChip({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    final alert = label == 'REAL ORDER SUBMITTED';
    final color = alert
        ? Colors.redAccent
        : label == 'ALPACA PAPER'
            ? Colors.lightBlueAccent
            : Colors.greenAccent;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.35)),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: color,
          fontSize: 11,
          fontWeight: FontWeight.w700,
          letterSpacing: 0,
        ),
      ),
    );
  }
}

class _RunHistoryCard extends StatelessWidget {
  const _RunHistoryCard({required this.run});

  final TradingLogItem run;

  @override
  Widget build(BuildContext context) {
    final blocked = !run.hasOrder && run.result.toLowerCase() != 'executed';
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _HistoryHeader(
              title: '${run.symbol} - ${run.statusLine}',
              subtitle:
                  '${run.provider.toUpperCase()} / ${run.market.toUpperCase()} / ${run.triggerSource} / ${run.mode}',
              badge: StatusBadge(
                text: run.result,
                active: run.result.toLowerCase() == 'executed',
                alert: false,
              ),
            ),
            const SizedBox(height: 8),
            _BadgeWrap(labels: [run.sourceLabel, ...run.safetyBadges]),
            const SizedBox(height: 10),
            _DetailRow(
              label: 'Time',
              value: formatTimestampWithKst(run.createdAt),
            ),
            _DetailRow(label: 'Gate', value: _formatGate(run.gateLevel)),
            _DetailRow(label: 'Action', value: _fallback(run.action, 'hold')),
            _DetailRow(label: 'Result', value: _fallback(run.result, '-')),
            _DetailRow(label: 'Reason', value: _fallback(run.reason, 'none')),
            _DetailRow(label: 'Order ID', value: run.orderLabel),
            if (run.signalId != null)
              _DetailRow(label: 'Signal ID', value: run.signalId!),
            ..._safetyFlagRows(
              previewOnly: run.isKisPreview ? run.previewOnly : null,
              realOrderSubmitted: run.realOrderSubmitted,
              brokerSubmitCalled: run.brokerSubmitCalled,
              manualSubmitCalled: run.manualSubmitCalled,
              forceDryRunAutoFlags: run.isKisDryRunAuto,
              forcePreviewFlags: run.isKisPreview,
            ),
            if (run.riskFlags.isNotEmpty)
              _DetailRow(label: 'Risk flags', value: run.riskFlags.join(', ')),
            if (run.gatingNotes.isNotEmpty)
              _DetailRow(label: 'Gates', value: _compactText(run.gatingNotes)),
            if (blocked)
              const Padding(
                padding: EdgeInsets.only(top: 8),
                child: Text(
                  'No trade trigger. This is a valid conservative outcome.',
                  style: TextStyle(color: Colors.white70),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _OrderHistoryCard extends StatelessWidget {
  const _OrderHistoryCard({required this.order});

  final OrderLogItem order;

  @override
  Widget build(BuildContext context) {
    final filled = order.statusLabel.toLowerCase().contains('filled');
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _HistoryHeader(
              title: '${order.symbol} - ${order.side.toUpperCase()}',
              subtitle:
                  '${order.provider.toUpperCase()} / ${order.market.toUpperCase()} / ${order.mode}',
              badge: StatusBadge(
                text: order.statusLabel,
                active: filled,
                alert: !filled && order.statusLabel.toLowerCase() == 'failed',
              ),
            ),
            const SizedBox(height: 8),
            _BadgeWrap(labels: [order.sourceLabel, ...order.safetyBadges]),
            const SizedBox(height: 10),
            _DetailRow(
                label: 'Time', value: formatTimestampWithKst(order.createdAt)),
            _DetailRow(
                label: 'Action', value: _fallback(order.action, order.side)),
            _DetailRow(
                label: 'Result',
                value: _fallback(order.result, order.internalStatus)),
            _DetailRow(label: 'Reason', value: _fallback(order.reason, 'none')),
            _DetailRow(label: 'Qty', value: _numberLabel(order.qty)),
            _DetailRow(label: 'Notional', value: _moneyLabel(order.notional)),
            _DetailRow(
                label: 'Order ID', value: '${order.orderId ?? order.id}'),
            _DetailRow(label: 'Broker ID', value: order.orderLabel),
            if (order.signalId != null)
              _DetailRow(label: 'Signal ID', value: order.signalId!),
            if (order.brokerOrderStatus != null)
              _DetailRow(label: 'Broker', value: order.brokerOrderStatus!),
            _DetailRow(label: 'Internal', value: order.internalStatus),
            _DetailRow(
                label: 'Updated',
                value: formatTimestampWithKst(order.updatedAt)),
            ..._safetyFlagRows(
              previewOnly: order.isKisPreview ? order.previewOnly : null,
              realOrderSubmitted: order.realOrderSubmitted,
              brokerSubmitCalled: order.brokerSubmitCalled,
              manualSubmitCalled: order.manualSubmitCalled,
              forceDryRunAutoFlags: order.isKisDryRunAuto,
              forcePreviewFlags: order.isKisPreview,
            ),
            if (order.riskFlags.isNotEmpty)
              _DetailRow(
                  label: 'Risk flags', value: order.riskFlags.join(', ')),
            if (order.gatingNotes.isNotEmpty)
              _DetailRow(
                  label: 'Gates', value: _compactText(order.gatingNotes)),
          ],
        ),
      ),
    );
  }
}

class _SignalHistoryCard extends StatelessWidget {
  const _SignalHistoryCard({required this.signal});

  final SignalLogItem signal;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _HistoryHeader(
              title: '${signal.symbol} - ${signal.statusLine}',
              subtitle:
                  '${signal.provider.toUpperCase()} / ${signal.market.toUpperCase()} / ${signal.triggerSource}',
              badge: StatusBadge(
                text: signal.signalStatus,
                active: signal.signalStatus.toLowerCase() == 'executed',
                alert: false,
              ),
            ),
            const SizedBox(height: 8),
            _BadgeWrap(labels: [signal.sourceLabel, ...signal.safetyBadges]),
            const SizedBox(height: 10),
            _DetailRow(
                label: 'Time', value: formatTimestampWithKst(signal.createdAt)),
            _DetailRow(
                label: 'Action', value: _fallback(signal.action, 'hold')),
            _DetailRow(
                label: 'Result',
                value: _fallback(signal.result, signal.signalStatus)),
            _DetailRow(
                label: 'Reason', value: _fallback(signal.reason, 'none')),
            _DetailRow(
                label: 'Buy score', value: _numberLabel(signal.buyScore)),
            _DetailRow(
                label: 'Sell score', value: _numberLabel(signal.sellScore)),
            _DetailRow(
                label: 'Confidence', value: _numberLabel(signal.confidence)),
            _DetailRow(label: 'Order ID', value: signal.orderLabel),
            ..._safetyFlagRows(
              previewOnly: signal.isKisPreview ? signal.previewOnly : null,
              realOrderSubmitted: signal.realOrderSubmitted,
              brokerSubmitCalled: signal.brokerSubmitCalled,
              manualSubmitCalled: signal.manualSubmitCalled,
              forceDryRunAutoFlags: signal.isKisDryRunAuto,
              forcePreviewFlags: signal.isKisPreview,
            ),
            if (signal.riskFlags.isNotEmpty)
              _DetailRow(
                  label: 'Risk flags', value: signal.riskFlags.join(', ')),
            if (signal.gatingNotes.isNotEmpty)
              _DetailRow(
                  label: 'Gates', value: _compactText(signal.gatingNotes)),
          ],
        ),
      ),
    );
  }
}

class _HistoryHeader extends StatelessWidget {
  const _HistoryHeader({
    required this.title,
    required this.subtitle,
    required this.badge,
  });

  final String title;
  final String subtitle;
  final Widget badge;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title,
                  style: const TextStyle(
                      fontSize: 16, fontWeight: FontWeight.w700)),
              const SizedBox(height: 4),
              Text(subtitle, style: const TextStyle(color: Colors.white60)),
            ],
          ),
        ),
        const SizedBox(width: 12),
        badge,
      ],
    );
  }
}

class _DetailRow extends StatelessWidget {
  const _DetailRow({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 5),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 92,
            child: Text(label, style: const TextStyle(color: Colors.white54)),
          ),
          Expanded(child: Text(value)),
        ],
      ),
    );
  }
}

class _LoadingState extends StatelessWidget {
  const _LoadingState();

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.symmetric(vertical: 36),
      child: Center(child: CircularProgressIndicator()),
    );
  }
}

class _StatePanel extends StatelessWidget {
  const _StatePanel({
    required this.icon,
    required this.title,
    required this.body,
    this.actionLabel,
    this.onAction,
  });

  final IconData icon;
  final String title;
  final String body;
  final String? actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          children: [
            Icon(icon, size: 34, color: Colors.white54),
            const SizedBox(height: 10),
            Text(title,
                style:
                    const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
            const SizedBox(height: 6),
            Text(body,
                textAlign: TextAlign.center,
                style: const TextStyle(color: Colors.white70)),
            if (actionLabel != null && onAction != null) ...[
              const SizedBox(height: 12),
              OutlinedButton.icon(
                onPressed: onAction,
                icon: const Icon(Icons.refresh),
                label: Text(actionLabel!),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

String _formatGate(int gateLevel) {
  if (gateLevel <= 0) return 'Gate unknown';
  return 'Gate $gateLevel';
}

String _fallback(String value, String fallback) {
  return value.isEmpty ? fallback : value;
}

String _numberLabel(num? value) {
  if (value == null) return '-';
  return value.toStringAsFixed(value % 1 == 0 ? 0 : 2);
}

String _moneyLabel(num? value) {
  if (value == null) return '-';
  return '\$${value.toStringAsFixed(2)}';
}

List<Widget> _safetyFlagRows({
  bool? previewOnly,
  bool? realOrderSubmitted,
  bool? brokerSubmitCalled,
  bool? manualSubmitCalled,
  bool forceDryRunAutoFlags = false,
  bool forcePreviewFlags = false,
}) {
  final rows = <Widget>[];
  if (forcePreviewFlags || previewOnly != null) {
    rows.add(_DetailRow(
      label: 'Safety',
      value: 'preview_only=${_boolLabel(previewOnly ?? true)}',
    ));
  }
  if (forceDryRunAutoFlags || forcePreviewFlags || realOrderSubmitted != null) {
    rows.add(_DetailRow(
      label: 'Safety',
      value: 'real_order_submitted=${_boolLabel(realOrderSubmitted ?? false)}',
    ));
  }
  if (forceDryRunAutoFlags || brokerSubmitCalled != null) {
    rows.add(_DetailRow(
      label: 'Safety',
      value: 'broker_submit_called=${_boolLabel(brokerSubmitCalled ?? false)}',
    ));
  }
  if (forceDryRunAutoFlags || manualSubmitCalled != null) {
    rows.add(_DetailRow(
      label: 'Safety',
      value: 'manual_submit_called=${_boolLabel(manualSubmitCalled ?? false)}',
    ));
  }
  return rows;
}

String _boolLabel(bool value) => value ? 'true' : 'false';

String _compactText(List<String> values) {
  final text = values.join(' | ');
  if (text.length <= 180) return text;
  return '${text.substring(0, 177)}...';
}
