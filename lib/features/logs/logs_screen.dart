import 'package:flutter/material.dart';

import '../../core/utils/timestamp_formatter.dart';
import '../../core/widgets/gpt_risk_context_view.dart';
import '../../core/widgets/status_badge.dart';
import '../../models/gpt_risk_context.dart';
import '../../models/kis_manual_order_safety_status.dart';
import '../../models/kis_scheduler_simulation.dart';
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
  KisSchedulerSimulationStatus? _kisSchedulerStatus;
  KisManualOrderSafetyStatus? _kisManualSafetyStatus;

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
        widget.controller.apiClient.fetchKisSchedulerStatus(),
        widget.controller.apiClient.fetchKisManualOrderSafetyStatus(),
      ]);

      if (!mounted) return;
      setState(() {
        _runs = results[0] as List<TradingLogItem>;
        _orders = results[1] as List<OrderLogItem>;
        _signals = results[2] as List<SignalLogItem>;
        _summary = results[3] as LogsSummary;
        _kisSchedulerStatus = results[4] as KisSchedulerSimulationStatus;
        _kisManualSafetyStatus = results[5] as KisManualOrderSafetyStatus;
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
            _KisSimulationOpsSummaryCard(
              loading: _loading,
              error: _error,
              runs: _runs,
              orders: _orders,
              signals: _signals,
              schedulerStatus: _kisSchedulerStatus,
              onRetry: _loading ? null : _loadLogs,
            ),
            const SizedBox(height: 14),
            _KisLiveAutomationReadinessCard(
              loading: _loading,
              error: _error,
              runs: _runs,
              orders: _orders,
              signals: _signals,
              schedulerStatus: _kisSchedulerStatus,
              manualSafetyStatus: _kisManualSafetyStatus,
              onRetry: _loading ? null : _loadLogs,
            ),
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

class _KisSimulationOpsSummaryCard extends StatelessWidget {
  const _KisSimulationOpsSummaryCard({
    required this.loading,
    required this.error,
    required this.runs,
    required this.orders,
    required this.signals,
    required this.schedulerStatus,
    required this.onRetry,
  });

  final bool loading;
  final String? error;
  final List<TradingLogItem> runs;
  final List<OrderLogItem> orders;
  final List<SignalLogItem> signals;
  final KisSchedulerSimulationStatus? schedulerStatus;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final summary = _KisSimulationOpsSummary.fromLogs(
      runs: runs,
      orders: orders,
      signals: signals,
    );
    final status =
        schedulerStatus ?? KisSchedulerSimulationStatus.safeDefault();

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.monitor_heart_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text('KIS Simulation Operations Summary',
                style: Theme.of(context).textTheme.titleSmall),
          ),
          IconButton(
            tooltip: 'Refresh KIS simulation summary',
            onPressed: onRetry,
            icon: loading
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.refresh),
          ),
        ]),
        const SizedBox(height: 8),
        const _BadgeWrap(labels: [
          'SIMULATION ONLY',
          'NO BROKER SUBMIT',
          'NOT LIVE AUTOMATION',
        ]),
        const SizedBox(height: 10),
        if (loading)
          const _SummaryStateLine(text: 'Loading KIS simulation summary...')
        else if (error != null)
          _SummaryErrorLine(
            text: 'KIS simulation summary unavailable: ${_primaryLine(error!)}',
            onRetry: onRetry,
          )
        else if (!summary.hasKisActivity)
          const _SummaryStateLine(
            text: 'No KIS scheduler simulation logs for today.',
          )
        else ...[
          _LatestKisSimulationBlock(summary: summary),
          const SizedBox(height: 10),
          _KisSimulationCountBlock(summary: summary),
          const SizedBox(height: 10),
          _KisSimulationSafetyBlock(status: status, summary: summary),
          const SizedBox(height: 10),
          _KisSimulationReasonBlock(summary: summary),
          const SizedBox(height: 8),
          Text(
            'Manual live records are separate from scheduler simulation records.',
            style: TextStyle(color: Colors.white.withValues(alpha: 0.70)),
          ),
        ],
      ]),
    );
  }
}

class _KisLiveAutomationReadinessCard extends StatelessWidget {
  const _KisLiveAutomationReadinessCard({
    required this.loading,
    required this.error,
    required this.runs,
    required this.orders,
    required this.signals,
    required this.schedulerStatus,
    required this.manualSafetyStatus,
    required this.onRetry,
  });

