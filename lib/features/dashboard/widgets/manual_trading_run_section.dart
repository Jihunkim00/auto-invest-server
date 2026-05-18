import 'package:flutter/material.dart';

import '../../../core/widgets/gpt_risk_context_view.dart';
import '../../../core/widgets/section_card.dart';
import '../../../models/manual_trading_run_result.dart';
import '../../dashboard/dashboard_controller.dart';

class ManualTradingRunSection extends StatefulWidget {
  const ManualTradingRunSection({
    super.key,
    required this.controller,
    this.onOpenManualOrder,
  });

  final DashboardController controller;
  final VoidCallback? onOpenManualOrder;

  @override
  State<ManualTradingRunSection> createState() =>
      _ManualTradingRunSectionState();
}

class _ManualTradingRunSectionState extends State<ManualTradingRunSection> {
  static const _usSymbols = <String>[
    'AAPL',
    'MSFT',
    'NVDA',
    'AMZN',
    'META',
    'GOOGL',
    'AVGO',
    'TSLA',
    'WMT',
    'CSCO',
    'APP',
    'ARM',
    'SHOP',
  ];

  late final TextEditingController _symbolController;

  @override
  void initState() {
    super.initState();
    _symbolController = TextEditingController(text: _usSymbols.first);
  }

  @override
  void dispose() {
    _symbolController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final controller = widget.controller;
    final symbol = _normalizedSymbol;
    final symbols = _usSymbols;
    final dropdownValue = symbols.contains(symbol) ? symbol : null;

    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.play_circle_outline, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text('Alpaca Analyze & Paper Buy',
                style: Theme.of(context).textTheme.titleMedium),
          ),
          const _SafetyBadge(text: 'ALPACA PAPER'),
        ]),
        const SizedBox(height: 12),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _SafetyBadge(text: 'Paper trading only'),
          _SafetyBadge(text: 'Uses existing risk engine'),
          _SafetyBadge(text: 'HOLD is normal'),
          _SafetyBadge(text: 'No KIS live order here'),
        ]),
        const SizedBox(height: 12),
        LayoutBuilder(builder: (context, constraints) {
          final vertical = constraints.maxWidth < 520;
          final dropdown = DropdownButtonFormField<String>(
            key: ValueKey(dropdownValue ?? 'custom-symbol'),
            initialValue: dropdownValue,
            decoration: const InputDecoration(
                labelText: 'Symbol selector', border: OutlineInputBorder()),
            items: symbols
                .map((symbol) =>
                    DropdownMenuItem(value: symbol, child: Text(symbol)))
                .toList(),
            onChanged: (value) {
              if (value == null) return;
              setState(() {
                _symbolController.value = TextEditingValue(
                  text: value,
                  selection: TextSelection.collapsed(offset: value.length),
                );
              });
            },
          );
          final input = TextField(
            controller: _symbolController,
            textCapitalization: TextCapitalization.characters,
            decoration: const InputDecoration(
                labelText: 'Symbol', border: OutlineInputBorder()),
            onChanged: (_) => setState(() {}),
          );

          if (vertical) {
            return Column(children: [
              dropdown,
              const SizedBox(height: 10),
              input,
            ]);
          }
          return Row(children: [
            Expanded(child: dropdown),
            const SizedBox(width: 10),
            Expanded(child: input),
          ]);
        }),
        const SizedBox(height: 12),
        SegmentedButton<int>(
          segments: const [
            ButtonSegment(value: 1, label: Text('Gate 1')),
            ButtonSegment(value: 2, label: Text('Gate 2')),
            ButtonSegment(value: 3, label: Text('Gate 3')),
            ButtonSegment(value: 4, label: Text('Gate 4')),
          ],
          selected: {controller.selectedGateLevel},
          onSelectionChanged: (selection) =>
              controller.setSelectedGateLevel(selection.first),
        ),
        const SizedBox(height: 12),
        FilledButton.icon(
          onPressed: controller.manualRunLoading || symbol.isEmpty
              ? null
              : () async {
                  final result = await controller.runTradingOnce(
                      symbol: symbol, gateLevel: controller.selectedGateLevel);
                  if (!context.mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(result.message),
                    backgroundColor:
                        result.success ? Colors.green : Colors.redAccent,
                  ));
                },
          icon: controller.manualRunLoading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2.0))
              : const Icon(Icons.play_arrow),
          label: Text(controller.manualRunLoading
              ? 'Analyzing...'
              : 'Analyze & Paper Buy'),
        ),
        if (controller.manualRunLoading) ...[
          const SizedBox(height: 10),
          Row(children: [
            const SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(strokeWidth: 2.0)),
            const SizedBox(width: 10),
            Expanded(
                child: Text(
                    'Running trading check for ${controller.manualRunSymbol ?? symbol}...')),
          ]),
        ],
        if (controller.manualRunResult != null) ...[
          const SizedBox(height: 12),
          ManualTradingRunResultPanel(result: controller.manualRunResult!),
        ],
      ]),
    );
  }

  String get _normalizedSymbol => _symbolController.text.trim().toUpperCase();

}

