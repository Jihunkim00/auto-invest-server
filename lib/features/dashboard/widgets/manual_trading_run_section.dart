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
  static const _fallbackKrSymbols = <String>['005930', '000660', '035420'];

  late final TextEditingController _symbolController;
  PortfolioMarket _market = PortfolioMarket.us;
  String? _lastPreparedKisSymbol;

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
    final symbols = _symbolsForMarket(controller);
    final dropdownValue = symbols.contains(symbol) ? symbol : null;
    final isKis = _market == PortfolioMarket.kr;

    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.play_circle_outline, size: 20),
          const SizedBox(width: 8),
          Text('Single Symbol Trading',
              style: Theme.of(context).textTheme.titleMedium),
        ]),
        const SizedBox(height: 12),
        SegmentedButton<PortfolioMarket>(
          segments: const [
            ButtonSegment(
              value: PortfolioMarket.us,
              label: Text('Alpaca Paper / US'),
              icon: Icon(Icons.public, size: 16),
            ),
            ButtonSegment(
              value: PortfolioMarket.kr,
              label: Text('KIS / KR'),
              icon: Icon(Icons.account_balance, size: 16),
            ),
          ],
          selected: {_market},
          onSelectionChanged: (selection) =>
              _setMarket(selection.first, controller),
        ),
        const SizedBox(height: 10),
        _ModeHelp(isKis: isKis),
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
        isKis
            ? FilledButton.icon(
                onPressed: symbol.isEmpty
                    ? null
                    : () {
                        final result =
                            controller.prepareKisManualBuyTicketFromSymbol(
                          symbol,
                          gateLevel: controller.selectedGateLevel,
                        );
                        if (result.success) {
                          setState(() => _lastPreparedKisSymbol = symbol);
                          widget.onOpenManualOrder?.call();
                        }
                        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                          content: Text(result.message),
                          backgroundColor:
                              result.success ? Colors.green : Colors.redAccent,
                        ));
                      },
                icon: const Icon(Icons.input),
                label: const Text('Prepare Buy Ticket'),
              )
            : FilledButton.icon(
                onPressed: controller.manualRunLoading || symbol.isEmpty
                    ? null
                    : () async {
                        final confirmed = await _showConfirmDialog(
                            context, symbol, controller.selectedGateLevel);
                        if (!confirmed || !context.mounted) return;

                        final result = await controller.runTradingOnce(
                            symbol: symbol,
                            gateLevel: controller.selectedGateLevel);
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
                    ? 'Running single symbol...'
                    : 'Run Single Symbol'),
              ),
        if (!isKis && controller.manualRunLoading) ...[
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
        if (!isKis && controller.manualRunResult != null) ...[
          const SizedBox(height: 12),
          _ManualRunResultPanel(result: controller.manualRunResult!),
        ],
        if (isKis &&
            _lastPreparedKisSymbol != null &&
            controller.orderTicketSourceMetadata?['source'] ==
                'single_symbol_trading') ...[
          const SizedBox(height: 12),
          _KisPreparedTicketPanel(
            symbol: _lastPreparedKisSymbol!,
            gateLevel: controller.selectedGateLevel,
          ),
        ],
      ]),
    );
  }

  String get _normalizedSymbol => _symbolController.text.trim().toUpperCase();

  List<String> _symbolsForMarket(DashboardController controller) {
    if (_market == PortfolioMarket.us) return _usSymbols;
    final symbols = controller.krWatchlist.symbols
        .map((item) => item.symbol.trim().toUpperCase())
        .where((symbol) => symbol.isNotEmpty)
        .toList();
    if (symbols.isEmpty) return _fallbackKrSymbols;
    for (final symbol in _fallbackKrSymbols) {
      if (!symbols.contains(symbol)) symbols.add(symbol);
    }
    return symbols;
  }

  void _setMarket(PortfolioMarket market, DashboardController controller) {
    if (_market == market) return;
    setState(() {
      _market = market;
      final nextSymbol = _symbolsForMarket(controller).first;
      _symbolController.value = TextEditingValue(
        text: nextSymbol,
        selection: TextSelection.collapsed(offset: nextSymbol.length),
      );
    });
  }

  Future<bool> _showConfirmDialog(
      BuildContext context, String symbol, int gateLevel) async {
    final settings = widget.controller.settings;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: const Text('Confirm Manual Trading Run'),
          content: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'This will run trading logic for one selected symbol only.\n'
                  'The risk engine will still decide whether an order is allowed.\n'
                  'No order is guaranteed.\n'
                  'Continue?',
                ),
                const SizedBox(height: 14),
                _ConfirmRow(label: 'symbol', value: symbol),
                _ConfirmRow(label: 'gate_level', value: gateLevel.toString()),
                _ConfirmRow(label: 'broker mode', value: settings.brokerMode),
                _ConfirmRow(
                    label: 'dry_run', value: settings.dryRun.toString()),
                _ConfirmRow(
                    label: 'kill_switch',
                    value: settings.killSwitch.toString()),
                if (settings.dryRun || settings.killSwitch) ...[
                  const SizedBox(height: 10),
                  Wrap(spacing: 8, runSpacing: 8, children: [
                    if (settings.dryRun)
                      const _SafetyBadge(
                          text: 'Dry Run - broker order will be blocked.'),
                    if (settings.killSwitch)
                      const _SafetyBadge(
                          text: 'Kill Switch Active - order blocked.',
                          alert: true),
                  ]),
                ],
              ]),
          actions: [
            TextButton(
                onPressed: () => Navigator.of(context).pop(false),
                child: const Text('Cancel')),
            FilledButton(
                onPressed: () => Navigator.of(context).pop(true),
                child: const Text('Continue')),
          ],
        );
      },
    );
    return confirmed == true;
  }
}

