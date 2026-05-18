import 'package:flutter/material.dart';

import '../../core/widgets/section_card.dart';
import '../dashboard/dashboard_controller.dart';
import '../dashboard/widgets/broker_context_controls.dart';
import '../dashboard/widgets/manual_trading_run_section.dart';

class AnalysisScreen extends StatelessWidget {
  const AnalysisScreen({
    super.key,
    required this.controller,
    this.onOpenManualOrder,
  });

  final DashboardController controller;
  final VoidCallback? onOpenManualOrder;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final hasDisplayRun =
            controller.hasLatestRunResult || controller.showingOfflineFallback;
        return SafeArea(
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Expanded(
                  child: Text(
                    'Analysis',
                    style: TextStyle(fontSize: 28, fontWeight: FontWeight.w700),
                  ),
                ),
                BrokerContextBadge(controller: controller),
              ]),
              const SizedBox(height: 6),
              const Text(
                'Read-only decision summary. Execution controls live in Trading.',
                style: TextStyle(color: Colors.white70),
              ),
              const SizedBox(height: 12),
              _DecisionSummaryCard(controller: controller),
              const SizedBox(height: 12),
              _LastSingleSymbolDecisionCard(controller: controller),
              const SizedBox(height: 12),
              if (!hasDisplayRun)
                const SectionCard(
                  child: Text(
                    'No watchlist run yet. Start a scan from Watchlist.',
                    style: TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                )
              else ...[
                if (controller.showingOfflineFallback) ...[
                  const SectionCard(
                    child: Text(
                      'Offline sample data',
                      style: TextStyle(
                        color: Colors.orangeAccent,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                ],
                _LastWatchlistDecisionCard(controller: controller),
              ],
            ],
          ),
        );
      },
    );
  }
}

class _LastSingleSymbolDecisionCard extends StatelessWidget {
  const _LastSingleSymbolDecisionCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final result = controller.manualRunResult;
    if (result == null) {
      return const SectionCard(
        child: Text(
          'No single-symbol decision yet. Run one from Trading.',
          style: TextStyle(color: Colors.white70),
        ),
      );
    }
    return ManualTradingRunResultPanel(result: result);
  }
}

class _LastWatchlistDecisionCard extends StatelessWidget {
  const _LastWatchlistDecisionCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final r = controller.runResult;
    final candidate =
        r.finalRankedCandidates.isEmpty ? null : r.finalRankedCandidates.first;
    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.manage_search_outlined, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              'Last Watchlist Decision',
              style: Theme.of(context).textTheme.titleMedium,
            ),
          ),
        ]),
        const SizedBox(height: 12),
        _DecisionLine(
          label: 'Decision',
          value: r.action.isEmpty ? 'HOLD' : r.action.toUpperCase(),
        ),
        _DecisionLine(
          label: 'Why',
          value: _friendlyReason(
            candidate?.noOrderReason ??
                candidate?.skipReason ??
                candidate?.blockReason ??
                r.reason,
            entryPenalty:
                candidate?.entryPenalty ?? candidate?.gptContext.entryPenalty,
          ),
          color: Colors.orangeAccent,
        ),
        _DecisionLine(label: 'Next Action', value: _nextAction(controller)),
        _DecisionLine(
          label: 'Scores',
          value:
              'Final Buy ${_score(candidate?.finalBuyScore)}, Final Sell ${_score(candidate?.finalSellScore)}, Confidence ${_score(candidate?.confidence)}',
        ),
        _DecisionLine(
          label: 'GPT Advisory',
          value: _textOrFallback(
            candidate?.gptContext.reason ??
                candidate?.marketResearchReason ??
                candidate?.gptReason,
            fallback: 'No advisory reason returned',
          ),
        ),
      ]),
    );
  }
}

