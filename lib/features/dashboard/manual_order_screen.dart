import 'dart:convert';

import 'package:flutter/material.dart';

import '../../core/i18n/app_strings.dart';
import '../../core/widgets/section_card.dart';
import '../../models/kis_single_symbol_trading_result.dart';
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
                    AppStrings.t(AppTextKey.trading, controller.uiLanguage),
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
        !controller.kisSingleSymbolTradingLoading;
    final result = controller.latestKisSingleSymbolTradingResult;

    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.verified_user_outlined, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text(AppStrings.t(AppTextKey.kisAnalyzeBuy, controller.uiLanguage),
                style: Theme.of(context).textTheme.titleMedium),
          ),
          const _SoftBadge(text: 'KIS LIVE', color: Colors.redAccent),
        ]),
        const SizedBox(height: 12),
        TextField(
          controller: _symbolController,
          decoration: const InputDecoration(
            labelText: AppStrings.t(AppTextKey.krSymbol, controller.uiLanguage),
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
            labelText: AppStrings.t(AppTextKey.quantity, controller.uiLanguage),
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
          onChanged: controller.kisSingleSymbolTradingLoading
              ? null
              : (value) =>
                  controller.setKisGuardedRunConfirmation(value == true),
          title: Text(AppStrings.t(AppTextKey.kisCheckbox, controller.uiLanguage)),
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
                    confirmLive: controller.kisGuardedRunConfirmation,
                  );
                  if (!context.mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(actionResult.message),
                    backgroundColor:
                        actionResult.success ? Colors.green : Colors.redAccent,
                  ));
                }
              : null,
          icon: controller.kisSingleSymbolTradingLoading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.play_arrow),
          label: Text(controller.kisSingleSymbolTradingLoading
              ? 'Analyzing...'
              : AppStrings.t(AppTextKey.kisAnalyzeBuy, controller.uiLanguage)),
        ),
        if (!canRequest) ...[
          const SizedBox(height: 8),
          _ReasonBanner(
            text: controller.kisGuardedRunConfirmation
                ? 'Enter a KR symbol and quantity.'
                : 'Confirm that a real KIS order may be submitted.',
          ),
        ],
        if (controller.kisSingleSymbolTradingError != null) ...[
          const SizedBox(height: 10),
          _ReasonBanner(
            text: controller.kisSingleSymbolTradingError!,
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
        title: Text(AppStrings.t(AppTextKey.kisConfirmTitle, controller.uiLanguage)),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(AppStrings.t(AppTextKey.kisConfirmBody, controller.uiLanguage)),
            const SizedBox(height: 12),
            _DialogRow(label: '종목', value: symbol),
            _DialogRow(label: '수량/금액', value: qty.toString()),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: Text(AppStrings.t(AppTextKey.cancel, controller.uiLanguage)),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: Text(AppStrings.t(AppTextKey.confirm, controller.uiLanguage)),
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

  final KisSingleSymbolTradingResult result;
  final String selectedSymbol;

  @override
  Widget build(BuildContext context) {
    final mismatch = presentation.selectedSymbolMismatch(
      selectedSymbol: selectedSymbol,
      returnedSymbol: result.analyzedSymbol ?? result.returnedSymbol,
    );
    final analysisStatus = _analysisStatus(result);
    final order = _orderLabel(result);
    final mainReason = _mainReason(result);
    final secondaryBlockers = _secondaryBlockers(result, mainReason);
    final cashShortfall = result.cashShortfall;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('Analysis Status',
            style: TextStyle(fontWeight: FontWeight.w800)),
        const SizedBox(height: 8),
        _ReasonBanner(
          text: analysisStatus,
          color: _analysisStatusColor(analysisStatus),
        ),
        const SizedBox(height: 12),
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
          _DataPairData(label: 'Order', value: order),
        ]),
        const SizedBox(height: 12),
        const Text('Score vs Threshold',
            style: TextStyle(fontWeight: FontWeight.w800)),
        const SizedBox(height: 8),
        _DataGrid(pairs: [
          _DataPairData(
              label: 'Buy Score',
              value: _displaySignalScore(result.finalBuyScore)),
          _DataPairData(
              label: 'Required Score',
              value: presentation.displayScore(result.effectiveMinEntryScore,
                  fallback: 'Threshold not returned')),
          _DataPairData(
              label: 'Sell Score',
              value: _displaySignalScore(result.finalSellScore)),
          _DataPairData(
              label: 'Confidence',
              value: presentation.displayScore(result.confidence,
                  fallback: 'Confidence not returned')),
        ]),
        const SizedBox(height: 12),
        const Text('Main Reason',
            style: TextStyle(fontWeight: FontWeight.w800)),
        const SizedBox(height: 8),
        _ReasonBanner(text: mainReason, color: Colors.amberAccent),
        if (cashShortfall != null) ...[
          const SizedBox(height: 12),
          const Text('Cash Check',
              style: TextStyle(fontWeight: FontWeight.w800)),
          const SizedBox(height: 8),
          _DataGrid(pairs: [
            _DataPairData(
              label: 'Available cash',
              value: _moneyLabel(result.availableCash),
            ),
            _DataPairData(
              label: 'Estimated amount',
              value: _moneyLabel(result.estimatedOrderAmount),
            ),
            _DataPairData(
              label: 'Cash shortfall',
              value: _moneyLabel(cashShortfall),
            ),
          ]),
        ],
        const SizedBox(height: 12),
        const Text('Technical Snapshot',
            style: TextStyle(fontWeight: FontWeight.w800)),
        const SizedBox(height: 8),
        _DataGrid(pairs: [
          _DataPairData(
              label: 'Current price',
              value: presentation.displayScore(result.currentPrice,
                  fallback: 'Price not returned')),
          _DataPairData(
              label: 'EMA20 relation', value: _emaRelation(result, 20)),
          _DataPairData(
              label: 'EMA50 relation', value: _emaRelation(result, 50)),
          _DataPairData(label: 'VWAP relation', value: _vwapRelation(result)),
          _DataPairData(label: 'RSI', value: _rsiLabel(result)),
          _DataPairData(label: 'Momentum', value: _momentumLabel(result)),
          _DataPairData(
              label: 'Volume ratio', value: _volumeRatioLabel(result)),
          _DataPairData(
              label: 'Recent return', value: _recentReturnLabel(result)),
        ]),
        const SizedBox(height: 12),
        const Text('Why No Order?',
            style: TextStyle(fontWeight: FontWeight.w800)),
        const SizedBox(height: 8),
        _DataGrid(pairs: [
          _DataPairData(label: 'Order', value: order),
          _DataPairData(label: 'Main blocker', value: mainReason),
          _DataPairData(label: 'Next action', value: _nextAction(result)),
        ]),
        if (secondaryBlockers.isNotEmpty) ...[
          const SizedBox(height: 8),
          _BulletList(title: 'Secondary blockers', items: secondaryBlockers),
        ],
        const SizedBox(height: 12),
        const Text('Order Submission',
            style: TextStyle(fontWeight: FontWeight.w800)),
        const SizedBox(height: 8),
        _DataGrid(pairs: [
          _DataPairData(
            label: 'Real order submitted',
            value: result.realOrderSubmitted ? 'Yes' : 'No',
          ),
          _DataPairData(
            label: 'Broker submit called',
            value: result.brokerSubmitCalled ? 'Yes' : 'No',
          ),
          _DataPairData(
            label: 'Manual submit called',
            value: result.manualSubmitCalled ? 'Yes' : 'No',
          ),
          _DataPairData(
            label: 'Order ID',
            value: result.orderId?.toString() ?? 'No order created',
          ),
          _DataPairData(
            label: 'KIS ODNO',
            value: result.kisOdno ?? 'No order created',
          ),
        ]),
        const SizedBox(height: 8),
        ExpansionTile(
          tilePadding: EdgeInsets.zero,
          childrenPadding: EdgeInsets.zero,
          title: const Text('Developer Raw Payload'),
          children: [
            _ReasonBanner(
              text:
                  const JsonEncoder.withIndent('  ').convert(result.rawPayload),
            ),
          ],
        ),
      ]),
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

