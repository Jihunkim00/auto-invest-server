import 'package:flutter/material.dart';

import '../../core/widgets/section_card.dart';
import '../../models/kis_limited_auto_buy.dart';
import 'dashboard_controller.dart';
import 'widgets/broker_context_controls.dart';
import 'widgets/manual_trading_run_section.dart';
import 'widgets/result_presentation_helpers.dart' as presentation;

class TradingScreen extends StatelessWidget {
  const TradingScreen({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final isKis = controller.selectedProvider == SelectedProvider.kis;
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
                isKis
                    ? 'Selected broker: KIS live. Analyze the selected KR symbol only.'
                    : 'Selected broker: Alpaca paper. Analyze and paper-buy one US symbol.',
                style: const TextStyle(color: Colors.white70),
              ),
              const SizedBox(height: 12),
              if (isKis)
                _KisAnalyzeAndBuyCard(controller: controller)
              else
                ManualTradingRunSection(controller: controller),
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

class _KisAnalyzeAndBuyCard extends StatefulWidget {
  const _KisAnalyzeAndBuyCard({required this.controller});

  final DashboardController controller;

  @override
  State<_KisAnalyzeAndBuyCard> createState() => _KisAnalyzeAndBuyCardState();
}

class _KisAnalyzeAndBuyCardState extends State<_KisAnalyzeAndBuyCard> {
  late final TextEditingController _symbolController;
  late final TextEditingController _qtyController;

  @override
  void initState() {
    super.initState();
    _symbolController =
        TextEditingController(text: widget.controller.kisGuardedRunSymbol);
    _qtyController = TextEditingController(text: '1');
  }

  @override
  void dispose() {
    _symbolController.dispose();
    _qtyController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final controller = widget.controller;
    final symbol = _symbolController.text.trim().toUpperCase();
    final qty = int.tryParse(_qtyController.text.trim());
    final canRequest = symbol.isNotEmpty &&
        qty != null &&
        qty > 0 &&
        controller.kisGuardedRunConfirmation &&
        !controller.kisLimitedAutoBuyLoading;
    final result = controller.latestKisLimitedAutoBuyResult;

    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.verified_user_outlined, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text('KIS Analyze & Buy',
                style: Theme.of(context).textTheme.titleMedium),
          ),
          const _SoftBadge(text: 'KIS LIVE', color: Colors.redAccent),
        ]),
        const SizedBox(height: 12),
        TextField(
          controller: _symbolController,
          decoration: const InputDecoration(
            labelText: 'KR Symbol',
            hintText: '005930',
            border: OutlineInputBorder(),
          ),
          keyboardType: TextInputType.number,
          onChanged: controller.setKisGuardedRunSymbol,
        ),
        const SizedBox(height: 10),
        TextField(
          controller: _qtyController,
          decoration: const InputDecoration(
            labelText: 'Quantity',
            border: OutlineInputBorder(),
          ),
          keyboardType: TextInputType.number,
          onChanged: (_) => setState(() {}),
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
          },
        ),
        const SizedBox(height: 12),
        CheckboxListTile(
          contentPadding: EdgeInsets.zero,
          controlAffinity: ListTileControlAffinity.leading,
          value: controller.kisGuardedRunConfirmation,
          onChanged: controller.kisLimitedAutoBuyLoading
              ? null
              : (value) =>
                  controller.setKisGuardedRunConfirmation(value == true),
          title: const Text('실제 KIS 주문이 제출될 수 있음을 확인했습니다.'),
        ),
        FilledButton.icon(
          onPressed: canRequest
              ? () async {
                  final confirmed =
                      await _confirmKisLiveRun(context, symbol, qty);
                  if (!confirmed || !context.mounted) return;
                  final actionResult =
                      await controller.runKisAnalyzeAndBuySelectedSymbol(
                    symbol: symbol,
                    quantity: qty,
                    gateLevel: controller.selectedGateLevel,
                  );
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
              ? 'Analyzing...'
              : 'Analyze & Buy KIS'),
        ),
        if (!canRequest) ...[
          const SizedBox(height: 8),
          _ReasonBanner(
            text: controller.kisGuardedRunConfirmation
                ? 'Enter a KR symbol and quantity.'
                : 'Confirm that a real KIS order may be submitted.',
          ),
        ],
        if (controller.kisLimitedAutoBuyError != null) ...[
          const SizedBox(height: 10),
          _ReasonBanner(
            text: controller.kisLimitedAutoBuyError!,
            color: Colors.redAccent,
          ),
        ],
        if (result != null) ...[
          const SizedBox(height: 12),
          _KisResultPanel(
            result: result,
            selectedSymbol: symbol,
          ),
        ],
      ]),
    );
  }

  Future<bool> _confirmKisLiveRun(
      BuildContext context, String symbol, int qty) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Confirm KIS Order'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('실제 KIS 주문이 제출될 수 있습니다.'),
            const SizedBox(height: 12),
            _DialogRow(label: '종목', value: symbol),
            _DialogRow(label: '수량/금액', value: qty.toString()),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('취소'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('확인'),
          ),
        ],
      ),
    );
    return confirmed == true;
  }
}