  final bool loading;
  final String? error;
  final List<TradingLogItem> runs;
  final List<OrderLogItem> orders;
  final List<SignalLogItem> signals;
  final KisSchedulerSimulationStatus? schedulerStatus;
  final KisManualOrderSafetyStatus? manualSafetyStatus;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final summary = _KisSimulationOpsSummary.fromLogs(
      runs: runs,
      orders: orders,
      signals: signals,
    );
    final checks = _readinessChecks(
      summary: summary,
      allLogsAvailable:
          runs.isNotEmpty || orders.isNotEmpty || signals.isNotEmpty,
      schedulerStatus: schedulerStatus,
      manualSafetyStatus: manualSafetyStatus,
    );
    final passed = checks.where((check) => check.passed).length;
    final blockers = checks.where((check) => !check.passed).take(5).toList();

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.verified_user_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text('KIS Live Automation Readiness',
                style: Theme.of(context).textTheme.titleSmall),
          ),
          IconButton(
            tooltip: 'Refresh KIS live automation readiness',
            onPressed: onRetry,
            icon: loading
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.refresh),
          ),
        ]),
        const SizedBox(height: 8),
        const _BadgeWrap(labels: [
          'READINESS ONLY',
          'LIVE AUTO DISABLED',
          'NO BROKER SUBMIT',
          'MANUAL APPROVAL REQUIRED',
        ]),
        const SizedBox(height: 10),
        const Text('LIVE AUTO ORDER: NOT ENABLED',
            style: TextStyle(
                color: Colors.redAccent, fontWeight: FontWeight.w800)),
        const SizedBox(height: 8),
        if (loading)
          const _SummaryStateLine(text: 'Loading KIS readiness checks...')
        else if (error != null)
          _SummaryErrorLine(
            text: 'KIS readiness unavailable: ${_primaryLine(error!)}',
            onRetry: onRetry,
          )
        else ...[
          Wrap(spacing: 14, runSpacing: 8, children: [
            _SummaryMetric(
                label: 'ready checks',
                value: '$passed/${checks.length} passed'),
            const _SummaryMetric(label: 'live automation', value: 'BLOCKED'),
            _SummaryMetric(
              label: 'manual live records',
              value: '${summary.manualLiveOrderCount} separate',
            ),
          ]),
          const SizedBox(height: 10),
          if (blockers.isNotEmpty) ...[
            const Text('Blockers',
                style: TextStyle(
                    color: Colors.white54, fontWeight: FontWeight.w700)),
            const SizedBox(height: 6),
            Wrap(spacing: 8, runSpacing: 8, children: [
              for (final blocker in blockers)
                _ReadinessChip(check: blocker, compact: true),
            ]),
            const SizedBox(height: 10),
          ],
          Wrap(spacing: 8, runSpacing: 8, children: [
            for (final check in checks) _ReadinessChip(check: check),
          ]),
          const SizedBox(height: 8),
          Text(
            'Manual live orders are excluded from scheduler automation readiness.',
            style: TextStyle(color: Colors.white.withValues(alpha: 0.70)),
          ),
        ],
      ]),
    );
  }
}

class _ReadinessChip extends StatelessWidget {
  const _ReadinessChip({required this.check, this.compact = false});

  final _ReadinessCheck check;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final color = check.passed ? Colors.greenAccent : Colors.redAccent;
    return Container(
      constraints: BoxConstraints(
        minWidth: compact ? 140 : 180,
        maxWidth: compact ? 280 : 340,
      ),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.30)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(
          '${check.passed ? 'PASS' : 'BLOCKED'}: ${check.label}',
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            color: color,
            fontSize: 11,
            fontWeight: FontWeight.w800,
          ),
        ),
        const SizedBox(height: 3),
        Text(
          check.detail,
          maxLines: compact ? 2 : 3,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(color: Colors.white70, fontSize: 12),
        ),
      ]),
    );
  }
}

class _ReadinessCheck {
  const _ReadinessCheck({
    required this.label,
    required this.detail,
    required this.passed,
  });

  final String label;
  final String detail;
  final bool passed;
}

