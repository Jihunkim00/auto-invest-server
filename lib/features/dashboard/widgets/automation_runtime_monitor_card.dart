import 'dart:convert';

import 'package:flutter/material.dart';

import '../../../core/utils/timestamp_formatter.dart';
import '../../../core/widgets/section_card.dart';
import '../../../models/automation_runtime_monitor.dart';
import '../../../models/scheduler_status.dart';
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
      key: const Key('automation_runtime_monitor_card'),
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
                    _Line('US Scheduler',
                        monitor.alpaca.schedulerEnabled ? 'ON' : 'OFF'),
                    _Line(
                      'Next US Slot',
                      _slotText(
                        monitor.alpaca.nextSlotName,
                        monitor.alpaca.nextSlotTimeLocal,
                      ),
                    ),
                    _Line('Bot',
                        monitor.alpaca.botEnabled ? 'enabled' : 'disabled'),
                    _Line('Dry Run', monitor.alpaca.dryRun ? 'on' : 'off'),
                    _Line('Mode', monitor.alpaca.paperMode ? 'paper' : 'live'),
                    _Line(
                      'Last US Scheduler Run',
                      _timestampOrNone(monitor.alpaca.lastRunAt),
                    ),
                    _Line(
                        'Last Run ID', _valueOrNone(monitor.alpaca.lastRunId)),
                    _Line('Result', _valueOrNone(monitor.alpaca.lastResult)),
                    _Line('Symbol', _valueOrNone(monitor.alpaca.lastSymbol)),
                    _Line('Action', _valueOrNone(monitor.alpaca.lastAction)),
                    _Line('Block Reason',
                        _valueOrNone(monitor.alpaca.lastBlockReason)),
                    _Line('Order Submitted',
                        monitor.alpaca.orderSubmitted ? 'yes' : 'no'),
                    _Line('Order ID', _valueOrNone(monitor.alpaca.orderId)),
                    _Line('Last Single Run',
                        _timestampOrNone(monitor.alpaca.lastSingleRunAt)),
                    _Line('Single Symbol',
                        _valueOrNone(monitor.alpaca.lastSingleSymbol)),
                    _Line('Single Action',
                        _valueOrNone(monitor.alpaca.lastSingleAction)),
                    _Line('Single Result',
                        _valueOrNone(monitor.alpaca.lastSingleResult)),
                    _Line('Single Block',
                        _valueOrNone(monitor.alpaca.lastSingleBlockReason)),
                    _Line('Today Paper Orders',
                        monitor.alpaca.todayPaperOrderCount.toString()),
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
          text: global.schedulerEnabled
              ? 'Global Scheduler ON'
              : 'Global Scheduler OFF',
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
    final risk = monitor.riskSummary;
    final warnings = _kisRiskWarnings(risk);
    final status = monitor.realOrderSubmitted
        ? 'ORDER SUBMITTED'
        : monitor.realOrderSchedulerEnabled
            ? 'READY'
            : monitor.schedulerEnabled
                ? (monitor.schedulerDryRun ? 'DRY RUN' : 'ACTIVE')
                : 'OFF';
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      for (final warning in warnings) ...[
        _RiskWarningLine(text: warning.text, color: warning.color),
        const SizedBox(height: 8),
      ],
      _ProviderPanel(
        title: 'KIS Live Scheduler',
        status: status,
        color: _statusColor(status),
        summary:
            'KIS Scheduler Effective: ${monitor.schedulerEnabled ? 'ON' : 'OFF'} | KIS Real Order Scheduler: ${monitor.realOrderSchedulerEnabled ? 'ON' : 'OFF'} | warning: ${risk.warningLevel}',
        lines: [
          _Line('Warning Level', risk.warningLevel),
          _Line('Live Sell Armed', risk.liveSellArmed ? 'true' : 'false'),
          _Line('Live Buy Armed', risk.liveBuyArmed ? 'true' : 'false'),
          _Line('Dry Run', risk.dryRun ? 'on' : 'off'),
          _Line('Kill Switch', risk.killSwitch ? 'on' : 'off'),
          _Line('KIS Scheduler Config',
              monitor.schedulerConfigEnabled ? 'ON' : 'OFF'),
          _Line('KIS Scheduler Effective',
              monitor.schedulerEnabled ? 'ON' : 'OFF'),
          _Line('KIS Real Order Scheduler',
              monitor.realOrderSchedulerEnabled ? 'ON' : 'OFF'),
          _Line(
              'KIS Live Ready', monitor.liveSchedulerReady ? 'true' : 'false'),
          _Line(
            'Next KR Slot',
            _slotText(monitor.nextSlotName, monitor.nextSlotTimeLocal),
          ),
          _Line('Last KR Scheduler Run',
              _timestampOrNone(monitor.lastSchedulerRunAt)),
          _Line('Last Scheduler Result',
              _valueOrNone(monitor.lastSchedulerRunResult)),
          _Line('Last Scheduler Reason',
              _valueOrNone(monitor.lastSchedulerRunReason)),
          _Line('Last Scheduler ID', _valueOrNone(monitor.lastSchedulerRunId)),
          _Line('Last Scheduler Mode',
              _valueOrNone(monitor.lastSchedulerRunMode)),
          _Line('Last Scheduler Source',
              _valueOrNone(monitor.lastSchedulerRunTriggerSource)),
          _Line(
            'Block Reasons',
            monitor.blockReasons.isEmpty
                ? 'none'
                : monitor.blockReasons.join(', '),
          ),
          _Line(
              'Blocking Flags',
              risk.blockingFlags.isEmpty
                  ? 'none'
                  : risk.blockingFlags.join(', ')),
          _Line('Risky Flags',
              risk.riskyFlags.isEmpty ? 'none' : risk.riskyFlags.join(', ')),
          _Line('Scheduler Dry Run', monitor.schedulerDryRun ? 'on' : 'off'),
          _Line('Real Orders Allowed',
              monitor.schedulerAllowRealOrders ? 'yes' : 'no'),
          _Line('KIS Sell Enabled',
              monitor.schedulerSellEnabled ? 'true' : 'false'),
          _Line('KIS Buy Enabled',
              monitor.schedulerBuyEnabled ? 'true' : 'false'),
          _Line('KIS Sell Gate', risk.sellGateEnabled ? 'READY' : 'OFF'),
          _Line('KIS Buy Gate', risk.buyGateEnabled ? 'READY' : 'OFF'),
          _Line('Daily Live Order Limit', risk.dailyLiveOrderLimit.toString()),
          _Line('Daily Limit Remaining',
              risk.dailyLiveOrderRemaining?.toString() ?? '--'),
          _Line('Max Notional %', _percent(risk.maxNotionalPct)),
          _Line('Live Auto Buy', monitor.liveAutoBuyEnabled ? 'on' : 'off'),
          _Line('Live Auto Sell', monitor.liveAutoSellEnabled ? 'on' : 'off'),
          _Line(
              'Stop-loss Enabled', monitor.stopLossEnabled ? 'true' : 'false'),
          _Line('Take-profit Enabled',
              monitor.takeProfitEnabled ? 'true' : 'false'),
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
          _Line('Today Submitted',
              monitor.todaySubmittedCount?.toString() ?? '--'),
          _Line('KIS Buy',
              '${monitor.buyStatusLabel} | ${monitor.schedulerBuyEnabled ? 'enabled' : 'scheduler buy disabled'}'),
        ],
      ),
    ]);
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

