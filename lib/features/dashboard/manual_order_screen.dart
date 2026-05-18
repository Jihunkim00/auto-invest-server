import 'package:flutter/material.dart';

import '../../core/widgets/section_card.dart';
import '../../models/kis_limited_auto_buy.dart';
import 'dashboard_controller.dart';
import 'widgets/broker_context_controls.dart';
import 'widgets/manual_trading_run_section.dart';
import 'widgets/order_ticket_section.dart';

class TradingScreen extends StatelessWidget {
  const TradingScreen({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        return SafeArea(
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Expanded(
                  child: Text(
                    'Trading',
                    style: TextStyle(fontSize: 28, fontWeight: FontWeight.w700),
                  ),
                ),
                BrokerContextBadge(controller: controller),
              ]),
              const SizedBox(height: 6),
              Text(
                controller.selectedProvider == SelectedProvider.kis
                    ? 'KIS guarded run once and manual live ticket controls.'
                    : 'Alpaca paper single-symbol run and KIS manual controls.',
                style: const TextStyle(color: Colors.white70),
              ),
              const SizedBox(height: 6),
              const SizedBox(height: 12),
              if (controller.selectedProvider == SelectedProvider.kis) ...[
                _KisGuardedTradingRunSection(controller: controller),
                const SizedBox(height: 12),
                OrderTicketSection(controller: controller),
                const SizedBox(height: 12),
                ManualTradingRunSection(controller: controller),
              ] else ...[
                ManualTradingRunSection(controller: controller),
                const SizedBox(height: 12),
                _KisGuardedTradingRunSection(controller: controller),
                const SizedBox(height: 12),
                OrderTicketSection(controller: controller),
              ],
            ],
          ),
        );
      },
    );
  }
}

class ManualOrderScreen extends StatelessWidget {
  const ManualOrderScreen({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return TradingScreen(controller: controller);
  }
}

class _KisGuardedTradingRunSection extends StatefulWidget {
  const _KisGuardedTradingRunSection({required this.controller});

  final DashboardController controller;