List<_ReadinessCheck> _readinessChecks({
  required _KisSimulationOpsSummary summary,
  required bool allLogsAvailable,
  required KisSchedulerSimulationStatus? schedulerStatus,
  required KisManualOrderSafetyStatus? manualSafetyStatus,
}) {
  final latest = summary.latestSchedulerRun;
  return [
    _ReadinessCheck(
      label: 'dry_run=false readiness',
      passed: manualSafetyStatus?.hasRuntimeDryRun == true &&
          manualSafetyStatus?.runtimeDryRun == false,
      detail: manualSafetyStatus?.hasRuntimeDryRun == true
          ? 'dry_run is ${manualSafetyStatus!.runtimeDryRun ? 'ON' : 'OFF'}'
          : 'dry_run is unknown',
    ),
    _ReadinessCheck(
      label: 'kill_switch=false',
      passed: manualSafetyStatus?.hasKillSwitch == true &&
          manualSafetyStatus?.killSwitch == false,
      detail: manualSafetyStatus?.hasKillSwitch == true
          ? 'kill_switch=${_boolLabel(manualSafetyStatus!.killSwitch)}'
          : 'kill_switch unknown',
    ),
    _ReadinessCheck(
      label: 'kis_enabled=true',
      passed: manualSafetyStatus?.hasKisEnabled == true &&
          manualSafetyStatus?.kisEnabled == true,
      detail: manualSafetyStatus?.hasKisEnabled == true
          ? 'kis_enabled=${_boolLabel(manualSafetyStatus!.kisEnabled)}'
          : 'kis_enabled unknown',
    ),
    _ReadinessCheck(
      label: 'kis_real_order_enabled=true',
      passed: manualSafetyStatus?.hasKisRealOrderEnabled == true &&
          manualSafetyStatus?.kisRealOrderEnabled == true,
      detail: manualSafetyStatus?.hasKisRealOrderEnabled == true
          ? 'kis_real_order_enabled=${_boolLabel(manualSafetyStatus!.kisRealOrderEnabled)}'
          : 'kis_real_order_enabled unknown',
    ),
    _ReadinessCheck(
      label: 'kis_scheduler_enabled status',
      passed: schedulerStatus?.enabled == true,
      detail: schedulerStatus == null
          ? 'kis_scheduler_enabled unknown'
          : 'kis_scheduler_enabled=${_boolLabel(schedulerStatus.enabled)}',
    ),
    _ReadinessCheck(
      label: 'kis_scheduler_dry_run=true',
      passed: schedulerStatus?.schedulerDryRun == true,
      detail: schedulerStatus?.schedulerDryRun == null
          ? 'kis_scheduler_dry_run unknown'
          : 'kis_scheduler_dry_run=${_boolLabel(schedulerStatus!.schedulerDryRun!)}',
    ),
    _ReadinessCheck(
      label: 'kis_scheduler_allow_real_orders=false',
      passed: schedulerStatus?.configuredAllowRealOrders == false,
      detail: schedulerStatus?.configuredAllowRealOrders == null
          ? 'kis_scheduler_allow_real_orders unknown'
          : 'kis_scheduler_allow_real_orders=${_boolLabel(schedulerStatus!.configuredAllowRealOrders!)}',
    ),
    _ReadinessCheck(
      label: 'real_orders_allowed=false',
      passed:
          schedulerStatus != null && schedulerStatus.realOrdersAllowed == false,
      detail: schedulerStatus == null
          ? 'real_orders_allowed unknown'
          : 'real_orders_allowed=${_boolLabel(schedulerStatus.realOrdersAllowed)}',
    ),
    _ReadinessCheck(
      label: 'live_scheduler_orders_enabled=false',
      passed: schedulerStatus != null &&
          schedulerStatus.realOrderSchedulerEnabled == false,
      detail: schedulerStatus == null
          ? 'live_scheduler_orders_enabled unknown'
          : 'live_scheduler_orders_enabled=${_boolLabel(schedulerStatus.realOrderSchedulerEnabled)}',
    ),
    _ReadinessCheck(
      label: 'recent KIS simulation runs exist',
      passed: summary.schedulerRuns.isNotEmpty,
      detail: summary.schedulerRuns.isEmpty
          ? 'recent simulation missing'
          : '${summary.schedulerRuns.length} scheduler dry-run record(s)',
    ),
    _ReadinessCheck(
      label: 'recent simulation submit flags all false',
      passed: summary.schedulerSubmitFlagsAllFalse,
      detail: summary.schedulerRuns.isEmpty
          ? 'latest submit flags unknown'
          : 'real_order_submitted=${_boolLabel(summary.realOrderSubmitted)}, '
              'broker_submit_called=${_boolLabel(summary.brokerSubmitCalled)}, '
              'manual_submit_called=${_boolLabel(summary.schedulerManualSubmitCalled)}',
    ),
    _ReadinessCheck(
      label: 'recent Logs/History records available',
      passed: allLogsAvailable,
      detail: allLogsAvailable ? 'logs loaded' : 'logs unavailable',
    ),
    _ReadinessCheck(
      label: 'latest scheduler run has clear result/reason',
      passed: latest != null &&
          latest.result.trim().isNotEmpty &&
          latest.reason.trim().isNotEmpty,
      detail: latest == null
          ? 'latest scheduler result missing'
          : 'result=${_fallback(latest.result, "unknown")} / reason=${_fallback(latest.reason, "unknown")}',
    ),
    _ReadinessCheck(
      label: 'latest simulation has no broker id / no kis_odno',
      passed: summary.latestSimulationHasNoBrokerIds,
      detail: summary.latestSimulationHasNoBrokerIds
          ? 'no real broker id or kis_odno on latest simulation'
          : 'real broker id or kis_odno is present or unknown',
    ),
  ];
}

