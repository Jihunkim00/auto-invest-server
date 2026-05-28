import 'dart:convert';

import 'package:flutter/material.dart';

import '../../../core/utils/timestamp_formatter.dart';
import '../../../core/widgets/section_card.dart';
import '../../../models/automation_runtime_monitor.dart';
import '../../dashboard/dashboard_controller.dart';

class AutomationRuntimeMonitorCard extends StatelessWidget {
  const AutomationRuntimeMonitorCard({
    super.key,
    required this.controller,
  });

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final monitor = controller.automationRuntimeMonitor;
    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.monitor_heart_outlined, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              'Automation Runtime Monitor',
              style: Theme.of(context).textTheme.titleMedium,
            ),
          ),
          IconButton(
            key: const ValueKey('automation-runtime-refresh'),
            tooltip: 'Refresh',
            onPressed: controller.automationRuntimeMonitorLoading
                ? null
                : () async {
                    final result =
                        await controller.refreshAutomationRuntimeMonitor();
                    if (!context.mounted) return;
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                      content: Text(result.message),
                      backgroundColor:
                          result.success ? Colors.green : Colors.orange,
                    ));
                  },
            icon: controller.automationRuntimeMonitorLoading
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.refresh, size: 20),
          ),
        ]),
        const SizedBox(height: 10),
        if (monitor == null)
          const _StateNote(
            text: 'No recent run loaded yet. Refresh to load runtime status.',
          )
        else ...[
          _GlobalSafetyLine(monitor: monitor),
          if (controller.automationRuntimeMonitorError != null) ...[
            const SizedBox(height: 8),
            _WarningLine(text: controller.automationRuntimeMonitorError!),
          ],
          const SizedBox(height: 12),
          LayoutBuilder(builder: (context, constraints) {
            final width = constraints.maxWidth < 760
                ? constraints.maxWidth
                : (constraints.maxWidth - 8) / 2;
            return Wrap(spacing: 8, runSpacing: 8, children: [
              SizedBox(
                width: width,
                child: _ProviderPanel(
                  title: 'Alpaca Paper Scheduler',
                  status: monitor.alpaca.statusLabel,
                  color: _statusColor(monitor.alpaca.statusLabel),
                  lines: [
                    _Line('Scheduler',
                        monitor.alpaca.schedulerEnabled ? 'ACTIVE' : 'OFF'),
                    _Line('Bot',
                        monitor.alpaca.botEnabled ? 'enabled' : 'disabled'),
                    _Line('Dry Run', monitor.alpaca.dryRun ? 'on' : 'off'),
                    _Line('Mode', monitor.alpaca.paperMode ? 'paper' : 'live'),
                    _Line(
                      'Last Run',
                      _timestampOrNone(monitor.alpaca.lastRunAt),
                    ),
                    _Line('Result', _valueOrNone(monitor.alpaca.lastResult)),
                    _Line('Symbol', _valueOrNone(monitor.alpaca.lastSymbol)),
                    _Line('Action', _valueOrNone(monitor.alpaca.lastAction)),
                    _Line('Block Reason',
                        _valueOrNone(monitor.alpaca.lastBlockReason)),
                    _Line('Order Submitted',
                        monitor.alpaca.orderSubmitted ? 'yes' : 'no'),
                    _Line('Order ID', _valueOrNone(monitor.alpaca.orderId)),
                  ],
                  summary:
                      'Alpaca: ${monitor.alpaca.statusLabel} | last run ${_valueOrNone(monitor.alpaca.lastResult)}: ${_valueOrNone(monitor.alpaca.lastBlockReason)}',
                ),
              ),
              SizedBox(
                width: width,
                child: _KisPanel(monitor: monitor.kis),
              ),
            ]);
          }),
          if (monitor.warnings.isNotEmpty ||
              monitor.diagnostics.isNotEmpty) ...[
            const SizedBox(height: 8),
            _Diagnostics(payload: {
              'warnings': monitor.warnings,
              'diagnostics': monitor.diagnostics,
            }),
          ],
        ],
      ]),
    );
  }
}

class _GlobalSafetyLine extends StatelessWidget {
  const _GlobalSafetyLine({required this.monitor});

  final AutomationRuntimeMonitor monitor;

