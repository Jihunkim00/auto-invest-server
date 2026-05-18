import 'package:flutter/material.dart';

import '../../core/widgets/section_card.dart';
import '../../models/candidate.dart';
import '../../models/kis_buy_shadow_decision.dart';
import '../../models/kis_limited_auto_buy.dart';
import '../../models/watchlist_run_result.dart';
import 'dashboard_controller.dart';
import 'widgets/broker_context_controls.dart';
import 'widgets/manual_trading_run_section.dart';
import 'widgets/order_ticket_section.dart';
import 'widgets/result_presentation_helpers.dart' as presentation;

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
    final preview = controller.krWatchlistPreview;
    final checkResult = controller.latestKisBuyShadowDecision;
    final liveResult = controller.latestKisLimitedAutoBuyResult;

    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.security_outlined, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text('KIS Guarded Trading',
                style: Theme.of(context).textTheme.titleMedium),
          ),
          const _SoftBadge(text: 'KIS GUARDED', color: Colors.redAccent),
        ]),
        const SizedBox(height: 10),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(
              text: 'Manual click required', color: Colors.lightBlueAccent),
          _SoftBadge(text: 'Check and live split', color: Colors.greenAccent),
          _SoftBadge(text: 'No scheduler enable', color: Colors.amberAccent),
        ]),
        const SizedBox(height: 12),
        _KisGuardedInputs(
          controller: controller,
          symbolController: _symbolController,
        ),
        const SizedBox(height: 12),
        _KisAnalysisPreviewCard(
          controller: controller,
          result: preview,
        ),
        const SizedBox(height: 12),
        _KisGuardedSafetyStatus(controller: controller),
        const SizedBox(height: 12),
        _KisGuardedCheckCard(
          controller: controller,
          result: checkResult,
        ),
        const SizedBox(height: 12),
        _KisLiveGuardedRunCard(
          controller: controller,
          result: liveResult,
          onConfirmRun: () => _confirmKisGuardedRun(context),
        ),
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

class _KisGuardedInputs extends StatelessWidget {
  const _KisGuardedInputs({
    required this.controller,
    required this.symbolController,
  });

  final DashboardController controller;
  final TextEditingController symbolController;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      TextField(
        controller: symbolController,
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
        },
      ),
    ]);
  }
}

class _KisAnalysisPreviewCard extends StatelessWidget {
  const _KisAnalysisPreviewCard({
    required this.controller,
    required this.result,
  });

  final DashboardController controller;
  final WatchlistRunResult? result;

  @override
  Widget build(BuildContext context) {
    final candidate = result == null ? null : _topWatchlistCandidate(result!);
    return _ResultPanel(
      title: 'KIS Analysis Preview',
      icon: Icons.manage_search_outlined,
      badges: const [
        _SoftBadge(text: 'PREVIEW ONLY', color: Colors.lightBlueAccent),
        _SoftBadge(text: 'NO REAL ORDER', color: Colors.orangeAccent),
      ],
      children: [
        FilledButton.icon(
          onPressed: controller.krWatchlistPreviewLoading
              ? null
              : () async {
                  final actionResult = await controller.runKrWatchlistPreview();
                  if (!context.mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(actionResult.message),
                    backgroundColor:
                        actionResult.success ? Colors.green : Colors.redAccent,
                  ));
                },
          icon: controller.krWatchlistPreviewLoading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.refresh),
          label: Text(controller.krWatchlistPreviewLoading
              ? 'Refreshing analysis...'
              : 'Refresh KIS Analysis'),
        ),
        if (controller.krWatchlistPreviewError != null) ...[
          const SizedBox(height: 10),
          _StateLine(
            text: controller.krWatchlistPreviewError!,
            color: Colors.redAccent,
          ),
        ],
        const SizedBox(height: 10),
        if (result == null)
          const _StateLine(
            text: 'No KIS analysis preview loaded yet.',
          )
        else ...[
          _DataGrid(pairs: [
            _DataPairData(
              label: 'Top candidate',
              value: candidate?.symbol ?? result!.finalBestCandidate,
            ),
            _DataPairData(
              label: 'Score',
              value:
                  presentation.displayScore(_candidatePrimaryScore(candidate)),
            ),
            _DataPairData(
              label: 'Confidence',
              value: presentation.displayScore(candidate?.confidence,
                  fallback: 'Confidence not returned'),
            ),
            _DataPairData(
              label: 'Quant Buy',
              value: presentation.displayScore(candidate?.quantBuyScore),
            ),
            _DataPairData(
              label: 'Quant Sell',
              value: presentation.displayScore(candidate?.quantSellScore),
            ),
            _DataPairData(
              label: 'AI Buy',
              value: presentation.displayScore(candidate?.aiBuyScore),
            ),
            _DataPairData(
              label: 'AI Sell',
              value: presentation.displayScore(candidate?.aiSellScore),
            ),
            _DataPairData(
              label: 'Block reason',
              value: presentation.translateReason(
                candidate?.blockReason ?? result!.triggerBlockReason,
                entryPenalty: candidate?.entryPenalty ??
                    candidate?.gptContext.entryPenalty,
              ),
            ),
            const _DataPairData(
              label: 'Order',
              value: 'Preview only, no real order',
            ),
          ]),
          const SizedBox(height: 10),
          _StateLine(
            text:
                'GPT Advisory: ${presentation.displayText(_candidateAdvisory(candidate), fallback: 'GPT advisory unavailable')}',
          ),
          const SizedBox(height: 8),
          _StateLine(text: _candidateNextAction(candidate, isKis: true)),
          const SizedBox(height: 8),
          _AdvancedText(
            title: 'Advanced Details',
            text: 'configured_symbol_count=${result!.configuredSymbolCount}\n'
                'analyzed_symbol_count=${result!.analyzedSymbolCount}\n'
                'final_best_candidate=${result!.finalBestCandidate}\n'
                'reason=${result!.reason}\n'
                'candidate=${_candidateDebugText(candidate)}',
          ),
        ],
      ],
    );
  }
}