class _DecisionSummaryCard extends StatelessWidget {
  const _DecisionSummaryCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final r = controller.runResult;
    final candidate =
        r.finalRankedCandidates.isEmpty ? null : r.finalRankedCandidates.first;
    final buyCandidate = candidate?.symbol ??
        (r.finalBestCandidate.isEmpty
            ? 'No buy candidate yet'
            : r.finalBestCandidate);
    final blockReason = candidate?.blockReason ??
        (candidate?.blockReasons.isEmpty == false
            ? candidate!.blockReasons.join(', ')
            : r.triggerBlockReason);
    final readiness = candidate == null
        ? (r.finalEntryReady ? 'Ready' : 'Not ready')
        : (candidate.entryReady ? 'Ready' : 'Not ready');
    final confidence = candidate?.confidence == null
        ? 'n/a'
        : candidate!.confidence!.toStringAsFixed(2);

    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.assistant_direction_outlined, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              'Decision Summary',
              style: Theme.of(context).textTheme.titleMedium,
            ),
          ),
        ]),
        const SizedBox(height: 12),
        _DecisionLine(label: 'Buy Candidate', value: buyCandidate),
        _DecisionLine(
            label: 'Sell Candidate', value: _sellCandidate(controller)),
        _DecisionLine(
          label: 'Block Reason',
          value: _friendlyReason(
            blockReason,
            entryPenalty:
                candidate?.entryPenalty ?? candidate?.gptContext.entryPenalty,
          ),
          color: Colors.orangeAccent,
        ),
        _DecisionLine(label: 'Next Action', value: _nextAction(controller)),
        _DecisionLine(label: 'Confidence', value: confidence),
        _DecisionLine(label: 'Readiness', value: readiness),
      ]),
    );
  }
}

class _DecisionLine extends StatelessWidget {
  const _DecisionLine({
    required this.label,
    required this.value,
    this.color,
  });

  final String label;
  final String value;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 6),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SizedBox(
          width: 116,
          child: Text(label, style: const TextStyle(color: Colors.white54)),
        ),
        Expanded(
          child: Text(
            value,
            style: TextStyle(
              color: color ?? Colors.white,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
      ]),
    );
  }
}

String _sellCandidate(DashboardController controller) {
  final latestSell = controller.latestKisLimitedAutoSellResult;
  if (latestSell?.symbol?.isNotEmpty == true) {
    return '${latestSell!.symbol} review from limited auto sell check';
  }
  final exitDecision = controller.latestKisExitShadowDecision;
  if (exitDecision?.candidate?.symbol.isNotEmpty == true) {
    return '${exitDecision!.candidate!.symbol} review from exit shadow';
  }
  return 'No sell candidate yet';
}

String _nextAction(DashboardController controller) {
  final r = controller.runResult;
  if (controller.settings.killSwitch) return 'Keep trading halted.';
  if (r.finalBestCandidate.isEmpty) return 'Run a watchlist scan.';
  if (!r.finalEntryReady)
    return 'Review the block reason before preparing a ticket.';
  return 'Prepare a manual ticket, then validate and confirm in Trading.';
}

String _friendlyReason(String? value, {num? entryPenalty}) {
  if (entryPenalty != null && entryPenalty >= 900) {
    return 'Entry blocked by GPT/risk context';
  }
  final text = value?.trim() ?? '';
  if (text.isEmpty || text == 'null') return 'No block reason';
  final normalized = text.toLowerCase();
  if (normalized == 'hard_blocked') return 'Entry blocked by risk context';
  if (normalized == 'gpt_hard_block_new_buy') {
    return 'GPT/risk context blocks new buy entries';
  }
  if (normalized == 'score_threshold_not_met') {
    return 'Score below entry threshold';
  }
  if (normalized == 'hold_signal') return 'HOLD signal, no order created';
  if (normalized == 'market_closed') return 'Market is closed';
  if (normalized == 'kr_trading_disabled') {
    return 'KR trading disabled / preview only';
  }
  if (normalized == 'preview_only') return 'Preview only, no real order';
  if (normalized == 'buy_entry_not_allowed_now') {
    return 'New buy entries are not allowed now';
  }
  if (normalized == 'dry_run_must_be_false') {
    return 'Dry-run is ON, live order blocked';
  }
  if (normalized == 'kill_switch_enabled') return 'Kill switch is ON';
  if (normalized.contains('gpt_entry_penalty=999')) {
    return 'New buy blocked by GPT/risk context';
  }
  return text;
}

String _score(double? value) {
  if (value == null) return '--';
  return value.toStringAsFixed(value.truncateToDouble() == value ? 0 : 2);
}

String _textOrFallback(String? value, {required String fallback}) {
  final text = value?.trim() ?? '';
  return text.isEmpty || text == 'null' ? fallback : text;
}