class _LatestKisSimulationBlock extends StatelessWidget {
  const _LatestKisSimulationBlock({required this.summary});

  final _KisSimulationOpsSummary summary;

  @override
  Widget build(BuildContext context) {
    final latest = summary.latestSchedulerRun;
    if (latest == null) {
      return const _SummaryStateLine(
        text: 'No scheduler dry-run result has been recorded today.',
      );
    }

    return Wrap(spacing: 14, runSpacing: 8, children: [
      _SummaryMetric(
        label: 'last run',
        value: formatTimestampWithKst(latest.createdAt),
      ),
      _SummaryMetric(
          label: 'last action', value: _fallback(latest.action, '-')),
      _SummaryMetric(
          label: 'last result', value: _fallback(latest.result, '-')),
      _SummaryMetric(
          label: 'last reason', value: _fallback(latest.reason, '-')),
      _SummaryMetric(label: 'symbol', value: _fallback(latest.symbol, '-')),
      _SummaryMetric(label: 'signal_id', value: latest.signalId ?? 'n/a'),
      _SummaryMetric(label: 'order_id', value: latest.orderLabel),
      _SummaryMetric(
        label: 'sim notional',
        value: summary.latestSimulatedNotionalLabel,
      ),
    ]);
  }
}

class _KisSimulationCountBlock extends StatelessWidget {
  const _KisSimulationCountBlock({required this.summary});

  final _KisSimulationOpsSummary summary;

  @override
  Widget build(BuildContext context) {
    return Wrap(spacing: 8, runSpacing: 8, children: [
      _MiniCount(label: 'Scheduler runs', value: summary.schedulerRuns.length),
      _MiniCount(label: 'Sim buys', value: summary.simulatedBuyCount),
      _MiniCount(label: 'Sim sells', value: summary.simulatedSellCount),
      _MiniCount(label: 'Hold/skipped', value: summary.holdSkippedCount),
      _MiniCount(label: 'Preview-only', value: summary.previewOnlyCount),
      _MiniCount(label: 'Manual live', value: summary.manualLiveOrderCount),
    ]);
  }
}

class _KisSimulationSafetyBlock extends StatelessWidget {
  const _KisSimulationSafetyBlock({
    required this.status,
    required this.summary,
  });

  final KisSchedulerSimulationStatus status;
  final _KisSimulationOpsSummary summary;

  @override
  Widget build(BuildContext context) {
    return Wrap(spacing: 14, runSpacing: 8, children: [
      _SafetyChip(
        label:
            'real_order_submitted=${_boolLabel(summary.realOrderSubmitted || status.realOrderSubmitted)}',
      ),
      _SafetyChip(
        label:
            'broker_submit_called=${_boolLabel(summary.brokerSubmitCalled || status.brokerSubmitCalled)}',
      ),
      _SafetyChip(
        label:
            'manual_submit_called=${_boolLabel(summary.schedulerManualSubmitCalled || status.manualSubmitCalled)}',
      ),
      _SafetyChip(
        label: 'real_orders_allowed=${_boolLabel(status.realOrdersAllowed)}',
      ),
      _SafetyChip(
        label:
            'live_scheduler=${status.realOrderSchedulerEnabled ? "enabled" : "disabled"}',
      ),
    ]);
  }
}