  @override
  Widget build(BuildContext context) {
    final global = monitor.global;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Global Safety',
          style: TextStyle(color: Colors.white70, fontWeight: FontWeight.w800)),
      const SizedBox(height: 8),
      Wrap(spacing: 8, runSpacing: 8, children: [
        _Badge(
          text: global.botEnabled ? 'Bot ON' : 'Bot OFF',
          color: global.botEnabled ? Colors.greenAccent : Colors.white70,
        ),
        _Badge(
          text: global.dryRun ? 'DRY RUN ON' : 'DRY RUN OFF',
          color: global.dryRun ? Colors.lightBlueAccent : Colors.redAccent,
        ),
        _Badge(
          text: global.killSwitch ? 'Kill Switch ON' : 'Kill Switch OFF',
          color: global.killSwitch ? Colors.redAccent : Colors.greenAccent,
        ),
        _Badge(
          text: global.schedulerEnabled ? 'Scheduler ON' : 'Scheduler OFF',
          color: global.schedulerEnabled ? Colors.greenAccent : Colors.white70,
        ),
        _Badge(
          text: 'Provider ${global.selectedProvider}',
          color: Colors.white70,
        ),
        _Badge(
          text: 'Now ${global.currentLocalTime}',
          color: Colors.white70,
        ),
        _Badge(
          text: 'Refresh ${global.lastRefreshTime}',
          color: Colors.white70,
        ),
      ]),
    ]);
  }
}

class _KisPanel extends StatelessWidget {
  const _KisPanel({required this.monitor});

  final KisAutomationStatus monitor;

  @override
  Widget build(BuildContext context) {
    final status = monitor.realOrderSubmitted
        ? 'ORDER SUBMITTED'
        : monitor.schedulerDryRun
            ? 'DRY RUN'
            : monitor.schedulerEnabled
                ? 'READY'
                : 'OFF';
    return _ProviderPanel(
      title: 'KIS Live Scheduler',
      status: status,
      color: _statusColor(status),
      summary:
          'KIS Sell: ${monitor.sellStatusLabel} | last trigger ${monitor.lastTriggerDetected.toUpperCase()} | blocked: ${_valueOrNone(monitor.lastBlockReason)}',
      lines: [
        _Line(
            'KIS Scheduler', monitor.schedulerEnabled ? 'enabled' : 'disabled'),
        _Line('Scheduler Dry Run', monitor.schedulerDryRun ? 'on' : 'off'),
        _Line('Real Orders Allowed',
            monitor.schedulerAllowRealOrders ? 'yes' : 'no'),
        _Line('Scheduler Buy', monitor.schedulerBuyEnabled ? 'on' : 'off'),
        _Line('Scheduler Sell', monitor.schedulerSellEnabled ? 'on' : 'off'),
        _Line('Live Auto Buy', monitor.liveAutoBuyEnabled ? 'on' : 'off'),
        _Line('Live Auto Sell', monitor.liveAutoSellEnabled ? 'on' : 'off'),
        _Line('Stop-loss', monitor.stopLossEnabled ? 'enabled' : 'off'),
        _Line('Take-profit', monitor.takeProfitEnabled ? 'enabled' : 'off'),
        _Line('Limited Auto Buy',
            monitor.limitedAutoBuyEnabled ? 'enabled' : 'off'),
        _Line('Last Sell Run', _timestampOrNone(monitor.lastSellRunAt)),
        _Line('Sell Result', _valueOrNone(monitor.lastSellRunResult)),
        _Line('Last Buy Run', _timestampOrNone(monitor.lastBuyRunAt)),
        _Line('Buy Result', _valueOrNone(monitor.lastBuyRunResult)),
        _Line('Last Trigger', monitor.lastTriggerDetected.toUpperCase()),
        _Line('Block Reason', _valueOrNone(monitor.lastBlockReason)),
        _Line('Real Order Submitted',
            monitor.realOrderSubmitted ? 'true' : 'false'),
        _Line('Broker Submit Called',
            monitor.brokerSubmitCalled ? 'true' : 'false'),
        _Line('Manual Submit Called',
            monitor.manualSubmitCalled ? 'true' : 'false'),
        _Line('KIS ODNO', _valueOrNone(monitor.kisOdno)),
        _Line(
            'Today Submitted', monitor.todaySubmittedCount?.toString() ?? '--'),
        _Line('Daily Limit Remaining',
            monitor.dailyLimitRemaining?.toString() ?? '--'),
        _Line('KIS Buy',
            '${monitor.buyStatusLabel} | ${monitor.schedulerBuyEnabled ? 'enabled' : 'scheduler buy disabled'}'),
      ],
    );
  }
}