class _RiskWarningLine extends StatelessWidget {
  const _RiskWarningLine({required this.text, required this.color});

  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.28)),
      ),
      child: Text(
        text,
        style: TextStyle(color: color, fontWeight: FontWeight.w800),
      ),
    );
  }
}

class _KisRiskWarning {
  const _KisRiskWarning(this.text, this.color);

  final String text;
  final Color color;
}

List<_KisRiskWarning> _kisRiskWarnings(SchedulerRiskSummary risk) {
  final items = <_KisRiskWarning>[];
  if (risk.liveSellArmed) {
    items.add(const _KisRiskWarning(
      'KIS live sell automation is armed. Stop-loss sell may submit real KIS orders.',
      Colors.orangeAccent,
    ));
  }
  if (risk.liveBuyArmed) {
    items.add(const _KisRiskWarning(
      'KIS live buy automation is enabled. This should remain OFF unless explicitly testing.',
      Colors.redAccent,
    ));
  }
  if (risk.warningLevel == 'dangerous_mixed') {
    final flags = risk.riskyFlags.isEmpty ? 'none' : risk.riskyFlags.join(', ');
    items.add(_KisRiskWarning(
      'Dangerous mixed KIS automation settings detected. Risky flags: $flags',
      Colors.redAccent,
    ));
  }
  if (risk.warningLevel == 'blocked') {
    final flags =
        risk.blockingFlags.isEmpty ? 'none' : risk.blockingFlags.join(', ');
    items.add(_KisRiskWarning(
      'KIS live automation request is blocked. Blocking flags: $flags',
      Colors.orangeAccent,
    ));
  }
  if (risk.warningLevel == 'safe' || risk.safeModeActive) {
    items.add(const _KisRiskWarning(
      'Safe Mode / Live automation off.',
      Colors.greenAccent,
    ));
  }
  return items;
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

String _slotText(String? name, String? timeLocal) {
  final slotName = _valueOrNone(name);
  final slotTime = timeLocal == null || timeLocal.trim().isEmpty
      ? 'time unknown'
      : formatTimestampWithKst(timeLocal);
  if (slotName == 'none') return slotTime;
  return '$slotName @ $slotTime';
}

String _valueOrNone(String? value) {
  final text = value?.trim();
  if (text == null || text.isEmpty) return 'none';
  return text;
}

String _percent(double value) => '${(value * 100).toStringAsFixed(2)}%';