class _KisSimulationReasonBlock extends StatelessWidget {
  const _KisSimulationReasonBlock({required this.summary});

  final _KisSimulationOpsSummary summary;

  @override
  Widget build(BuildContext context) {
    final reasons = summary.topReasons;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Top recent block/risk reasons',
          style: TextStyle(color: Colors.white54, fontWeight: FontWeight.w700)),
      const SizedBox(height: 6),
      if (reasons.isEmpty)
        const Text('n/a', style: TextStyle(color: Colors.white70))
      else
        Wrap(spacing: 8, runSpacing: 8, children: [
          for (final reason in reasons)
            _SafetyChip(label: '${reason.key} x${reason.value}'),
        ]),
    ]);
  }
}

class _SummaryMetric extends StatelessWidget {
  const _SummaryMetric({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return ConstrainedBox(
      constraints: const BoxConstraints(minWidth: 124, maxWidth: 240),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label.toUpperCase(),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
                color: Colors.white38,
                fontSize: 10,
                fontWeight: FontWeight.w700)),
        const SizedBox(height: 3),
        Text(value,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
                color: Colors.white70, fontWeight: FontWeight.w700)),
      ]),
    );
  }
}

class _MiniCount extends StatelessWidget {
  const _MiniCount({required this.label, required this.value});

  final String label;
  final int value;

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(minWidth: 112),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 9),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label,
            style: const TextStyle(color: Colors.white54, fontSize: 11)),
        const SizedBox(height: 3),
        Text('$value',
            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800)),
      ]),
    );
  }
}

class _SummaryStateLine extends StatelessWidget {
  const _SummaryStateLine({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(text, style: const TextStyle(color: Colors.white70));
  }
}

class _SummaryErrorLine extends StatelessWidget {
  const _SummaryErrorLine({required this.text, required this.onRetry});

  final String text;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 8,
      runSpacing: 6,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        Text(text, style: const TextStyle(color: Colors.redAccent)),
        TextButton.icon(
          onPressed: onRetry,
          icon: const Icon(Icons.refresh, size: 16),
          label: const Text('Retry'),
        ),
      ],
    );
  }
}

class _KisSimulationOpsSummary {
  const _KisSimulationOpsSummary({
    required this.schedulerRuns,
    required this.kisOrders,
    required this.kisSignals,
    required this.previewOnlyCount,
    required this.manualLiveOrderCount,
    required this.topReasons,
  });

  final List<TradingLogItem> schedulerRuns;
  final List<OrderLogItem> kisOrders;
  final List<SignalLogItem> kisSignals;
  final int previewOnlyCount;
  final int manualLiveOrderCount;
  final List<MapEntry<String, int>> topReasons;

  bool get hasKisActivity =>
      schedulerRuns.isNotEmpty || kisOrders.isNotEmpty || kisSignals.isNotEmpty;

  TradingLogItem? get latestSchedulerRun =>
      schedulerRuns.isEmpty ? null : schedulerRuns.first;

  int get simulatedBuyCount =>
      schedulerRuns.where((run) => run.action.toLowerCase() == 'buy').length;

  int get simulatedSellCount =>
      schedulerRuns.where((run) => run.action.toLowerCase() == 'sell').length;

  int get holdSkippedCount => schedulerRuns.where((run) {
        final action = run.action.toLowerCase();
        final result = run.result.toLowerCase();
        return action == 'hold' ||
            result == 'skipped' ||
            result.contains('skipped') ||
            result.contains('blocked');
      }).length;

  bool get realOrderSubmitted =>
      schedulerRuns.any((run) => run.realOrderSubmitted == true);

  bool get brokerSubmitCalled =>
      schedulerRuns.any((run) => run.brokerSubmitCalled == true);

  bool get schedulerManualSubmitCalled =>
      schedulerRuns.any((run) => run.manualSubmitCalled == true);

  bool get schedulerSubmitFlagsAllFalse =>
      schedulerRuns.isNotEmpty &&
      schedulerRuns.every((run) =>
          run.realOrderSubmitted == false &&
          run.brokerSubmitCalled == false &&
          run.manualSubmitCalled == false);

  bool get latestSimulationHasNoBrokerIds {
    final order = latestSchedulerOrder;
    if (order == null) return schedulerRuns.isNotEmpty;
    return order.brokerOrderId == null && order.kisOdno == null;
  }