class _ModeHelp extends StatelessWidget {
  const _ModeHelp({required this.isKis});

  final bool isKis;

  @override
  Widget build(BuildContext context) {
    final labels = isKis
        ? const [
            'Manual Order only',
            'No KIS live submit here',
            'confirm_live remains unchecked',
          ]
        : const [
            'Uses existing risk engine',
            'Paper order may be created if risk-approved',
            'HOLD is normal',
          ];
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        for (final label in labels) _SafetyBadge(text: label),
      ],
    );
  }
}

class _ConfirmRow extends StatelessWidget {
  const _ConfirmRow({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Row(children: [
        SizedBox(
            width: 92,
            child: Text(label, style: const TextStyle(color: Colors.white70))),
        Expanded(
            child: Text(value,
                style: const TextStyle(fontWeight: FontWeight.w700))),
      ]),
    );
  }
}

class _SafetyBadge extends StatelessWidget {
  const _SafetyBadge({required this.text, this.alert = false});

  final String text;
  final bool alert;

  @override
  Widget build(BuildContext context) {
    final color = alert ? Colors.redAccent : Colors.orangeAccent;
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

class _ManualRunResultPanel extends StatelessWidget {
  const _ManualRunResultPanel({required this.result});

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
        const Text('Result Summary',
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
          title: 'Advanced Details',
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
      _ResultRow('symbol', result.symbol),
      _ResultRow('action', result.action.toLowerCase()),
      _ResultRow('signal status', result.displayStatus),
      _ResultRow('approved_by_risk',
          (result.approvedByRisk ?? result.riskApproved ?? false).toString()),
      _ResultRow('order', result.displayOrderId),
      _ResultRow('gate', result.gateLabel),
      if (result.createdAt != null) _ResultRow('created_at', result.createdAt!),
      if (result.signalId != null) _ResultRow('signal_id', result.signalId!),
      if (result.brokerStatus != null)
        _ResultRow('broker_status', result.brokerStatus!),
      if (result.internalStatus != null)
        _ResultRow('internal_status', result.internalStatus!),
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
          _ChipList(label: 'Gating notes', items: result.gatingNotes),
        ],
        if (result.riskFlags.isNotEmpty) ...[
          const SizedBox(height: 6),
          _ChipList(label: 'Risk flags', items: result.riskFlags),
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
      _MetricValue('Reason', _textOrDash(result.reason)),
      _MetricValue('Hard block', result.hardBlocked ? 'true' : 'false'),
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
        _ResultRow('hard_block_reason', result.hardBlockReason!),
      ],
      if (result.gptContext.reason?.isNotEmpty == true) ...[
        const SizedBox(height: 8),
        _ResultRow('GPT Advisory Reason', result.gptContext.reason!),
      ],
      if (result.riskFlags.isNotEmpty) ...[
        const SizedBox(height: 8),
        _ChipList(label: 'Risk flags', items: result.riskFlags),
      ],
      if (result.gatingNotes.isNotEmpty) ...[
        const SizedBox(height: 8),
        _ChipList(label: 'Gating notes', items: result.gatingNotes),
      ],
    ]);
  }
}

class _KisPreparedTicketPanel extends StatelessWidget {
  const _KisPreparedTicketPanel({
    required this.symbol,
    required this.gateLevel,
  });

  final String symbol;
  final int gateLevel;

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
        const Text('Result Summary',
            style: TextStyle(fontWeight: FontWeight.w700)),
        const SizedBox(height: 10),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _DecisionBadge(text: 'BUY TICKET', color: Colors.lightBlueAccent),
          _DecisionBadge(text: 'MANUAL REVIEW', color: Colors.amberAccent),
          _DecisionBadge(text: 'NO SUBMIT', color: Colors.greenAccent),
        ]),
        const SizedBox(height: 10),
        _ResultRow('symbol', symbol),
        const _ResultRow('action', 'buy'),
        const _ResultRow('signal status', 'manual_review'),
        const _ResultRow('approved_by_risk', 'false'),
        const _ResultRow('order', 'No order created'),
        _ResultRow('gate', 'Gate $gateLevel'),
        const SizedBox(height: 8),
        const Text(
          'KIS live submit is only available from Manual Order after validation and an explicit confirm_live check.',
          style: TextStyle(color: Colors.white70),
        ),
      ]),
    );
  }
}

class _ReasonDetails extends StatelessWidget {
  const _ReasonDetails({required this.result});

  final ManualTradingRunResult result;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      _ResultRow('reason', result.reason.isEmpty ? 'none' : result.reason),
      _ResultRow('quant_reason', result.quantReason ?? 'none'),
      _ResultRow('ai_reason', result.aiReason ?? 'none'),
      if (result.runReason != null) _ResultRow('run.reason', result.runReason!),
      if (result.hardBlockReason != null)
        _ResultRow('hard_block', result.hardBlockReason!),
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
      return SelectableText(result.rawIndicatorPayload!);
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