  @override
  State<_KisGuardedTradingRunSection> createState() =>
      _KisGuardedTradingRunSectionState();
}

class _KisGuardedTradingRunSectionState
    extends State<_KisGuardedTradingRunSection> {
  late final TextEditingController _symbolController;

  @override
  void initState() {
    super.initState();
    _symbolController =
        TextEditingController(text: widget.controller.kisGuardedRunSymbol);
  }

  @override
  void dispose() {
    _symbolController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final controller = widget.controller;
    _syncSymbol(controller);
    final result = controller.latestKisLimitedAutoBuyResult;

    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.security_outlined, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text('KIS Guarded Trading Run Once',
                style: Theme.of(context).textTheme.titleMedium),
          ),
          const _SoftBadge(
              text: 'KIS GUARDED RUN ONCE', color: Colors.redAccent),
        ]),
        const SizedBox(height: 10),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(
              text: 'Manual click required', color: Colors.lightBlueAccent),
          _SoftBadge(text: 'Existing backend gate', color: Colors.greenAccent),
          _SoftBadge(text: 'No scheduler enable', color: Colors.amberAccent),
        ]),
        const SizedBox(height: 12),
        TextField(
          controller: _symbolController,
          decoration: const InputDecoration(
            labelText: 'KR symbol',
            hintText: '005930',
            border: OutlineInputBorder(),
          ),
          keyboardType: TextInputType.number,
          onChanged: controller.setKisGuardedRunSymbol,
        ),
        const SizedBox(height: 12),
        SegmentedButton<int>(
          segments: const [
            ButtonSegment(value: 1, label: Text('Gate 1')),
            ButtonSegment(value: 2, label: Text('Gate 2')),
            ButtonSegment(value: 3, label: Text('Gate 3')),
            ButtonSegment(value: 4, label: Text('Gate 4')),
          ],
          selected: {controller.selectedGateLevel},
          onSelectionChanged: (selection) {
            controller.setSelectedGateLevel(selection.first);
            controller.setKisGuardedRunConfirmation(false);
            controller.setKisGuardedRunExtraSafety(false);
          },
        ),
        const SizedBox(height: 12),
        _KisGuardedSafetyStatus(controller: controller),
        const SizedBox(height: 8),
        CheckboxListTile(
          contentPadding: EdgeInsets.zero,
          controlAffinity: ListTileControlAffinity.leading,
          value: controller.kisGuardedRunConfirmation,
          onChanged: controller.kisLimitedAutoBuyLoading
              ? null
              : (value) =>
                  controller.setKisGuardedRunConfirmation(value == true),
          title: const Text('Confirm live KIS guarded run once'),
          subtitle: const Text(
            'This is not an auto-trading enable switch.',
          ),
        ),
        CheckboxListTile(
          contentPadding: EdgeInsets.zero,
          controlAffinity: ListTileControlAffinity.leading,
          value: controller.kisGuardedRunExtraSafety,
          onChanged: controller.kisLimitedAutoBuyLoading
              ? null
              : (value) =>
                  controller.setKisGuardedRunExtraSafety(value == true),
          title: const Text('I understand this may place a real KIS buy order'),
          subtitle: const Text(
            'Backend risk gates still decide whether an order is approved.',
          ),
        ),
        const SizedBox(height: 8),
        FilledButton.icon(
          onPressed: controller.canRunKisGuardedTradingOnce
              ? () async {
                  final confirmed = await _confirmKisGuardedRun(context);
                  if (!confirmed || !context.mounted) return;
                  final actionResult =
                      await controller.runKisGuardedTradingOnce();
                  if (!context.mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(actionResult.message),
                    backgroundColor:
                        actionResult.success ? Colors.green : Colors.redAccent,
                  ));
                }
              : null,
          icon: controller.kisLimitedAutoBuyLoading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.play_arrow),
          label: Text(controller.kisLimitedAutoBuyLoading
              ? 'Running guarded KIS...'
              : 'Analyze & Run Once'),
        ),
        if (!controller.canRunKisGuardedTradingOnce) ...[
          const SizedBox(height: 8),
          _StateLine(text: controller.kisGuardedRunBlockedMessage()),
        ],
        if (controller.kisLimitedAutoBuyError != null) ...[
          const SizedBox(height: 10),
          _StateLine(
            text: controller.kisLimitedAutoBuyError!,
            color: Colors.redAccent,
          ),
        ],
        if (result != null) ...[
          const SizedBox(height: 12),
          _KisGuardedResultSummary(result: result),
        ],
      ]),
    );
  }

  void _syncSymbol(DashboardController controller) {
    final symbol = controller.kisGuardedRunSymbol;
    if (_symbolController.text == symbol) return;
    _symbolController.value = TextEditingValue(
      text: symbol,
      selection: TextSelection.collapsed(offset: symbol.length),
    );
  }

  Future<bool> _confirmKisGuardedRun(BuildContext context) async {
    final controller = widget.controller;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Confirm Run Once'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'This may place a real KIS buy order if backend risk gates approve it.\n'
              'Broker account funds may be used.',
            ),
            const SizedBox(height: 14),
            _DialogRow(label: 'Symbol', value: controller.kisGuardedRunSymbol),
            _DialogRow(
                label: 'Gate', value: 'Gate ${controller.selectedGateLevel}'),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Confirm Run Once'),
          ),
        ],
      ),
    );
    return confirmed == true;
  }
}