  OrderLogItem? get latestSchedulerOrder {
    for (final order in kisOrders) {
      if (order.isKisDryRunAuto) return order;
    }
    return null;
  }

  String get latestSimulatedNotionalLabel {
    final order = latestSchedulerOrder;
    if (order == null) return 'n/a';
    return _moneyLabel(
      order.notional,
      provider: order.provider,
      market: order.market,
      currency: order.currency,
    );
  }

  factory _KisSimulationOpsSummary.fromLogs({
    required List<TradingLogItem> runs,
    required List<OrderLogItem> orders,
    required List<SignalLogItem> signals,
  }) {
    final today = _todayKstStamp();
    final todayRuns =
        runs.where((run) => _isSameKstDay(run.createdAt, today)).toList();
    final todayOrders =
        orders.where((order) => _isSameKstDay(order.createdAt, today)).toList();
    final todaySignals = signals
        .where((signal) => _isSameKstDay(signal.createdAt, today))
        .toList();
    final schedulerRuns = todayRuns
        .where(_isKisSchedulerDryRun)
        .toList(growable: false)
      ..sort((a, b) => _compareTimestampsDesc(a.createdAt, b.createdAt));
    final kisOrders = todayOrders
        .where((order) => order.isKis)
        .toList(growable: false)
      ..sort((a, b) => _compareTimestampsDesc(a.createdAt, b.createdAt));
    final kisSignals = todaySignals
        .where((signal) => signal.isKis)
        .toList(growable: false)
      ..sort((a, b) => _compareTimestampsDesc(a.createdAt, b.createdAt));
    final previewOnlyCount = todayRuns.where((run) => run.isKisPreview).length;
    final manualLiveOrderCount =
        kisOrders.where((order) => order.isKisManualLive).length;

    return _KisSimulationOpsSummary(
      schedulerRuns: schedulerRuns,
      kisOrders: kisOrders,
      kisSignals: kisSignals,
      previewOnlyCount: previewOnlyCount,
      manualLiveOrderCount: manualLiveOrderCount,
      topReasons: _topReasons(
        runs: schedulerRuns,
        orders: kisOrders,
        signals: kisSignals,
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
            if (run.exitTrigger != null)
              _DetailRow(label: 'Trigger', value: run.exitTrigger!),
            if (run.exitTriggerSource != null)
              _DetailRow(label: 'Trigger src', value: run.exitTriggerSource!),
            if (run.suggestedQuantity != null)
              _DetailRow(
                  label: 'Suggested qty',
                  value: _numberLabel(run.suggestedQuantity)),
            if (run.currentPrice != null)
              _DetailRow(
                label: 'Current price',
                value: _moneyLabel(
                  run.currentPrice,
                  provider: run.provider,
                  market: run.market,
                  currency: run.market.toUpperCase() == 'KR' ? 'KRW' : 'USD',
                ),
              ),
            if (run.costBasis != null)
              _DetailRow(
                label: 'Cost basis',
                value: _moneyLabel(
                  run.costBasis,
                  provider: run.provider,
                  market: run.market,
                  currency: run.market.toUpperCase() == 'KR' ? 'KRW' : 'USD',
                ),
              ),
            if (run.unrealizedPl != null)
              _DetailRow(
                label: 'Unrealized P/L',
                value: _moneyLabel(
                  run.unrealizedPl,
                  provider: run.provider,
                  market: run.market,
                  currency: run.market.toUpperCase() == 'KR' ? 'KRW' : 'USD',
                ),
              ),
            if (run.unrealizedPlPct != null)
              _DetailRow(
                label: 'Unrealized P/L %',
                value: _percentFromDecimal(run.unrealizedPlPct),
              ),
            if (run.gptContext.hasDetails)
              _GptLogContextBlock(context: run.gptContext),
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
            if (order.gptContext.hasDetails)
              _GptLogContextBlock(context: order.gptContext),
            _DetailRow(label: 'Qty', value: _numberLabel(order.qty)),
            _DetailRow(
              label: 'Notional',
              value: _moneyLabel(
                order.notional,
                provider: order.provider,
                market: order.market,
                currency: order.currency,
              ),
            ),
            _DetailRow(
                label: 'Order ID', value: '${order.orderId ?? order.id}'),
            _DetailRow(label: 'Broker ID', value: order.orderLabel),
            if (order.isFromExitPreflight)
              const _DetailRow(
                  label: 'Source', value: 'Prepared from exit preflight'),
            if (order.exitTrigger != null)
              _DetailRow(label: 'Trigger', value: order.exitTrigger!),
            if (order.exitTriggerSource != null)
              _DetailRow(label: 'Trigger src', value: order.exitTriggerSource!),
            if (order.filledQuantity != null)
              _DetailRow(
                  label: 'Filled qty',
                  value: _numberLabel(order.filledQuantity)),
            if (order.remainingQuantity != null)
              _DetailRow(
                  label: 'Remaining',
                  value: _numberLabel(order.remainingQuantity)),
            if (order.averageFillPrice != null)
              _DetailRow(
                label: 'Avg fill',
                value: _moneyLabel(
                  order.averageFillPrice,
                  provider: order.provider,
                  market: order.market,
                  currency: order.currency,
                ),
              ),
            if (order.rejectedReason != null)
              _DetailRow(label: 'Rejected', value: order.rejectedReason!),
            if (order.lastSyncedAt != null)
              _DetailRow(
                  label: 'Last sync',
                  value: formatTimestampWithKst(order.lastSyncedAt!)),
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
            if (signal.gptContext.hasDetails)
              _GptLogContextBlock(context: signal.gptContext),
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

class _GptLogContextBlock extends StatelessWidget {
  const _GptLogContextBlock({required this.context});

  final GptRiskContext context;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        GptRiskContextSummaryBadges(context: this.context, compact: true),
        _DetailRow(
          label: 'GPT Risk',
          value: this.context.marketRiskRegime ??
              this.context.eventRiskLevel ??
              'n/a',
        ),
        _DetailRow(
          label: 'Entry penalty',
          value: this.context.entryPenalty?.toString() ?? 'n/a',
        ),
        _DetailRow(
          label: 'New Buy Blocked',
          value: this.context.hardBlockNewBuy ? 'true' : 'false',
        ),
        if (this.context.reason?.isNotEmpty == true)
          _DetailRow(label: 'GPT reason', value: this.context.reason!),
        if (this.context.riskFlags.isNotEmpty)
          _DetailRow(
            label: 'GPT flags',
            value: this.context.riskFlags.join(', '),
          ),
        if (this.context.gatingNotes.isNotEmpty)
          _DetailRow(
            label: 'GPT gates',
            value: _compactText(this.context.gatingNotes),
          ),
      ]),
    );
  }
}