class _ProviderPanel extends StatelessWidget {
  const _ProviderPanel({
    required this.title,
    required this.status,
    required this.color,
    required this.lines,
    required this.summary,
  });

  final String title;
  final String status;
  final Color color;
  final List<_Line> lines;
  final String summary;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Text(title,
                style:
                    const TextStyle(fontSize: 14, fontWeight: FontWeight.w800)),
          ),
          _Badge(text: status, color: color),
        ]),
        const SizedBox(height: 8),
        Text(summary,
            style: const TextStyle(
                color: Colors.white70, fontWeight: FontWeight.w700)),
        const SizedBox(height: 10),
        Wrap(spacing: 14, runSpacing: 8, children: [
          for (final line in lines)
            _DataPair(label: line.label, value: line.value),
        ]),
      ]),
    );
  }
}

class _Line {
  const _Line(this.label, this.value);

  final String label;
  final String value;
}

class _DataPair extends StatelessWidget {
  const _DataPair({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return ConstrainedBox(
      constraints: const BoxConstraints(minWidth: 118, maxWidth: 190),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label.toUpperCase(),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
                color: Colors.white54,
                fontSize: 10,
                fontWeight: FontWeight.w700)),
        const SizedBox(height: 3),
        Text(value,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
                color: Colors.white,
                fontSize: 13,
                fontWeight: FontWeight.w700)),
      ]),
    );
  }
}

class _Badge extends StatelessWidget {
  const _Badge({required this.text, required this.color});

  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.34)),
      ),
      child: Text(text,
          style: TextStyle(
              color: color, fontSize: 11, fontWeight: FontWeight.w800)),
    );
  }
}

class _WarningLine extends StatelessWidget {
  const _WarningLine({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.orangeAccent.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.orangeAccent.withValues(alpha: 0.26)),
      ),
      child: Text(text,
          style: const TextStyle(
              color: Colors.orangeAccent, fontWeight: FontWeight.w700)),
    );
  }
}

class _StateNote extends StatelessWidget {
  const _StateNote({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(text, style: const TextStyle(color: Colors.white60));
  }
}

class _Diagnostics extends StatelessWidget {
  const _Diagnostics({required this.payload});

  final Map<String, dynamic> payload;

  @override
  Widget build(BuildContext context) {
    return ExpansionTile(
      tilePadding: EdgeInsets.zero,
      childrenPadding: EdgeInsets.zero,
      title: const Text('Diagnostics',
          style: TextStyle(
              color: Colors.white70,
              fontSize: 12,
              fontWeight: FontWeight.w800)),
      children: [
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(
            color: Colors.black.withValues(alpha: 0.22),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
          ),
          child: SelectableText(
            const JsonEncoder.withIndent('  ').convert(payload),
            style: const TextStyle(
                color: Colors.white70, fontSize: 11, fontFamily: 'monospace'),
          ),
        ),
      ],
    );
  }
}

Color _statusColor(String status) {
  switch (status) {
    case 'READY':
    case 'ACTIVE':
    case 'ORDER SUBMITTED':
    case 'FILLED':
      return Colors.greenAccent;
    case 'TRIGGER DETECTED':
    case 'DRY RUN':
      return Colors.lightBlueAccent;
    case 'BLOCKED':
    case 'MARKET CLOSED':
      return Colors.orangeAccent;
    case 'OFF':
    case 'NO RECENT RUN':
    default:
      return Colors.white70;
  }
}

String _timestampOrNone(String? value) {
  if (value == null || value.trim().isEmpty) return 'NO RECENT RUN';
  return formatTimestampWithKst(value);
}

String _valueOrNone(String? value) {
  final text = value?.trim();
  if (text == null || text.isEmpty) return 'none';
  return text;
}