String _mainReason(KisSingleSymbolTradingResult result) {
  if (_hasReasonCode(result, 'insufficient_cash') ||
      result.cashShortfall != null) {
    return presentation.translateReason(
      'insufficient_cash',
      singleSymbolContext: true,
    );
  }
  if (_analysisUnavailableBecauseData(result)) {
    return presentation.translateReason(
      'insufficient_data',
      singleSymbolContext: true,
    );
  }
  final buyScore = result.finalBuyScore;
  final requiredScore = result.effectiveMinEntryScore;
  if (buyScore != null && requiredScore != null && buyScore < requiredScore) {
    return presentation.translateReason(
      'score_threshold_not_met',
      singleSymbolContext: true,
    );
  }
  final technicalReason = _technicalMainReason(result);
  if (technicalReason != null) return technicalReason;
  for (final reason in _reasonCandidates(result)) {
    final translated = _translateSingleSymbolReason(reason);
    if (_isReadableSummaryText(translated)) return translated;
  }
  if (result.safetyFlag('runtime_dry_run') || result.safetyFlag('dry_run')) {
    return presentation.translateReason('dry_run', singleSymbolContext: true);
  }
  return 'Backend risk gate blocked this order';
}

String _decisionLabel(KisSingleSymbolTradingResult result) {
  final action = result.action.trim().toLowerCase();
  if (action == 'buy') return 'BUY';
  if (action == 'hold') return 'HOLD';
  if (_analysisStatus(result) == 'Blocked before analysis') return 'BLOCKED';
  final resultText = result.result.trim().toLowerCase();
  if (resultText.contains('block')) return 'BLOCKED';
  return 'HOLD';
}