const _kstOffset = Duration(hours: 9);

final _opsTimestampPattern = RegExp(
  r'^\s*(?:(\d{4})-)?(\d{2})-(\d{2})[T\s](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?(?:\s*(Z|[+-]\d{2}:?\d{2}))?\s*$',
);

bool _isKisSchedulerDryRun(TradingLogItem run) {
  final trigger = run.triggerSource.toLowerCase();
  final mode = run.mode.toLowerCase();
  return run.isKis &&
      trigger.contains('scheduler') &&
      (trigger.contains('dry_run') || mode.contains('dry_run'));
}

List<MapEntry<String, int>> _topReasons({
  required List<TradingLogItem> runs,
  required List<OrderLogItem> orders,
  required List<SignalLogItem> signals,
}) {
  final counts = <String, int>{};

  void scanItem(Iterable<String> values) {
    final seen = <String>{};
    for (final value in values) {
      final normalized = value.toLowerCase();
      for (final reason in _trackedReasons) {
        if (normalized.contains(reason)) {
          seen.add(reason);
        }
      }
    }
    for (final reason in seen) {
      counts[reason] = (counts[reason] ?? 0) + 1;
    }
  }

  for (final run in runs) {
    scanItem([run.result, run.reason, ...run.riskFlags, ...run.gatingNotes]);
  }
  for (final order in orders) {
    scanItem([
      order.result,
      order.reason,
      ...order.riskFlags,
      ...order.gatingNotes,
    ]);
  }
  for (final signal in signals) {
    scanItem([
      signal.result,
      signal.reason,
      ...signal.riskFlags,
      ...signal.gatingNotes,
    ]);
  }

  final entries = counts.entries.toList();
  entries.sort((a, b) {
    final countCompare = b.value.compareTo(a.value);
    if (countCompare != 0) return countCompare;
    return a.key.compareTo(b.key);
  });
  return entries.take(6).toList(growable: false);
}