class _SafetyBadge extends StatelessWidget {
  const _SafetyBadge({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    const color = Colors.orangeAccent;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.45)),
      ),
      child: Text(text,
          style: TextStyle(
              color: color, fontWeight: FontWeight.w700, fontSize: 12)),
    );
  }
}

class ManualTradingRunResultPanel extends StatelessWidget {
  const ManualTradingRunResultPanel({super.key, required this.result});

  final ManualTradingRunResult result;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.20),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('Decision Summary',
            style: TextStyle(fontWeight: FontWeight.w700)),
        const SizedBox(height: 12),
        _DecisionSummary(result: result),
        const SizedBox(height: 10),
        _WhyNoTradeSection(result: result),
        const SizedBox(height: 8),
        _ResultExpansion(
          title: 'Score Breakdown',
          initiallyExpanded: true,
          child: _ScoreBreakdown(result: result),
        ),
        _ResultExpansion(
          title: 'Run Details',
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            _ReasonDetails(result: result),
            if (result.gptContext.hasDetails) ...[
              const SizedBox(height: 10),
              const Text('GPT Risk Context',
                  style: TextStyle(fontWeight: FontWeight.w700)),
              const SizedBox(height: 6),
              GptRiskContextDetails(
                context: result.gptContext,
                title: 'GPT Risk Filter',
              ),
            ],
            if (result.indicatorPayload.isNotEmpty ||
                result.rawIndicatorPayload != null) ...[
              const SizedBox(height: 10),
              const Text('Indicator Details',
                  style: TextStyle(fontWeight: FontWeight.w700)),
              const SizedBox(height: 6),
              _IndicatorDetails(result: result),
            ],
            const SizedBox(height: 10),
            _ResultExpansion(
              title: 'Developer Raw Payload',
              child: _DeveloperRawPayload(result: result),
            ),
          ]),
        ),
      ]),
    );
  }
}

class _DecisionSummary extends StatelessWidget {
  const _DecisionSummary({required this.result});

  final ManualTradingRunResult result;

  @override
  Widget build(BuildContext context) {
    final action = result.action.toUpperCase();
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Wrap(spacing: 8, runSpacing: 8, children: [
        _DecisionBadge(text: action, color: _actionColor(action)),
        _DecisionBadge(
            text: result.displayStatus.toUpperCase(),
            color: _statusColor(result.displayStatus)),
        _DecisionBadge(
          text: result.riskAllowed ? 'RISK APPROVED' : 'RISK BLOCKED',
          color: result.riskAllowed ? Colors.greenAccent : Colors.redAccent,
        ),
        _DecisionBadge(
          text: result.noOrderCreated ? 'NO ORDER' : 'ORDER CREATED',
          color: result.noOrderCreated ? Colors.grey : Colors.greenAccent,
        ),
      ]),
      const SizedBox(height: 10),
      _ResultRow('Symbol', result.symbol),
      _ResultRow('Decision', result.action.toUpperCase()),
      _ResultRow('Result', result.displayStatus),
      _ResultRow('Risk approved',
          (result.approvedByRisk ?? result.riskApproved ?? false) ? 'Yes' : 'No'),
      _ResultRow('Order', result.displayOrderId),
      _ResultRow('Gate', result.gateLabel),
      if (result.createdAt != null) _ResultRow('Created at', result.createdAt!),
      if (result.signalId != null) _ResultRow('Signal ID', result.signalId!),
      if (result.brokerStatus != null)
        _ResultRow('Broker status', result.brokerStatus!),
      if (result.internalStatus != null)
        _ResultRow('Internal status', result.internalStatus!),
    ]);
  }

  Color _actionColor(String action) {
    if (action == 'BUY') return Colors.greenAccent;
    if (action == 'SELL') return Colors.deepOrangeAccent;
    if (action == 'HOLD') return Colors.amberAccent;
    return Colors.grey;
  }

  Color _statusColor(String status) {
    final normalized = status.toLowerCase();
    if (normalized.contains('executed') || normalized.contains('filled')) {
      return Colors.greenAccent;
    }
    if (normalized.contains('reject') || normalized.contains('error')) {
      return Colors.redAccent;
    }
    if (normalized.contains('skip') || normalized.contains('hold')) {
      return Colors.amberAccent;
    }
    return Colors.grey;
  }
}