class _KisResultPanel extends StatelessWidget {
  const _KisResultPanel({
    required this.result,
    required this.selectedSymbol,
  });

  final KisLimitedAutoBuy result;
  final String selectedSymbol;

  @override
  Widget build(BuildContext context) {
    final mismatch = presentation.selectedSymbolMismatch(
      selectedSymbol: selectedSymbol,
      returnedSymbol: result.symbol,
    );
    final reason = presentation.translateReason(_mainReason(result));
    final safety = presentation.safetyLine(result.safety);
    final hasScore = result.finalScore != null || result.confidence != null;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('Decision Summary',
            style: TextStyle(fontWeight: FontWeight.w800)),
        const SizedBox(height: 10),
        if (mismatch != null) ...[
          _ReasonBanner(text: mismatch, color: Colors.redAccent),
          const SizedBox(height: 10),
        ],
        _DataGrid(pairs: [
          _DataPairData(label: 'Symbol', value: selectedSymbol),
          _DataPairData(
              label: 'Decision', value: _decisionLabel(result).toUpperCase()),
          _DataPairData(label: 'Result', value: _resultLabel(result)),
          _DataPairData(label: 'Next Action', value: _nextAction(result)),
        ]),
        const SizedBox(height: 12),
        const Text('Score / Analysis Summary',
            style: TextStyle(fontWeight: FontWeight.w800)),
        const SizedBox(height: 8),
        if (!hasScore)
          const _ReasonBanner(
            text:
                'Analysis score was not returned by this run. This run was blocked before full analysis. Use Watchlist for candidate discovery.',
          )
        else
          _DataGrid(pairs: [
            _DataPairData(
                label: 'Primary score',
                value: presentation.displayScore(result.finalScore)),
            _DataPairData(
                label: 'Confidence',
                value: presentation.displayScore(result.confidence,
                    fallback: 'Confidence not returned')),
          ]),
        const SizedBox(height: 12),
        const Text('Order Result',
            style: TextStyle(fontWeight: FontWeight.w800)),
        const SizedBox(height: 8),
        _DataGrid(pairs: [
          _DataPairData(label: 'Order', value: presentation.orderStatusLabel(
            realOrderSubmitted: result.realOrderSubmitted,
            orderId: result.orderId?.toString(),
            kisOdno: result.kisOdno,
            result: result.result,
            safety: result.safety,
          )),
          _DataPairData(
              label: 'Order ID', value: result.orderId?.toString() ?? '--'),
          _DataPairData(label: 'KIS ODNO', value: result.kisOdno ?? '--'),
          _DataPairData(
              label: 'Qty', value: result.quantity?.toString() ?? '--'),
        ]),
        const SizedBox(height: 12),
        _ReasonBanner(text: reason, color: Colors.amberAccent),
        const SizedBox(height: 8),
        _ReasonBanner(text: safety, color: Colors.lightBlueAccent),
        const SizedBox(height: 8),
        _ReadableDetails(result: result),
      ]),
    );
  }
}

class _ReadableDetails extends StatelessWidget {
  const _ReadableDetails({required this.result});

  final KisLimitedAutoBuy result;