class _KisGuardedCheckCard extends StatelessWidget {
  const _KisGuardedCheckCard({
    required this.controller,
    required this.result,
  });

  final DashboardController controller;
  final KisBuyShadowDecision? result;

  @override
  Widget build(BuildContext context) {
    final loaded = result;
    return _ResultPanel(
      title: 'KIS Guarded Check Result',
      icon: Icons.fact_check_outlined,
      badges: const [
        _SoftBadge(text: 'CHECK ONLY', color: Colors.lightBlueAccent),
        _SoftBadge(text: 'NO REAL ORDER', color: Colors.greenAccent),
        _SoftBadge(text: 'SAFE TO TEST', color: Colors.amberAccent),
      ],
      children: [
        FilledButton.icon(
          onPressed: controller.kisBuyShadowLoading
              ? null
              : () async {
                  final actionResult = await controller.runKisGuardedCheck();
                  if (!context.mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(actionResult.message),
                    backgroundColor:
                        actionResult.success ? Colors.green : Colors.redAccent,
                  ));
                },
          icon: controller.kisBuyShadowLoading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.play_arrow),
          label: Text(controller.kisBuyShadowLoading
              ? 'Running check...'
              : 'Run KIS Guarded Check'),
        ),
        if (controller.kisBuyShadowError != null) ...[
          const SizedBox(height: 10),
          _StateLine(
            text: controller.kisBuyShadowError!,
            color: Colors.redAccent,
          ),
        ],
        const SizedBox(height: 10),
        if (loaded == null)
          const _StateLine(text: 'No guarded check result yet.')
        else ...[
          _DataGrid(pairs: [
            const _DataPairData(label: 'Check', value: 'Check only result'),
            _DataPairData(
                label: 'Result', value: _resultLabel(loaded.decision)),
            _DataPairData(
              label: 'Reason',
              value: presentation.translateReason(loaded.reason),
            ),
            const _DataPairData(label: 'Order', value: 'No order created'),
            _DataPairData(
              label: 'real_order_submitted',
              value: presentation.boolStatus(loaded.realOrderSubmitted),
            ),
            _DataPairData(
              label: 'broker_submit_called',
              value: presentation.boolStatus(loaded.brokerSubmitCalled),
            ),
            _DataPairData(
              label: 'manual_submit_called',
              value: presentation.boolStatus(loaded.manualSubmitCalled),
            ),
          ]),
          const SizedBox(height: 10),
          if (loaded.candidate == null) ...[
            const _StateLine(text: 'This check did not return AI analysis.'),
            const SizedBox(height: 8),
            const _StateLine(
              text: 'Refresh KIS Analysis to view candidate scores.',
            ),
          ] else
            _DataGrid(pairs: [
              _DataPairData(
                  label: 'Candidate', value: loaded.candidate!.symbol),
              _DataPairData(
                  label: 'Score',
                  value:
                      presentation.displayScore(loaded.candidate!.finalScore)),
              _DataPairData(
                  label: 'Confidence',
                  value:
                      presentation.displayScore(loaded.candidate!.confidence)),
              _DataPairData(
                  label: 'Quant',
                  value:
                      presentation.displayScore(loaded.candidate!.quantScore)),
              _DataPairData(
                  label: 'AI/GPT',
                  value:
                      presentation.displayScore(loaded.candidate!.gptBuyScore)),
            ]),
          const SizedBox(height: 8),
          _AdvancedText(
            title: 'Advanced Details',
            text: 'mode=${loaded.mode}\n'
                'status=${loaded.status}\n'
                'checks=${loaded.checks}\n'
                'safety=${loaded.safety}\n'
                'risk_flags=${loaded.riskFlags}\n'
                'gating_notes=${loaded.gatingNotes}\n'
                'failed_checks=${loaded.failedChecks}',
          ),
        ],
      ],
    );
  }
}