class _WhyNoTradeSection extends StatelessWidget {
  const _WhyNoTradeSection({required this.result});

  final ManualTradingRunResult result;

  @override
  Widget build(BuildContext context) {
    if (!result.isHold &&
        result.signalStatus != 'skipped' &&
        !result.noOrderCreated) {
      return const SizedBox.shrink();
    }

    final explanations = <String>[];
    if (result.riskFlags.contains('hold_signal')) {
      explanations.add('The model selected HOLD, so no order was sent.');
    }
    if (result.gatingNotes.contains('score_threshold_not_met')) {
      explanations.add('The signal did not meet the minimum score threshold.');
    }
    if (result.approvedByRisk == false || result.riskApproved == false) {
      explanations.add('Risk engine did not approve an order.');
    }
    if (result.hardBlocked) {
      explanations.add(
          'Hard block active: ${result.hardBlockReason ?? 'unknown reason'}.');
    }
    if (result.noOrderCreated) {
      explanations.add('No order created.');
    }
    if (explanations.isEmpty && result.reason.isNotEmpty) {
      explanations.add(result.reason);
    }

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.amberAccent.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.amberAccent.withValues(alpha: 0.24)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('Why No Trade?',
            style: TextStyle(fontWeight: FontWeight.w700)),
        const SizedBox(height: 8),
        for (final explanation in explanations)
          Padding(
            padding: const EdgeInsets.only(bottom: 4),
            child: Text(explanation,
                style: const TextStyle(color: Colors.white70)),
          ),
        if (result.gatingNotes.isNotEmpty) ...[
          const SizedBox(height: 6),
          _ChipList(
              label: 'Gating notes',
              items: result.gatingNotes.map(_translateReason).toList()),
        ],
        if (result.riskFlags.isNotEmpty) ...[
          const SizedBox(height: 6),
          _ChipList(
              label: 'Risk flags',
              items: result.riskFlags.map(_translateReason).toList()),
        ],
      ]),
    );
  }
}

class _ScoreBreakdown extends StatelessWidget {
  const _ScoreBreakdown({required this.result});

  final ManualTradingRunResult result;