class _KisGuardedSafetyStatus extends StatelessWidget {
  const _KisGuardedSafetyStatus({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final status = controller.kisSafetyStatus;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Expanded(
            child: Text('SAFETY STATUS',
                style: TextStyle(
                    color: Colors.white54,
                    fontSize: 10,
                    fontWeight: FontWeight.w800)),
          ),
          IconButton(
            tooltip: 'Refresh KIS safety status',
            onPressed: controller.kisSafetyStatusLoading
                ? null
                : () => controller.refreshKisSafetyStatus(),
            icon: controller.kisSafetyStatusLoading
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.refresh, size: 18),
          ),
        ]),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _DataPair(
              label: 'dry_run', value: status.runtimeDryRun ? 'ON' : 'OFF'),
          _DataPair(
              label: 'kill_switch', value: status.killSwitch ? 'ON' : 'OFF'),
          _DataPair(label: 'kis_enabled', value: status.kisEnabled.toString()),
          _DataPair(
              label: 'kis_real_order_enabled',
              value: status.kisRealOrderEnabled.toString()),
          _DataPair(label: 'market_open', value: status.marketOpen.toString()),
          _DataPair(
              label: 'entry_allowed_now',
              value: status.entryAllowedNow.toString()),
        ]),
      ]),
    );
  }
}

class _KisGuardedResultSummary extends StatelessWidget {
  const _KisGuardedResultSummary({required this.result});

  final KisLimitedAutoBuy result;

  @override
  Widget build(BuildContext context) {
    final orderStatus = result.orderId == null
        ? 'No order created'
        : 'Order ID ${result.orderId}';
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('Result Summary',
            style: TextStyle(fontWeight: FontWeight.w800)),
        const SizedBox(height: 10),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _DataPair(
              label: 'Action', value: result.action.toString().toUpperCase()),
          _DataPair(label: 'Result', value: result.result.toString()),
          _DataPair(label: 'Reason', value: _displayText(result.reason)),
          _DataPair(label: 'Symbol', value: result.symbol?.toString() ?? 'n/a'),
          _DataPair(label: 'Final score', value: _score(result.finalScore)),
          _DataPair(label: 'Confidence', value: _score(result.confidence)),
          _DataPair(label: 'Order status', value: orderStatus),
          _DataPair(
              label: 'real_order_submitted',
              value: result.realOrderSubmitted.toString()),
          _DataPair(
              label: 'broker_submit_called',
              value: result.brokerSubmitCalled.toString()),
          _DataPair(
              label: 'manual_submit_called',
              value: result.manualSubmitCalled.toString()),
        ]),
        if (result.blockedBy.isNotEmpty) ...[
          const SizedBox(height: 8),
          _StateLine(text: 'Risk flags: ${result.blockedBy.join(', ')}'),
        ],
        if (result.failedChecks.isNotEmpty) ...[
          const SizedBox(height: 8),
          _StateLine(text: 'Gating notes: ${result.failedChecks.join(', ')}'),
        ],
        const SizedBox(height: 8),
        ExpansionTile(
          tilePadding: EdgeInsets.zero,
          childrenPadding: EdgeInsets.zero,
          title: const Text('Advanced Details'),
          children: [
            _StateLine(
              text:
                  'checks=${result.checks}\nsafety=${result.safety}\naudit_metadata=${result.auditMetadata}',
            ),
          ],
        ),
      ]),
    );
  }
}

class _DialogRow extends StatelessWidget {
  const _DialogRow({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Row(children: [
        SizedBox(
            width: 76,
            child: Text(label, style: const TextStyle(color: Colors.white70))),
        Expanded(
            child: Text(value,
                style: const TextStyle(fontWeight: FontWeight.w700))),
      ]),
    );
  }
}

class _DataPair extends StatelessWidget {
  const _DataPair({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return ConstrainedBox(
      constraints: const BoxConstraints(minWidth: 112, maxWidth: 190),
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
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
                color: Colors.white,
                fontSize: 13,
                fontWeight: FontWeight.w700)),
      ]),
    );
  }
}

class _StateLine extends StatelessWidget {
  const _StateLine({required this.text, this.color = Colors.white60});

  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 11),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
      ),
      child: Text(text, style: TextStyle(color: color)),
    );
  }
}

class _SoftBadge extends StatelessWidget {
  const _SoftBadge({required this.text, required this.color});

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

String _score(double? value) {
  if (value == null) return '--';
  return value.toStringAsFixed(value.truncateToDouble() == value ? 0 : 2);
}

String _displayText(Object? value) {
  final text = value?.toString().trim() ?? '';
  return text.isEmpty || text == 'null' ? 'Not available' : text;
}