class _KisLiveGuardedRunCard extends StatelessWidget {
  const _KisLiveGuardedRunCard({
    required this.controller,
    required this.result,
    required this.onConfirmRun,
  });

  final DashboardController controller;
  final KisLimitedAutoBuy? result;
  final Future<bool> Function() onConfirmRun;

  @override
  Widget build(BuildContext context) {
    final loaded = result;
    return _ResultPanel(
      title: 'KIS Live Guarded Run Result',
      icon: Icons.verified_user_outlined,
      badges: const [
        _SoftBadge(text: 'LIVE GUARDED RUN', color: Colors.redAccent),
        _SoftBadge(text: 'ONE SHOT', color: Colors.lightBlueAccent),
      ],
      children: [
        CheckboxListTile(
          contentPadding: EdgeInsets.zero,
          controlAffinity: ListTileControlAffinity.leading,
          value: controller.kisGuardedRunConfirmation,
          onChanged: controller.kisLimitedAutoBuyLoading
              ? null
              : (value) =>
                  controller.setKisGuardedRunConfirmation(value == true),
          title: const Text(
            'I understand this may place a real KIS order if all backend risk gates approve it.',
          ),
        ),
        FilledButton.icon(
          onPressed: controller.canRunKisGuardedTradingOnce
              ? () async {
                  final confirmed = await onConfirmRun();
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
              ? 'Running live guarded...'
              : 'Run KIS Live Guarded Once'),
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
        const SizedBox(height: 10),
        if (loaded == null)
          const _StateLine(text: 'No live guarded run result yet.')
        else
          _KisGuardedResultSummary(result: loaded),
      ],
    );
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
            child: Text('KIS SAFETY GATE SUMMARY',
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
          _DataPair(
              label: 'selected_symbol', value: controller.kisGuardedRunSymbol),
          _DataPair(
              label: 'manual_confirmation_required',
              value: controller.kisGuardedRunConfirmation
                  ? 'checked'
                  : 'required'),
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
    final orderStatus = _liveOrderStatus(result);
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
        _DataGrid(pairs: [
          _DataPairData(label: 'Action', value: result.action.toUpperCase()),
          _DataPairData(label: 'Result', value: _resultLabel(result.result)),
          _DataPairData(
              label: 'Reason',
              value: presentation.translateReason(result.reason)),
          _DataPairData(
              label: 'Symbol', value: result.symbol ?? 'Not selected'),
          _DataPairData(
              label: 'Final score',
              value: presentation.displayScore(result.finalScore)),
          _DataPairData(
              label: 'Confidence',
              value: presentation.displayScore(result.confidence,
                  fallback: 'Confidence not returned')),
          _DataPairData(label: 'Order', value: orderStatus),
          _DataPairData(
              label: 'Real order submitted',
              value: presentation.boolStatus(result.realOrderSubmitted)),
          _DataPairData(
              label: 'Broker submit called',
              value: presentation.boolStatus(result.brokerSubmitCalled)),
          _DataPairData(
              label: 'Manual submit called',
              value: presentation.boolStatus(result.manualSubmitCalled)),
          _DataPairData(
              label: 'Order ID', value: result.orderId?.toString() ?? '--'),
          _DataPairData(label: 'KIS ODNO', value: result.kisOdno ?? '--'),
        ]),
        if (result.blockedBy.isNotEmpty) ...[
          const SizedBox(height: 8),
          _StateLine(
              text: 'Risk flags: ${result.blockedBy.take(3).join(', ')}'),
        ],
        if (result.failedChecks.isNotEmpty) ...[
          const SizedBox(height: 8),
          _StateLine(
              text: 'Gating notes: ${result.failedChecks.take(3).join(', ')}'),
        ],
        const SizedBox(height: 8),
        _StateLine(text: _liveNextAction(result)),
        const SizedBox(height: 8),
        _AdvancedText(
          title: 'Advanced Details',
          text: 'mode=${result.mode}\n'
              'status=${result.status}\n'
              'checks=${result.checks}\n'
              'safety=${result.safety}\n'
              'audit_metadata=${result.auditMetadata}\n'
              'blocked_by=${result.blockedBy}\n'
              'failed_checks=${result.failedChecks}',
        ),
      ]),
    );
  }
}