  @override
  Widget build(BuildContext context) {
    final metrics = <_MetricValue>[
      _MetricValue('Buy Score', _formatNullable(result.buyScore)),
      _MetricValue('Sell Score', _formatNullable(result.sellScore)),
      _MetricValue('Final Buy', _formatNullable(result.finalBuyScore)),
      _MetricValue('Final Sell', _formatNullable(result.finalSellScore)),
      _MetricValue('Confidence', _formatNullable(result.confidence)),
      _MetricValue('AI Buy', _formatNullable(result.aiBuyScore)),
      _MetricValue('AI Sell', _formatNullable(result.aiSellScore)),
      _MetricValue(
        'GPT Numeric Buy',
        _formatGptNumericScore(result.gptContext.gptBuyScore),
      ),
      _MetricValue(
        'GPT Numeric Sell',
        _formatGptNumericScore(result.gptContext.gptSellScore),
      ),
      _MetricValue('Action', result.action.toUpperCase()),
      _MetricValue('Reason', _textOrDash(_translateReason(result.reason))),
      _MetricValue('Hard block', result.hardBlocked ? 'Yes' : 'No'),
    ];
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      if (result.scoreDetailsNotReturned) ...[
        const Text('Score details not returned in run response',
            style: TextStyle(
                color: Colors.orangeAccent, fontWeight: FontWeight.w700)),
        const SizedBox(height: 8),
      ],
      Wrap(
        spacing: 8,
        runSpacing: 8,
        children: metrics
            .map((metric) =>
                _MiniMetricCard(label: metric.label, value: metric.value))
            .toList(),
      ),
      if (result.hardBlockReason != null) ...[
        const SizedBox(height: 8),
        _ResultRow(
            'Hard block reason', _translateReason(result.hardBlockReason!)),
      ],
      if (result.gptContext.reason?.isNotEmpty == true) ...[
        const SizedBox(height: 8),
        _ResultRow('GPT Advisory Reason', result.gptContext.reason!),
      ],
      if (result.riskFlags.isNotEmpty) ...[
        const SizedBox(height: 8),
        _ChipList(
            label: 'Risk flags',
            items: result.riskFlags.map(_translateReason).toList()),
      ],
      if (result.gatingNotes.isNotEmpty) ...[
        const SizedBox(height: 8),
        _ChipList(
            label: 'Gating notes',
            items: result.gatingNotes.map(_translateReason).toList()),
      ],
    ]);
  }
}

class _ReasonDetails extends StatelessWidget {
  const _ReasonDetails({required this.result});

  final ManualTradingRunResult result;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      _ResultRow('Main reason',
          result.reason.isEmpty ? 'No reason returned' : _translateReason(result.reason)),
      _ResultRow('Quant reason', result.quantReason ?? 'No quant reason returned'),
      _ResultRow('AI reason', result.aiReason ?? 'No AI reason returned'),
      if (result.runReason != null)
        _ResultRow('Run reason', _translateReason(result.runReason!)),
      if (result.hardBlockReason != null)
        _ResultRow('Hard block', _translateReason(result.hardBlockReason!)),
    ]);
  }
}

class _IndicatorDetails extends StatelessWidget {
  const _IndicatorDetails({required this.result});

  final ManualTradingRunResult result;

  @override
  Widget build(BuildContext context) {
    final indicators = result.indicatorPayload;
    if (indicators.isEmpty && result.rawIndicatorPayload != null) {
      return const Text(
        'Indicator payload returned only as raw data. Open Developer Raw Payload for the raw value.',
        style: TextStyle(color: Colors.white70),
      );
    }

    final rows = <_ResultRow>[
      _indicatorRow(indicators, 'price', decimals: 2),
      _indicatorRow(indicators, 'ema20', decimals: 2),
      _indicatorRow(indicators, 'ema50', decimals: 2),
      _indicatorRow(indicators, 'rsi', decimals: 1),
      _indicatorRow(indicators, 'vwap', decimals: 2),
      _indicatorRow(indicators, 'atr', decimals: 2),
      _indicatorRow(indicators, 'volume_ratio', decimals: 2),
      _indicatorRow(indicators, 'short_momentum', percent: true),
      _indicatorRow(indicators, 'day_open', decimals: 2),
      _indicatorRow(indicators, 'previous_high', decimals: 2),
      _indicatorRow(indicators, 'previous_low', decimals: 2),
    ];

    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: rows);
  }

  _ResultRow _indicatorRow(Map<String, dynamic> indicators, String key,
      {int decimals = 2, bool percent = false}) {
    final value = indicators[key];
    final numericValue = value is num
        ? value.toDouble()
        : double.tryParse(value?.toString() ?? '');
    if (numericValue == null)
      return _ResultRow(key, value?.toString() ?? 'n/a');
    if (percent)
      return _ResultRow(key, '${(numericValue * 100).toStringAsFixed(2)}%');
    return _ResultRow(key, numericValue.toStringAsFixed(decimals));
  }
}

class _DeveloperRawPayload extends StatelessWidget {
  const _DeveloperRawPayload({required this.result});