const _trackedReasons = [
  'market_closed',
  'final_score_below_min_entry',
  'near_close_no_new_entry',
  'stop_loss_triggered',
  'take_profit_triggered',
  'kr_trading_disabled',
  'preview_only',
];

String _todayKstStamp() {
  final now = DateTime.now().toUtc().add(_kstOffset);
  return _dateStamp(now);
}

bool _isSameKstDay(String timestamp, String todayStamp) {
  return _kstDateStamp(timestamp) == todayStamp;
}

int _compareTimestampsDesc(String a, String b) {
  final aTime = _parseToKst(a);
  final bTime = _parseToKst(b);
  if (aTime == null && bTime == null) return 0;
  if (aTime == null) return 1;
  if (bTime == null) return -1;
  return bTime.compareTo(aTime);
}

String? _kstDateStamp(String value) {
  final kst = _parseToKst(value);
  if (kst == null) return null;
  return _dateStamp(kst);
}

DateTime? _parseToKst(String value) {
  final raw = value.trim();
  if (raw.isEmpty || raw == 'null') return null;
  final match = _opsTimestampPattern.firstMatch(raw);
  if (match == null) return null;

  final year = int.tryParse(match.group(1) ?? '2000');
  final month = int.tryParse(match.group(2) ?? '');
  final day = int.tryParse(match.group(3) ?? '');
  final hour = int.tryParse(match.group(4) ?? '');
  final minute = int.tryParse(match.group(5) ?? '');
  final second = int.tryParse(match.group(6) ?? '0');
  if (year == null ||
      month == null ||
      day == null ||
      hour == null ||
      minute == null ||
      second == null) {
    return null;
  }

  final sourceDateTime = DateTime.utc(year, month, day, hour, minute, second);
  final offset = _opsOffsetDuration(match.group(7));
  if (offset == null) return null;
  return sourceDateTime.subtract(offset).add(_kstOffset);
}

Duration? _opsOffsetDuration(String? zone) {
  if (zone == null || zone == 'Z') return Duration.zero;
  final compact = zone.replaceAll(':', '');
  if (compact.length != 5) return null;
  final sign = compact.startsWith('-') ? -1 : 1;
  if (!compact.startsWith('-') && !compact.startsWith('+')) return null;
  final hours = int.tryParse(compact.substring(1, 3));
  final minutes = int.tryParse(compact.substring(3, 5));
  if (hours == null || minutes == null || hours > 23 || minutes > 59) {
    return null;
  }
  return Duration(minutes: sign * ((hours * 60) + minutes));
}

String _dateStamp(DateTime value) {
  return '${value.year.toString().padLeft(4, '0')}-'
      '${value.month.toString().padLeft(2, '0')}-'
      '${value.day.toString().padLeft(2, '0')}';
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

String _primaryLine(String value) {
  final lines = value
      .split(RegExp(r'[\r\n]+'))
      .map((line) => line.trim())
      .where((line) => line.isNotEmpty);
  return lines.isEmpty ? value.trim() : lines.first;
}

String _numberLabel(num? value) {
  if (value == null) return '-';
  return value.toStringAsFixed(value % 1 == 0 ? 0 : 2);
}

String _percentFromDecimal(num? value) {
  if (value == null) return '-';
  final percent = value * 100;
  final sign = percent > 0 ? '+' : '';
  return '$sign${percent.toStringAsFixed(2)}%';
}

String _moneyLabel(
  num? value, {
  required String provider,
  required String market,
  required String currency,
}) {
  if (value == null) return '-';
  final displayCurrency = _displayCurrency(
    provider: provider,
    market: market,
    currency: currency,
  );
  final decimals = displayCurrency == 'KRW' ? 0 : 2;
  final formatted = _groupedNumber(value.abs(), decimals: decimals);
  final sign = value < 0 ? '-' : '';
  final symbol = displayCurrency == 'KRW' ? '\u20A9' : r'$';
  return '$sign$symbol$formatted';
}

String _displayCurrency({
  required String provider,
  required String market,
  required String currency,
}) {
  if (currency.trim().toUpperCase() == 'KRW' ||
      provider.trim().toLowerCase() == 'kis' ||
      market.trim().toUpperCase() == 'KR') {
    return 'KRW';
  }
  return 'USD';
}

String _groupedNumber(num value, {required int decimals}) {
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