  @override
  Widget build(BuildContext context) {
    return ExpansionTile(
      tilePadding: EdgeInsets.zero,
      childrenPadding: EdgeInsets.zero,
      title: const Text('Run Details'),
      subtitle: const Text('Readable analysis, safety, and order details.'),
      children: [
        _DataGrid(pairs: [
          _DataPairData(label: 'Action', value: result.action.toUpperCase()),
          _DataPairData(label: 'Result', value: _resultLabel(result)),
          _DataPairData(
              label: 'Real order submitted',
              value: result.realOrderSubmitted ? 'Yes' : 'No'),
          _DataPairData(
              label: 'Broker submit called',
              value: result.brokerSubmitCalled ? 'Yes' : 'No'),
          _DataPairData(
              label: 'Manual submit called',
              value: result.manualSubmitCalled ? 'Yes' : 'No'),
        ]),
        const SizedBox(height: 8),
        if (result.blockedBy.isNotEmpty)
          _BulletList(
            title: 'Risk / Block Details',
            items: result.blockedBy
                .take(5)
                .map(presentation.translateReason)
                .toList(),
          ),
        if (result.failedChecks.isNotEmpty)
          _BulletList(
            title: 'Gating Notes',
            items: result.failedChecks
                .take(5)
                .map(presentation.translateReason)
                .toList(),
          ),
        ExpansionTile(
          tilePadding: EdgeInsets.zero,
          childrenPadding: EdgeInsets.zero,
          title: const Text('Developer Raw Payload'),
          children: [
            _ReasonBanner(
              text: 'checks=${result.checks}\n'
                  'safety=${result.safety}\n'
                  'audit_metadata=${result.auditMetadata}',
            ),
          ],
        ),
      ],
    );
  }
}

class _BulletList extends StatelessWidget {
  const _BulletList({required this.title, required this.items});

  final String title;
  final List<String> items;

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) return const SizedBox.shrink();
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(title, style: const TextStyle(fontWeight: FontWeight.w800)),
      const SizedBox(height: 6),
      for (final item in items)
        Padding(
          padding: const EdgeInsets.only(bottom: 4),
          child: Text('- $item', style: const TextStyle(color: Colors.white70)),
        ),
      const SizedBox(height: 8),
    ]);
  }
}

class _DataGrid extends StatelessWidget {
  const _DataGrid({required this.pairs});

  final List<_DataPairData> pairs;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 14,
      runSpacing: 8,
      children: [
        for (final pair in pairs)
          _DataPair(label: pair.label, value: pair.value),
      ],
    );
  }
}

class _DataPairData {
  const _DataPairData({required this.label, required this.value});

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
      constraints: const BoxConstraints(minWidth: 112, maxWidth: 220),
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

class _ReasonBanner extends StatelessWidget {
  const _ReasonBanner({required this.text, this.color = Colors.white60});

  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 11),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.18)),
      ),
      child: Text(text, style: TextStyle(color: color)),
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

String _mainReason(KisLimitedAutoBuy result) {
  if (result.reason.trim().isNotEmpty) return result.reason;
  if (result.blockedBy.isNotEmpty) return result.blockedBy.first;
  if (result.failedChecks.isNotEmpty) return result.failedChecks.first;
  if (result.safetyFlag('runtime_dry_run') || result.safetyFlag('dry_run')) {
    return 'dry_run';
  }
  return 'Backend risk gate blocked this order';
}

String _decisionLabel(KisLimitedAutoBuy result) {
  final action = result.action.trim().toLowerCase();
  final resultText = result.result.trim().toLowerCase();
  if (resultText.contains('preview')) return 'PREVIEW ONLY';
  if (resultText.contains('block') || result.blockedBy.isNotEmpty) {
    return 'BLOCKED';
  }
  if (action == 'buy') return 'BUY';
  return 'HOLD';
}

String _resultLabel(KisLimitedAutoBuy result) {
  final normalized = result.result.trim().toLowerCase();
  if (result.realOrderSubmitted || normalized == 'submitted') {
    return 'executed';
  }
  if (normalized.contains('dry')) return 'dry-run';
  if (normalized.contains('reject')) return 'rejected';
  if (normalized.contains('block')) return 'blocked';
  if (normalized.contains('skip')) return 'skipped';
  if (normalized.isEmpty) return 'blocked';
  return normalized;
}

String _nextAction(KisLimitedAutoBuy result) {
  if (result.realOrderSubmitted) return 'Monitor and sync order status';
  if (result.safetyFlag('runtime_dry_run') || result.safetyFlag('dry_run')) {
    return 'Dry-run mode: no real order submitted';
  }
  return presentation.translateReason(_mainReason(result));
}