class _ResultPanel extends StatelessWidget {
  const _ResultPanel({
    required this.title,
    required this.icon,
    required this.badges,
    required this.children,
  });

  final String title;
  final IconData icon;
  final List<Widget> badges;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
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
          Icon(icon, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text(title, style: Theme.of(context).textTheme.titleSmall),
          ),
        ]),
        const SizedBox(height: 8),
        Wrap(spacing: 8, runSpacing: 8, children: badges),
        const SizedBox(height: 12),
        ...children,
      ]),
    );
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

class _AdvancedText extends StatelessWidget {
  const _AdvancedText({required this.title, required this.text});

  final String title;
  final String text;

  @override
  Widget build(BuildContext context) {
    return ExpansionTile(
      tilePadding: EdgeInsets.zero,
      childrenPadding: EdgeInsets.zero,
      title: Text(title),
      children: [_StateLine(text: text)],
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

Candidate? _topWatchlistCandidate(WatchlistRunResult result) {
  if (result.finalRankedCandidates.isNotEmpty) {
    return result.finalRankedCandidates.first;
  }
  if (result.researchedCandidates.isNotEmpty) {
    return result.researchedCandidates.first;
  }
  if (result.topQuantCandidates.isNotEmpty) {
    return result.topQuantCandidates.first;
  }
  return null;
}

double? _candidatePrimaryScore(Candidate? candidate) {
  return candidate?.finalEntryScore ??
      candidate?.entryScore ??
      candidate?.finalBuyScore ??
      candidate?.finalScore ??
      (candidate?.score == null ? null : candidate!.score!.toDouble());
}

String _candidateAdvisory(Candidate? candidate) {
  return presentation.firstText([
    candidate?.gptContext.reason,
    candidate?.marketResearchReason,
    candidate?.gptReason,
    candidate?.reason,
  ]);
}

String _candidateNextAction(Candidate? candidate, {required bool isKis}) {
  if (candidate == null) return 'Next Action: refresh analysis.';
  if (candidate.previewOnly == true || isKis) {
    return candidate.entryReady
        ? 'Next Action: prepare a manual ticket in Trading if you want to review it.'
        : 'Next Action: keep on watchlist or refresh analysis.';
  }
  return candidate.entryReady
      ? 'Next Action: review risk gates before any order action.'
      : 'Next Action: review again at the next scan.';
}

String _candidateDebugText(Candidate? candidate) {
  if (candidate == null) return 'No candidate payload';
  return 'symbol=${candidate.symbol}, '
      'final_entry_score=${candidate.finalEntryScore}, '
      'entry_score=${candidate.entryScore}, '
      'final_buy_score=${candidate.finalBuyScore}, '
      'confidence=${candidate.confidence}, '
      'risk_flags=${candidate.riskFlags}, '
      'gating_notes=${candidate.gatingNotes}, '
      'gpt_context=${candidate.gptContext}';
}

String _resultLabel(String value) {
  final normalized = value.trim().toLowerCase();
  if (normalized == 'would_buy') return 'Would buy';
  if (normalized == 'blocked') return 'Blocked';
  if (normalized == 'skipped') return 'Skipped';
  if (normalized == 'preview_only') return 'Preview only';
  if (normalized == 'dry_run') return 'Dry-run';
  if (normalized == 'submitted') return 'Executed';
  if (normalized.isEmpty) return 'Not available';
  return value;
}

String _liveOrderStatus(KisLimitedAutoBuy result) {
  if (result.realOrderSubmitted) return 'Real order submitted';
  if (result.result.toLowerCase().contains('reject')) return 'Rejected';
  if (result.orderId != null) return 'Order ID ${result.orderId}';
  if (result.safetyFlag('preview_only')) return 'Preview only';
  return 'No order created';
}

String _liveNextAction(KisLimitedAutoBuy result) {
  if (result.realOrderSubmitted)
    return 'Next Action: monitor and sync order status.';
  if (result.reason.isNotEmpty) {
    return 'Next Action: ${presentation.translateReason(result.reason)}.';
  }
  return 'Next Action: review safety gates before another run.';
}