String _resultLabel(KisSingleSymbolTradingResult result) {
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

String _nextAction(KisSingleSymbolTradingResult result) {
  if (result.realOrderSubmitted) return 'Monitor and sync order status';
  if (result.safetyFlag('runtime_dry_run') || result.safetyFlag('dry_run')) {
    return 'Dry-run mode: no real order submitted';
  }
  if (_analysisUnavailableBecauseData(result)) {
    return 'Refresh KIS OHLCV data and run analysis again';
  }
  if (result.finalBuyScore != null &&
      result.effectiveMinEntryScore != null &&
      result.finalBuyScore! < result.effectiveMinEntryScore!) {
    return 'Wait for setup to improve before submitting a buy';
  }
  return _mainReason(result);
}

String _analysisStatus(KisSingleSymbolTradingResult result) {
  final indicatorStatus = result.indicatorStatus?.trim().toLowerCase() ?? '';
  if (indicatorStatus == 'ok' || result.finalBuyScore != null) {
    return 'Analysis completed';
  }
  if (_blockedBeforeAnalysis(result)) return 'Blocked before analysis';
  if (_analysisUnavailableBecauseData(result)) return 'Analysis unavailable';
  return 'Analysis unavailable';
}

Color _analysisStatusColor(String status) {
  if (status == 'Analysis completed') return Colors.greenAccent;
  if (status == 'Blocked before analysis') return Colors.amberAccent;
  return Colors.redAccent;
}

bool _analysisUnavailableBecauseData(KisSingleSymbolTradingResult result) {
  final indicatorStatus = result.indicatorStatus?.trim().toLowerCase() ?? '';
  return result.buyScore == null &&
      result.finalBuyScore == null &&
      result.confidence == null &&
      _indicatorMissingOrError(indicatorStatus);
}

bool _indicatorMissingOrError(String status) {
  return status.isEmpty ||
      status == 'missing' ||
      status == 'error' ||
      status == 'insufficient_data' ||
      status == 'price_only';
}

bool _blockedBeforeAnalysis(KisSingleSymbolTradingResult result) {
  if (result.finalBuyScore != null || result.confidence != null) return false;
  final codes = _reasonCandidates(result).map((item) => item.toLowerCase());
  return codes.any((code) =>
      code == 'market_closed' ||
      code == 'after_no_new_entry_time' ||
      code == 'near_close' ||
      code == 'buy_entry_not_allowed_now' ||
      code == 'kill_switch_enabled' ||
      code == 'kis_disabled' ||
      code == 'kis_real_order_disabled' ||
      code == 'confirm_live_required');
}

String _orderLabel(KisSingleSymbolTradingResult result) {
  final normalized = result.result.trim().toLowerCase();
  if (result.realOrderSubmitted || normalized == 'submitted') {
    return 'Real order submitted';
  }
  if (normalized.contains('dry') ||
      result.safetyFlag('runtime_dry_run') ||
      result.safetyFlag('dry_run')) {
    return 'Dry-run, no real order';
  }
  return 'No order created';
}

List<String> _secondaryBlockers(
  KisSingleSymbolTradingResult result,
  String mainReason,
) {
  final blockers = <String>[];
  for (final reason in _reasonCandidates(result)) {
    final translated = _translateSingleSymbolReason(reason);
    if (!_isReadableSummaryText(translated)) continue;
    if (translated == mainReason || blockers.contains(translated)) continue;
    blockers.add(translated);
    if (blockers.length >= 5) break;
  }
  return blockers;
}

List<String> _reasonCandidates(KisSingleSymbolTradingResult result) {
  final values = <String?>[
    _nestedString(result.rawPayload, const ['readiness', 'block_reason']),
    result.noOrderReason,
    result.blockReason,
    result.reason,
    ...result.validationBlockReasons,
    ...result.validationWarnings,
    ..._nestedStringList(result.rawPayload, const ['validation', 'warnings']),
    ..._nestedStringList(
        result.rawPayload, const ['validation', 'block_reasons']),
  ];
  final marketSession = _nestedMap(result.rawPayload, const ['market_session']);
  if (marketSession['is_near_close'] == true) values.add('near_close');
  if (marketSession['is_entry_allowed_now'] == false) {
    values.add('after_no_new_entry_time');
  }
  values.addAll(result.riskFlags);
  values.addAll(result.gatingNotes);
  return values
      .map((value) => value?.trim() ?? '')
      .where((value) => value.isNotEmpty && value != 'null')
      .toList(growable: false);
}

String _translateSingleSymbolReason(String reason) {
  final translated = presentation.translateReason(
    reason,
    singleSymbolContext: true,
  );
  if (_looksLikeRawReasonCode(translated))
    return _humanizeReasonCode(translated);
  return translated;
}

bool _hasReasonCode(KisSingleSymbolTradingResult result, String code) {
  final normalizedCode = code.trim().toLowerCase();
  return _reasonCandidates(result)
      .map((reason) => reason.trim().toLowerCase())
      .contains(normalizedCode);
}

bool _looksLikeRawReasonCode(String value) {
  return RegExp(r'^[A-Za-z0-9_-]+$').hasMatch(value);
}

String _humanizeReasonCode(String value) {
  final words = value
      .replaceAll('-', '_')
      .split('_')
      .where((part) => part.isNotEmpty)
      .map((part) => part.toLowerCase())
      .toList();
  if (words.isEmpty) return value;
  final text = words.join(' ');
  return text[0].toUpperCase() + text.substring(1);
}

bool _isReadableSummaryText(String value) {
  final text = value.trim();
  if (text.isEmpty || text == 'Not available') return false;
  final hasReplacementOrControl = text.runes
      .any((code) => code == 0xfffd || (code >= 0x80 && code <= 0x9f));
  final hasMojibakeMarkers =
      RegExp(r'[\u00c2\u00c3\u00ea\u00eb\u00ec]').hasMatch(text);
  return !hasReplacementOrControl && !hasMojibakeMarkers;
}

String? _technicalMainReason(KisSingleSymbolTradingResult result) {
  final below = [
    if (_isBelow(result, 'ema20', 'below_EMA20')) 'EMA20',
    if (_isBelow(result, 'ema50', 'below_EMA50')) 'EMA50',
    if (_isBelow(result, 'vwap', 'below_VWAP')) 'VWAP',
  ];
  if (below.length >= 2) {
    return 'Weak setup: price below ${below.join(' / ')}';
  }
  final rsi = _numberValue(result.indicatorPayload['rsi']);
  final hasOverboughtFlag =
      result.riskFlags.any((flag) => flag.toLowerCase() == 'overbought_rsi');
  if ((rsi != null && rsi >= 70) || hasOverboughtFlag) {
    return 'Overbought setup: chase risk';
  }
  return null;
}

bool _isBelow(KisSingleSymbolTradingResult result, String key, String flag) {
  final price = _snapshotPrice(result);
  final value = _numberValue(result.indicatorPayload[key]);
  if (price != null && value != null) return price < value;
  return result.riskFlags
      .any((item) => item.toLowerCase() == flag.toLowerCase());
}

String _emaRelation(KisSingleSymbolTradingResult result, int period) {
  return _priceRelation(result, 'ema$period', 'EMA$period');
}

String _vwapRelation(KisSingleSymbolTradingResult result) {
  return _priceRelation(result, 'vwap', 'VWAP');
}

String _priceRelation(
  KisSingleSymbolTradingResult result,
  String key,
  String label,
) {
  final price = _snapshotPrice(result);
  final value = _numberValue(result.indicatorPayload[key]);
  if (price != null && value != null) {
    return price >= value ? 'Price above $label' : 'Price below $label';
  }
  final normalized = label.toLowerCase();
  if (result.riskFlags
      .any((flag) => flag.toLowerCase() == 'below_$normalized')) {
    return 'Price below $label';
  }
  if (result.riskFlags
      .any((flag) => flag.toLowerCase() == 'above_$normalized')) {
    return 'Price above $label';
  }
  return 'Indicator not returned';
}

String _rsiLabel(KisSingleSymbolTradingResult result) {
  final rsi = _numberValue(result.indicatorPayload['rsi']);
  if (rsi == null) {
    if (result.riskFlags.any((flag) => flag.toLowerCase() == 'oversold_rsi')) {
      return 'RSI oversold';
    }
    if (result.riskFlags
        .any((flag) => flag.toLowerCase() == 'overbought_rsi')) {
      return 'RSI overbought';
    }
    return 'Indicator not returned';
  }
  final suffix = ' (${_formatDecimal(rsi)})';
  if (rsi <= 30) return 'RSI oversold$suffix';
  if (rsi >= 70) return 'RSI overbought$suffix';
  return 'RSI neutral$suffix';
}

String _momentumLabel(KisSingleSymbolTradingResult result) {
  final momentum = _numberValue(result.indicatorPayload['momentum'] ??
      result.indicatorPayload['short_momentum']);
  if (momentum == null) {
    if (result.riskFlags
        .any((flag) => flag.toLowerCase() == 'negative_momentum')) {
      return 'Momentum negative';
    }
    return 'Indicator not returned';
  }
  if (momentum < 0) return 'Momentum negative (${_formatPercent(momentum)})';
  if (momentum > 0) return 'Momentum positive (${_formatPercent(momentum)})';
  return 'Momentum flat';
}

String _volumeRatioLabel(KisSingleSymbolTradingResult result) {
  final volumeRatio = _numberValue(result.indicatorPayload['volume_ratio']);
  if (volumeRatio == null) return 'Indicator not returned';
  final formatted = '${_formatDecimal(volumeRatio)}x';
  if (volumeRatio < 0.8) return 'Volume weak ($formatted)';
  if (volumeRatio > 1.2) return 'Volume strong ($formatted)';
  return 'Volume normal ($formatted)';
}

String _recentReturnLabel(KisSingleSymbolTradingResult result) {
  final recentReturn = _numberValue(result.indicatorPayload['recent_return']);
  if (recentReturn == null) {
    if (result.riskFlags
        .any((flag) => flag.toLowerCase() == 'weak_recent_return')) {
      return 'Recent return weak';
    }
    return 'Indicator not returned';
  }
  if (recentReturn < 0)
    return 'Recent return weak (${_formatPercent(recentReturn)})';
  if (recentReturn > 0) {
    return 'Recent return positive (${_formatPercent(recentReturn)})';
  }
  return 'Recent return flat';
}

double? _snapshotPrice(KisSingleSymbolTradingResult result) {
  return result.currentPrice ??
      _numberValue(result.indicatorPayload['price']) ??
      _numberValue(result.indicatorPayload['close']);
}

double? _numberValue(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  final text = value.toString().trim().replaceAll(',', '');
  if (text.isEmpty || text == 'null') return null;
  return double.tryParse(text);
}

String _formatDecimal(double value) {
  return value.toStringAsFixed(value.truncateToDouble() == value ? 0 : 2);
}

String _displaySignalScore(num? value,
    {String fallback = 'Score not returned'}) {
  if (value == null) return fallback;
  final numeric = value.toDouble();
  return numeric.toStringAsFixed(numeric.truncateToDouble() == numeric ? 1 : 2);
}

String _moneyLabel(num? value) {
  if (value == null) return 'Amount not returned';
  final formatted = _groupedNumber(value.abs(), decimals: 0);
  final sign = value < 0 ? '-' : '';
  return '$sign\u20A9$formatted';
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

String _formatPercent(double value) {
  return '${(value * 100).toStringAsFixed(2)}%';
}

Map<String, dynamic> _nestedMap(
  Map<String, dynamic> source,
  List<String> path,
) {
  Object? current = source;
  for (final key in path) {
    if (current is! Map) return const {};
    current = current[key];
  }
  if (current is Map<String, dynamic>) return current;
  if (current is Map) return Map<String, dynamic>.from(current);
  return const {};
}

String? _nestedString(Map<String, dynamic> source, List<String> path) {
  Object? current = source;
  for (final key in path) {
    if (current is! Map) return null;
    current = current[key];
  }
  final text = current?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return null;
  return text;
}

List<String> _nestedStringList(Map<String, dynamic> source, List<String> path) {
  Object? current = source;
  for (final key in path) {
    if (current is! Map) return const [];
    current = current[key];
  }
  if (current is! List) return const [];
  return current
      .map((item) => item.toString().trim())
      .where((item) => item.isNotEmpty && item != 'null')
      .toList(growable: false);
}