  final ManualTradingRunResult result;

  @override
  Widget build(BuildContext context) {
    return SelectableText(
      'symbol=${result.symbol}\n'
      'gate_level=${result.gateLevel}\n'
      'action=${result.action}\n'
      'result=${result.result}\n'
      'signal_status=${result.signalStatus}\n'
      'risk_flags=${result.riskFlags}\n'
      'gating_notes=${result.gatingNotes}\n'
      'indicator_payload=${result.indicatorPayload}\n'
      'raw_indicator_payload=${result.rawIndicatorPayload}\n'
      'gpt_context=${result.gptContext}',
      style: const TextStyle(color: Colors.white60),
    );
  }
}

class _ResultExpansion extends StatelessWidget {
  const _ResultExpansion({
    required this.title,
    required this.child,
    this.initiallyExpanded = false,
  });

  final String title;
  final Widget child;
  final bool initiallyExpanded;

  @override
  Widget build(BuildContext context) {
    return Theme(
      data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
      child: ExpansionTile(
        tilePadding: EdgeInsets.zero,
        childrenPadding: const EdgeInsets.only(bottom: 8),
        initiallyExpanded: initiallyExpanded,
        title: Text(title, style: const TextStyle(fontWeight: FontWeight.w700)),
        children: [child],
      ),
    );
  }
}

class _DecisionBadge extends StatelessWidget {
  const _DecisionBadge({required this.text, required this.color});

  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.42)),
      ),
      child: Text(text,
          style: TextStyle(
              color: color, fontSize: 11, fontWeight: FontWeight.w800)),
    );
  }
}

class _MiniMetricCard extends StatelessWidget {
  const _MiniMetricCard({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 116,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label.toUpperCase(),
            style: const TextStyle(
                color: Colors.white60,
                fontSize: 10,
                fontWeight: FontWeight.w700)),
        const SizedBox(height: 4),
        Text(value, style: const TextStyle(fontWeight: FontWeight.w800)),
      ]),
    );
  }
}

class _ChipList extends StatelessWidget {
  const _ChipList({required this.label, required this.items});

  final String label;
  final List<String> items;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(label, style: const TextStyle(color: Colors.white70, fontSize: 12)),
      const SizedBox(height: 4),
      Wrap(
        spacing: 6,
        runSpacing: 6,
        children: [
          for (final item in items)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: 0.07),
                borderRadius: BorderRadius.circular(999),
                border: Border.all(color: Colors.white.withValues(alpha: 0.14)),
              ),
              child: Text(item, style: const TextStyle(fontSize: 11)),
            )
        ],
      ),
    ]);
  }
}

class _MetricValue {
  const _MetricValue(this.label, this.value);

  final String label;
  final String value;
}

class _ResultRow extends StatelessWidget {
  const _ResultRow(this.label, this.value);

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 5),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SizedBox(
            width: 108,
            child: Text(label, style: const TextStyle(color: Colors.white70))),
        Expanded(child: SelectableText(value)),
      ]),
    );
  }
}

String _formatNullable(double? value) {
  if (value == null) return '--';
  return value.toStringAsFixed(2);
}

String _formatGptNumericScore(double? value) {
  if (value == null) return 'No numeric GPT score returned';
  return _formatNullable(value);
}

String _textOrDash(String value) {
  final text = value.trim();
  return text.isEmpty || text == 'null' ? '--' : text;
}

String _translateReason(String value) {
  final normalized = value.trim().toLowerCase();
  if (normalized == 'score_threshold_not_met') {
    return 'Score below entry threshold';
  }
  if (normalized == 'hard_blocked') return 'Entry blocked by risk context';
  if (normalized == 'gpt_hard_block_new_buy') {
    return 'GPT/risk context blocks new buy entries';
  }
  if (normalized == 'market_closed') return 'Market is closed';
  if (normalized == 'dry_run') return 'Dry-run mode';
  if (normalized == 'kill_switch_enabled') return 'Kill switch is ON';
  if (normalized == 'buy_entry_not_allowed_now') {
    return 'New buy entries are not allowed now';
  }
  return value;
}
