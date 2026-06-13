import 'dart:convert';

import 'package:flutter/material.dart';

import '../../../core/utils/timestamp_formatter.dart';
import '../../../core/widgets/section_card.dart';
import '../../../models/candidate.dart';
import '../../../models/kis_auto_readiness.dart';
import '../../../models/kis_auto_simulator_result.dart';
import '../../../models/kis_buy_shadow_decision.dart';
import '../../../models/kis_exit_shadow_decision.dart';
import '../../../models/kis_limited_auto_buy.dart';
import '../../../models/kis_limited_auto_buy_execution_review.dart';
import '../../../models/kis_limited_auto_buy_review.dart';
import '../../../models/kis_limited_auto_sell.dart';
import '../../../models/kis_shadow_exit_review.dart';
import '../../../models/kis_shadow_exit_review_queue.dart';
import '../../../models/kis_live_exit_preflight.dart';
import '../../../models/kis_scheduler_dry_run_orchestration.dart';
import '../../../models/kis_scheduler_dry_run_review.dart';
import '../../../models/kis_scheduler_guarded_buy.dart';
import '../../../models/kis_scheduler_guarded_sell.dart';
import '../../../models/kis_scheduler_guarded_sell_review.dart';
import '../../../models/kis_scheduler_readiness.dart';
import '../../../models/kis_scheduler_simulation.dart';
import '../../../models/kis_scheduler_live.dart';
import '../../../models/kis_single_symbol_trading_result.dart';
import '../../../models/market_watchlist.dart';
import '../../../models/managed_position.dart';
import '../../../models/ops_production_readiness.dart';
import '../../../models/ops_settings.dart';
import '../../../models/watchlist_run_result.dart';
import '../../dashboard/dashboard_controller.dart';
import 'result_presentation_helpers.dart' as presentation;

class WatchlistSection extends StatelessWidget {
  const WatchlistSection({
    super.key,
    required this.controller,
    this.onOpenManualOrder,
  });

  final DashboardController controller;
  final VoidCallback? onOpenManualOrder;

  @override
  Widget build(BuildContext context) {
    final isKr = controller.selectedProvider == SelectedProvider.kis;
    final watchlist = isKr ? controller.krWatchlist : controller.usWatchlist;
    final title = isKr ? 'KR watchlist / KIS' : 'US watchlist / Alpaca';
    final topCandidate = _topWatchlistCandidate(controller.runResult);
    void prepareAnalyzeInTrading(Candidate candidate, int? rank) {
      final result = controller.prepareKisTradingFromWatchlistCandidate(
        candidate,
        candidateRank: rank,
      );
      if (result.success) {
        onOpenManualOrder?.call();
      }
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(result.message),
        backgroundColor: result.success ? Colors.green : Colors.redAccent,
      ));
    }

    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.manage_search_outlined, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text(isKr ? 'Watchlist' : 'New Buy Candidates',
                style: Theme.of(context).textTheme.titleMedium),
          ),
          _CountPill(text: '${watchlist.count} symbols'),
        ]),
        const SizedBox(height: 10),
        Wrap(spacing: 8, runSpacing: 8, children: [
          Text(title,
              style: const TextStyle(
                  color: Colors.white70, fontWeight: FontWeight.w800)),
          if (isKr) ...[
            const _SoftBadge(text: 'WATCHLIST', color: Colors.lightBlueAccent),
            const _SoftBadge(
                text: 'PREVIEW ONLY', color: Colors.lightBlueAccent),
            const _SoftBadge(
                text: 'NO DIRECT ORDER SUBMIT', color: Colors.orangeAccent),
            const _SoftBadge(
                text: 'CANDIDATE DETAIL', color: Colors.greenAccent),
          ],
        ]),
        const SizedBox(height: 12),
        Wrap(spacing: 8, runSpacing: 8, children: [
          FilledButton.icon(
            onPressed: controller.runOnceLoading
                ? null
                : () async {
                    final result = await controller.runOnce();
                    if (!context.mounted) return;
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                      content: Text(result.message),
                      backgroundColor:
                          result.success ? Colors.green : Colors.redAccent,
                    ));
                  },
            icon: controller.runOnceLoading
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.play_arrow),
            label: Text(controller.runOnceLoading
                ? 'Analyzing...'
                : 'Run Watchlist Analysis'),
          ),
          OutlinedButton.icon(
            onPressed: controller.watchlistLoading
                ? null
                : () async {
                    final result = await controller.refreshWatchlist();
                    if (!context.mounted) return;
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                      content: Text(result.message),
                      backgroundColor:
                          result.success ? Colors.green : Colors.redAccent,
                    ));
                  },
            icon: controller.watchlistLoading
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.refresh),
            label: Text(controller.watchlistLoading
                ? 'Refreshing...'
                : 'Refresh Watchlist'),
          ),
          if (isKr)
            OutlinedButton.icon(
              key: const Key('update_kosdaq_top50_button'),
              onPressed: controller.kosdaqTop50Updating ||
                      controller.watchlistLoading
                  ? null
                  : () async {
                      final confirmed =
                          await _confirmKosdaqTop50Update(context);
                      if (confirmed != true || !context.mounted) return;
                      final result =
                          await controller.updateKosdaqTop50Watchlist();
                      if (!context.mounted) return;
                      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                        content: Text(result.message),
                        backgroundColor:
                            result.success ? Colors.green : Colors.redAccent,
                      ));
                    },
              icon: controller.kosdaqTop50Updating
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.update),
              label: Text(controller.kosdaqTop50Updating
                  ? 'Updating KR Top 50...'
                  : 'Update KR Top 50'),
            ),
        ]),
        if (isKr) ...[
          const SizedBox(height: 8),
          const Wrap(spacing: 8, runSpacing: 8, children: [
            _SoftBadge(
                text: 'WATCHLIST CONFIG ONLY', color: Colors.lightBlueAccent),
            _SoftBadge(text: 'NO ORDER SUBMIT', color: Colors.orangeAccent),
          ]),
        ],
        if (controller.kosdaqTop50UpdateError != null) ...[
          const SizedBox(height: 10),
          _StateLine(
            text: _primaryLine(controller.kosdaqTop50UpdateError!),
            color: Colors.redAccent,
          ),
        ],
        if (isKr && controller.latestKosdaqTop50Update != null) ...[
          const SizedBox(height: 10),
          _KosdaqUpdateResultSummary(
            payload: controller.latestKosdaqTop50Update!,
          ),
        ],
        const SizedBox(height: 12),
        _GateSelector(controller: controller),
        const SizedBox(height: 12),
        if (controller.error != null) ...[
          _StateLine(text: controller.error!, color: Colors.redAccent),
          const SizedBox(height: 12),
        ],
        if (controller.hasLatestRunResult ||
            controller.showingOfflineFallback) ...[
          _WatchlistRunResultSummary(
            runResult: controller.runResult,
            candidate: topCandidate,
            isKr: isKr,
            providerLabel: isKr ? 'KIS' : 'Alpaca',
            marketLabel: isKr ? 'KR' : 'US',
            onPrepareBuyTicket: topCandidate == null || !isKr
                ? null
                : () {
                    controller.useKrCandidateInOrderTicket(topCandidate);
                    onOpenManualOrder?.call();
                    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                      content: Text(
                          'Manual buy ticket prepared. Validate in Trading before submit.'),
                      backgroundColor: Colors.green,
                    ));
                  },
            onAnalyzeInTrading: isKr
                ? (candidate, rank) => prepareAnalyzeInTrading(candidate, rank)
                : null,
          ),
          const SizedBox(height: 12),
        ],
        if (controller.watchlistLoading)
          const LinearProgressIndicator(minHeight: 2),
        if (controller.watchlistError != null) ...[
          const SizedBox(height: 12),
          _StateLine(text: controller.watchlistError!, color: Colors.redAccent),
        ],
        if (watchlist.symbols.isEmpty && !controller.watchlistLoading) ...[
          const SizedBox(height: 12),
          _StateLine(
            text: isKr
                ? 'No KR watchlist symbols available'
                : 'No US watchlist symbols available',
          ),
        ],
        if (controller.hasLatestRunResult ||
            controller.showingOfflineFallback) ...[
          const SizedBox(height: 12),
          _WatchlistAdvancedDetails(
            runResult: controller.runResult,
            isKr: isKr,
            onAnalyzeInTrading: isKr
                ? (candidate, rank) => prepareAnalyzeInTrading(candidate, rank)
                : null,
          ),
        ],
        const SizedBox(height: 12),
        ExpansionTile(
          tilePadding: EdgeInsets.zero,
          childrenPadding: EdgeInsets.zero,
          title: const Text('Watchlist Symbols'),
          children: [
            if (watchlist.symbols.isEmpty)
              const _StateLine(text: 'No symbols loaded yet.')
            else
              _WatchlistSymbols(watchlist: watchlist, isKr: isKr),
          ],
        ),
      ]),
    );
  }
}

Future<bool?> _confirmKosdaqTop50Update(BuildContext context) {
  return showDialog<bool>(
    context: context,
    builder: (dialogContext) => AlertDialog(
      title: const Text('Update KR Top 50'),
      content: const Text(
        'This will rebuild the KR watchlist as 코스피 Top 30 + 코스닥 Top 20. No order will be submitted.',
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(dialogContext).pop(false),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: () => Navigator.of(dialogContext).pop(true),
          child: const Text('Update'),
        ),
      ],
    ),
  );
}

class _KosdaqUpdateResultSummary extends StatelessWidget {
  const _KosdaqUpdateResultSummary({required this.payload});

  final Map<String, dynamic> payload;

  @override
  Widget build(BuildContext context) {
    final groupLabel = _watchlistGroupLabel(payload);
    final count = _intFromPayload(payload, 'count');
    final targetCount = _intFromPayload(payload, 'target_count');
    final added = _listFromPayload(payload, 'added_symbols');
    final removed = _listFromPayload(payload, 'removed_symbols');
    final kept = _listFromPayload(payload, 'kept_symbols');
    final groups = _listFromPayload(payload, 'groups');

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
          const Icon(Icons.playlist_add_check, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text(groupLabel,
                style: const TextStyle(
                    color: Colors.white, fontWeight: FontWeight.w800)),
          ),
          _SoftBadge(
            text: targetCount == null
                ? '$count symbols'
                : '$count / $targetCount',
            color: Colors.lightBlueAccent,
          ),
        ]),
        const SizedBox(height: 8),
        Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(text: 'added ${added.length}', color: Colors.greenAccent),
          _SoftBadge(
              text: 'removed ${removed.length}', color: Colors.amberAccent),
          _SoftBadge(
              text: 'kept ${kept.length}', color: Colors.lightBlueAccent),
        ]),
        if (groups.isNotEmpty) ...[
          const SizedBox(height: 8),
          Wrap(spacing: 8, runSpacing: 8, children: [
            for (final group in groups)
              _SoftBadge(
                text: _groupCountLabel(group),
                color: Colors.cyanAccent,
              ),
          ]),
        ],
        if (removed.isNotEmpty) ...[
          const SizedBox(height: 8),
          const _StateLine(
            text: '50개 제한으로 일부 기존 종목이 제외되었습니다.',
            color: Colors.amberAccent,
          ),
          ExpansionTile(
            tilePadding: EdgeInsets.zero,
            childrenPadding: EdgeInsets.zero,
            title: const Text('Excluded Symbols',
                style: TextStyle(color: Colors.white70)),
            children: [
              Align(
                alignment: Alignment.centerLeft,
                child: Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    for (final item in removed.take(20))
                      _RemovedSymbolChip(item: item),
                  ],
                ),
              ),
            ],
          ),
        ],
        ExpansionTile(
          tilePadding: EdgeInsets.zero,
          childrenPadding: EdgeInsets.zero,
          title: const Text('Developer Raw Payload',
              style: TextStyle(color: Colors.white70)),
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
                    color: Colors.white70,
                    fontSize: 11,
                    fontFamily: 'monospace'),
              ),
            ),
          ],
        ),
      ]),
    );
  }
}

class _RemovedSymbolChip extends StatelessWidget {
  const _RemovedSymbolChip({required this.item});

  final Map<String, dynamic> item;

  @override
  Widget build(BuildContext context) {
    final symbol = item['symbol']?.toString() ?? '';
    final name = item['name']?.toString() ?? '';
    final market = _displayMarketLabel(item);
    final label = [
      symbol,
      if (name.isNotEmpty) name,
      if (market.isNotEmpty) market,
    ].join(' - ');
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
      ),
      child: Text(label, style: const TextStyle(color: Colors.white70)),
    );
  }
}

class _WatchlistRunResultSummary extends StatelessWidget {
  const _WatchlistRunResultSummary({
    required this.runResult,
    required this.candidate,
    required this.isKr,
    required this.providerLabel,
    required this.marketLabel,
    this.onPrepareBuyTicket,
    this.onAnalyzeInTrading,
  });

  final WatchlistRunResult runResult;
  final Candidate? candidate;
  final bool isKr;
  final String providerLabel;
  final String marketLabel;
  final VoidCallback? onPrepareBuyTicket;
  final void Function(Candidate candidate, int? rank)? onAnalyzeInTrading;

  @override
  Widget build(BuildContext context) {
    final status = presentation.firstText([
      candidate?.result,
      candidate?.status,
      runResult.result,
      runResult.action,
      'run completed',
    ]);
    final entryPenalty =
        candidate?.entryPenalty ?? candidate?.gptContext.entryPenalty;
    final reason = presentation.translateReason(
      presentation.firstText([
        runResult.reason,
        candidate?.noOrderReason,
        candidate?.skipReason,
        candidate?.reason,
        'No additional reason.',
      ]),
      entryPenalty: entryPenalty,
    );
    final orderId =
        candidate?.orderId ?? candidate?.relatedOrderId ?? runResult.orderId;
    final orderStatus = _watchlistOrderStatus(orderId, isKr: isKr);
    final topSymbol = candidate?.symbol.isNotEmpty == true
        ? candidate!.symbol
        : runResult.finalBestCandidate.isNotEmpty
            ? runResult.finalBestCandidate
            : 'No top candidate';
    final nextAction = _watchlistNextAction(candidate, runResult, isKr: isKr);
    final decision = _watchlistDecision(candidate, runResult);
    final resultLabel = _watchlistResultLabel(status, isKr: isKr);
    final normalizedStatus = status.toLowerCase();
    final blockReason = presentation.translateReason(
      presentation.firstText([
        candidate?.blockReason,
        candidate?.blockReasons.isNotEmpty == true
            ? candidate!.blockReasons.join(', ')
            : null,
        candidate?.skipReason,
        candidate?.noOrderReason,
        runResult.triggerBlockReason,
        runResult.reason,
      ]),
      entryPenalty: entryPenalty,
    );
    final noOrderReason = presentation.translateReason(
      presentation.firstText([
        candidate?.noOrderReason,
        candidate?.skipReason,
        runResult.reason,
        runResult.triggerBlockReason,
      ]),
      entryPenalty: entryPenalty,
    );
    final previewCandidates =
        _candidatePreviewList(runResult).take(5).toList(growable: false);
    final noOrder = orderId == null ||
        normalizedStatus.contains('skip') ||
        normalizedStatus.contains('block') ||
        isKr;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.list_alt_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text('Latest Scan Summary',
                style: Theme.of(context).textTheme.titleSmall),
          ),
          _SoftBadge(
            text: resultLabel.toUpperCase(),
            color: normalizedStatus.contains('skip') ||
                    normalizedStatus.contains('hold') ||
                    normalizedStatus.contains('block')
                ? Colors.amberAccent
                : Colors.lightBlueAccent,
          ),
        ]),
        const SizedBox(height: 10),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _ResultPair(
              label: 'Broker', value: isKr ? 'KIS Preview' : 'Alpaca Paper'),
          _ResultPair(
              label: 'Mode', value: isKr ? 'KIS Preview' : 'Watchlist Scan'),
          _ResultPair(label: 'Result', value: resultLabel),
          _ResultPair(label: 'Decision', value: decision),
          _ResultPair(label: 'Top Symbol', value: topSymbol),
          _ResultPair(label: 'Next Action', value: nextAction),
          _ResultPair(label: 'Order Status', value: orderStatus),
          _ResultPair(label: 'Provider', value: providerLabel),
          _ResultPair(label: 'Market', value: marketLabel),
          _ResultPair(
              label: 'Analyzed',
              value:
                  '${runResult.analyzedSymbolCount}/${runResult.configuredSymbolCount}'),
        ]),
        const SizedBox(height: 10),
        _StateLine(text: 'Reason: $reason'),
        const SizedBox(height: 12),
        _TopCandidateCard(
          candidate: candidate,
          isKr: isKr,
          threshold: runResult.minEntryScore,
          onPrepareBuyTicket: onPrepareBuyTicket,
          onAnalyzeInTrading: onAnalyzeInTrading == null
              ? null
              : () => onAnalyzeInTrading!(candidate!, 1),
        ),
        if (previewCandidates.isNotEmpty) ...[
          const SizedBox(height: 10),
          _WatchlistCandidatePreview(
            candidates: previewCandidates,
            isKr: isKr,
            threshold: runResult.minEntryScore,
            onAnalyzeInTrading: onAnalyzeInTrading,
          ),
        ],
        if (noOrder) ...[
          const SizedBox(height: 10),
          _WhyNoOrderCard(
            reason: noOrderReason,
            mainBlocker: blockReason,
            nextAction: nextAction,
          ),
        ],
      ]),
    );
  }
}

class _WatchlistCandidatePreview extends StatelessWidget {
  const _WatchlistCandidatePreview({
    required this.candidates,
    required this.isKr,
    required this.threshold,
    this.onAnalyzeInTrading,
  });

  final List<Candidate> candidates;
  final bool isKr;
  final int? threshold;
  final void Function(Candidate candidate, int? rank)? onAnalyzeInTrading;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Top Watchlist Candidates',
          style: TextStyle(fontWeight: FontWeight.w700)),
      const SizedBox(height: 8),
      for (final entry in candidates.asMap().entries)
        Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: _ExpandableWatchlistCandidateCard(
            candidate: entry.value,
            isKr: isKr,
            threshold: threshold,
            candidateRank: entry.key + 1,
            onAnalyzeInTrading: onAnalyzeInTrading,
          ),
        ),
    ]);
  }
}

class _WhyNoOrderCard extends StatelessWidget {
  const _WhyNoOrderCard({
    required this.reason,
    required this.mainBlocker,
    required this.nextAction,
  });

  final String reason;
  final String mainBlocker;
  final String nextAction;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: _panelDecoration(),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.info_outline, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text('Why No Order?',
                style: Theme.of(context).textTheme.titleSmall),
          ),
          const _SoftBadge(text: 'NO ORDER', color: Colors.amberAccent),
        ]),
        const SizedBox(height: 10),
        Wrap(spacing: 14, runSpacing: 8, children: [
          const _ResultPair(label: 'Order', value: 'No order created'),
          _ResultPair(label: 'Reason', value: reason),
          _ResultPair(label: 'Main blocker', value: mainBlocker),
          _ResultPair(label: 'Next action', value: nextAction),
        ]),
      ]),
    );
  }
}

class _WatchlistAdvancedDetails extends StatelessWidget {
  const _WatchlistAdvancedDetails({
    required this.runResult,
    required this.isKr,
    this.onAnalyzeInTrading,
  });

  final WatchlistRunResult runResult;
  final bool isKr;
  final void Function(Candidate candidate, int? rank)? onAnalyzeInTrading;

  @override
  Widget build(BuildContext context) {
    final candidates =
        _candidatePreviewList(runResult).take(5).toList(growable: false);
    final top = candidates.isEmpty ? null : candidates.first;
    return ExpansionTile(
      tilePadding: EdgeInsets.zero,
      childrenPadding: EdgeInsets.zero,
      title: const Text('Analysis Details'),
      subtitle: const Text('Readable score, advisory, and risk details.'),
      children: [
        _ReadableDetailGroup(
          title: 'Score Details',
          pairs: [
            _ResultPair(
                label: 'Primary Score',
                value: presentation.compactScore(_candidatePrimaryScore(top))),
            _ResultPair(
                label: 'Threshold',
                value: presentation.compactScore(runResult.minEntryScore)),
            _ResultPair(
                label: 'Confidence',
                value: presentation.compactScore(top?.confidence)),
            _ResultPair(
                label: 'Quant Buy',
                value: presentation.compactScore(top?.quantBuyScore)),
            _ResultPair(
                label: 'Quant Sell',
                value: presentation.compactScore(top?.quantSellScore)),
            _ResultPair(
                label: 'AI Buy',
                value: presentation.compactScore(top?.aiBuyScore)),
            _ResultPair(
                label: 'AI Sell',
                value: presentation.compactScore(top?.aiSellScore)),
            _ResultPair(
                label: 'GPT Buy',
                value: presentation.compactScore(top?.gptBuyScore)),
            _ResultPair(
                label: 'GPT Sell',
                value: presentation.compactScore(top?.gptSellScore)),
          ],
        ),
        const SizedBox(height: 10),
        _ReadableDetailGroup(
          title: 'Advisory Details',
          lines: [
            presentation.displayText(
              _gptAdvisoryReason(top),
              fallback: 'GPT advisory unavailable',
            ),
            if (runResult.finalCandidateSelectionReason.isNotEmpty)
              runResult.finalCandidateSelectionReason,
          ],
        ),
        const SizedBox(height: 10),
        _ReadableDetailGroup(
          title: 'Risk / Block Details',
          lines: [
            presentation.translateReason(
              presentation.firstText([
                top?.blockReason,
                top?.noOrderReason,
                top?.skipReason,
                runResult.triggerBlockReason,
                runResult.reason,
              ]),
              entryPenalty: top?.entryPenalty ?? top?.gptContext.entryPenalty,
            ),
            ..._candidateRiskNotes(top),
          ],
        ),
        const SizedBox(height: 10),
        _AdvancedCandidateList(
          title: 'Candidate Details',
          candidates: candidates,
          isKr: isKr,
          threshold: runResult.minEntryScore,
          onAnalyzeInTrading: onAnalyzeInTrading,
        ),
        ExpansionTile(
          tilePadding: EdgeInsets.zero,
          childrenPadding: EdgeInsets.zero,
          title: const Text('Developer Raw Payload'),
          children: [
            _StateLine(
              text:
                  'configured_symbol_count=${runResult.configuredSymbolCount}\n'
                  'analyzed_symbol_count=${runResult.analyzedSymbolCount}\n'
                  'quant_candidates_count=${runResult.quantCandidatesCount}\n'
                  'researched_candidates_count=${runResult.researchedCandidatesCount}\n'
                  'final_best_candidate=${runResult.finalBestCandidate}\n'
                  'trigger_block_reason=${runResult.triggerBlockReason}\n'
                  'top_quant_candidates=${runResult.topQuantCandidates}\n'
                  'researched_candidates=${runResult.researchedCandidates}\n'
                  'final_ranked_candidates=${runResult.finalRankedCandidates}',
            ),
          ],
        ),
      ],
    );
  }
}

class _ReadableDetailGroup extends StatelessWidget {
  const _ReadableDetailGroup({
    required this.title,
    this.pairs = const <Widget>[],
    this.lines = const <String>[],
  });

  final String title;
  final List<Widget> pairs;
  final List<String> lines;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(title, style: const TextStyle(fontWeight: FontWeight.w700)),
      const SizedBox(height: 8),
      if (pairs.isNotEmpty) Wrap(spacing: 14, runSpacing: 8, children: pairs),
      for (final line in lines.where((line) => line.trim().isNotEmpty))
        Padding(
          padding: const EdgeInsets.only(bottom: 4),
          child: Text('- $line', style: const TextStyle(color: Colors.white70)),
        ),
    ]);
  }
}

class _AdvancedCandidateList extends StatelessWidget {
  const _AdvancedCandidateList({
    required this.title,
    required this.candidates,
    required this.isKr,
    required this.threshold,
    this.onAnalyzeInTrading,
  });

  final String title;
  final List<Candidate> candidates;
  final bool isKr;
  final int? threshold;
  final void Function(Candidate candidate, int? rank)? onAnalyzeInTrading;

  @override
  Widget build(BuildContext context) {
    return ExpansionTile(
      tilePadding: EdgeInsets.zero,
      childrenPadding: EdgeInsets.zero,
      title: Text(title),
      children: [
        if (candidates.isEmpty)
          const _StateLine(text: 'No candidates.')
        else
          for (final entry in candidates.asMap().entries)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: _ExpandableWatchlistCandidateCard(
                candidate: entry.value,
                isKr: isKr,
                threshold: threshold,
                candidateRank: entry.key + 1,
                onAnalyzeInTrading: onAnalyzeInTrading,
              ),
            ),
      ],
    );
  }
}

class _ExpandableWatchlistCandidateCard extends StatelessWidget {
  const _ExpandableWatchlistCandidateCard({
    required this.candidate,
    required this.isKr,
    required this.threshold,
    this.candidateRank,
    this.onAnalyzeInTrading,
  });

  final Candidate candidate;
  final bool isKr;
  final int? threshold;
  final int? candidateRank;
  final void Function(Candidate candidate, int? rank)? onAnalyzeInTrading;

  @override
  Widget build(BuildContext context) {
    final company = _candidateCompanyLabel(candidate);
    final requiredScore = _candidateRequiredScore(candidate, threshold);
    final reason = _candidateDisplayReason(candidate);
    final actionStatus = _candidateActionStatus(candidate);
    final tradability = _candidateTradability(candidate, isKr: isKr);
    final riskNotes = _candidateTranslatedNotes(candidate.riskFlags);
    final gatingNotes = _candidateTranslatedNotes(candidate.gatingNotes);
    final blockNotes = _candidateTranslatedNotes([
      ...candidate.blockReasons,
      if (candidate.blockReason != null) candidate.blockReason!,
      if (candidate.noOrderReason != null) candidate.noOrderReason!,
      if (candidate.skipReason != null) candidate.skipReason!,
    ]);

    return Container(
      decoration: _panelDecoration(),
      child: ExpansionTile(
        tilePadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 2),
        childrenPadding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
        title: Text(
          '${candidate.symbol} \u00B7 $company',
          style: const TextStyle(fontWeight: FontWeight.w800),
        ),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 4),
            Text(
              '$actionStatus \u00B7 Buy ${presentation.compactScore(_candidateBuyScore(candidate))} / '
              'Required ${presentation.compactScore(requiredScore)} \u00B7 '
              'Sell ${presentation.compactScore(_candidateSellScore(candidate))}',
              style: const TextStyle(color: Colors.white70),
            ),
            const SizedBox(height: 2),
            Text(
              '${tradability.label}: $reason',
              style: TextStyle(color: tradability.color),
            ),
          ],
        ),
        children: [
          _ReadableDetailGroup(
            title: 'Candidate Identity',
            pairs: [
              _ResultPair(label: 'Symbol', value: candidate.symbol),
              _ResultPair(label: 'Company', value: company),
              _ResultPair(
                  label: 'Market / Provider',
                  value: _candidateMarketProviderLabel(candidate, isKr: isKr)),
              _ResultPair(label: 'Action hint', value: actionStatus),
              _ResultPair(
                  label: 'Entry ready', value: _yesNo(candidate.entryReady)),
              _ResultPair(
                  label: 'Trade allowed',
                  value: _nullableYesNo(candidate.tradeAllowed)),
            ],
          ),
          if (isKr && onAnalyzeInTrading != null) ...[
            const SizedBox(height: 10),
            Align(
              alignment: Alignment.centerLeft,
              child: OutlinedButton.icon(
                onPressed: () => onAnalyzeInTrading!(candidate, candidateRank),
                icon: const Icon(Icons.search, size: 18),
                label: const Text('Analyze in Trading'),
              ),
            ),
          ],
          const SizedBox(height: 10),
          _ReadableDetailGroup(
            title: 'Score Detail',
            pairs: [
              _ResultPair(
                  label: 'Current price',
                  value: _candidatePriceLabel(candidate)),
              _ResultPair(
                  label: 'Final buy score',
                  value: presentation.compactScore(candidate.finalBuyScore)),
              _ResultPair(
                  label: 'Final sell score',
                  value: presentation.compactScore(candidate.finalSellScore)),
              _ResultPair(
                  label: 'Quant buy score',
                  value: presentation.compactScore(candidate.quantBuyScore)),
              _ResultPair(
                  label: 'Quant sell score',
                  value: presentation.compactScore(candidate.quantSellScore)),
              _ResultPair(
                  label: 'AI buy score',
                  value: presentation.compactScore(candidate.aiBuyScore)),
              _ResultPair(
                  label: 'AI sell score',
                  value: presentation.compactScore(candidate.aiSellScore)),
              _ResultPair(
                  label: 'GPT buy score',
                  value: presentation.compactScore(candidate.gptBuyScore)),
              _ResultPair(
                  label: 'GPT sell score',
                  value: presentation.compactScore(candidate.gptSellScore)),
              _ResultPair(
                  label: 'Confidence',
                  value: presentation.compactScore(candidate.confidence)),
              _ResultPair(
                  label: 'Required threshold',
                  value: presentation.compactScore(requiredScore)),
              _ResultPair(
                  label: 'Buy-sell spread',
                  value: presentation.compactScore(candidate.buySellSpread)),
            ],
          ),
          const SizedBox(height: 10),
          _ReadableDetailGroup(
            title: 'Technical Snapshot',
            pairs: [
              _ResultPair(
                  label: 'Indicator status',
                  value: presentation.displayText(candidate.indicatorStatus,
                      fallback: 'Indicator status unavailable')),
              _ResultPair(
                  label: 'Indicator bars',
                  value: candidate.indicatorBarCount?.toString() ??
                      'Bar count unavailable'),
              _ResultPair(
                  label: 'EMA20',
                  value: _candidateIndicatorLabel(
                      candidate, const ['ema20', 'ema_20'])),
              _ResultPair(
                  label: 'EMA50',
                  value: _candidateIndicatorLabel(
                      candidate, const ['ema50', 'ema_50'])),
              _ResultPair(
                  label: 'VWAP',
                  value: _candidateIndicatorLabel(candidate, const ['vwap'])),
              _ResultPair(
                  label: 'RSI',
                  value: _candidateIndicatorLabel(candidate, const ['rsi'])),
              _ResultPair(
                  label: 'ATR',
                  value: _candidateIndicatorLabel(candidate, const ['atr'])),
              _ResultPair(
                  label: 'Volume ratio',
                  value: _candidateIndicatorLabel(
                      candidate, const ['volume_ratio', 'volumeRatio'])),
              _ResultPair(
                  label: 'Recent return',
                  value: _candidateIndicatorLabel(
                    candidate,
                    const ['recent_return', 'recentReturn'],
                    percentLike: true,
                  )),
              _ResultPair(
                  label: 'Momentum',
                  value: _candidateIndicatorLabel(
                    candidate,
                    const ['momentum'],
                    percentLike: true,
                  )),
              _ResultPair(
                  label: 'Price position',
                  value: _candidateIndicatorLabel(
                      candidate, const ['price_position', 'pricePosition'])),
            ],
          ),
          const SizedBox(height: 10),
          _ReadableDetailGroup(
            title: 'Advisory / Risk',
            lines: [
              'GPT/AI reason: ${presentation.displayText(_gptAdvisoryReason(candidate), fallback: 'GPT advisory unavailable')}',
              'Why not tradable: $reason',
              if (blockNotes.isNotEmpty) 'Blockers: ${blockNotes.join(' / ')}',
              if (riskNotes.isNotEmpty) 'Risk flags: ${riskNotes.join(' / ')}',
              if (gatingNotes.isNotEmpty)
                'Gating notes: ${gatingNotes.join(' / ')}',
            ],
          ),
        ],
      ),
    );
  }
}

class KisAutomationSection extends StatelessWidget {
  const KisAutomationSection({
    super.key,
    required this.controller,
    this.advancedInitiallyExpanded = false,
  });

  final DashboardController controller;
  final bool advancedInitiallyExpanded;

  @override
  Widget build(BuildContext context) {
    return Column(key: const Key('kis_automation_main'), children: [
      SectionCard(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            const Icon(Icons.auto_awesome_motion_outlined, size: 20),
            const SizedBox(width: 8),
            Expanded(
              child: Text('KIS Automation',
                  style: Theme.of(context).textTheme.titleMedium),
            ),
          ]),
          const SizedBox(height: 8),
          const Wrap(spacing: 8, runSpacing: 8, children: [
            _SoftBadge(text: 'OPERATOR FLOW', color: Colors.lightBlueAccent),
            _SoftBadge(text: 'DEFAULT HOLD', color: Colors.greenAccent),
            _SoftBadge(text: 'READINESS ONLY', color: Colors.white70),
            _SoftBadge(text: 'NO BROKER SUBMIT', color: Colors.orangeAccent),
          ]),
          const SizedBox(height: 8),
          const Text(
            'KIS automation only places orders after all safety gates pass. Default action is HOLD. The system checks dry-run, kill switch, cash, duplicate orders, daily limits, market session, score thresholds, and broker-submit status before any order.',
            style: TextStyle(color: Colors.white70),
          ),
        ]),
      ),
      const SizedBox(height: 12),
      _OperationsReadinessCard(controller: controller),
      const SizedBox(height: 12),
      _KisWatchlistAnalyzeBuyCard(controller: controller),
      const SizedBox(height: 12),
      _KisSingleSymbolAnalyzeBuyCard(controller: controller),
      const SizedBox(height: 12),
      _KisPositionManagementCard(controller: controller),
      const SizedBox(height: 12),
      _KisScheduledPositionManagementCard(controller: controller),
      const SizedBox(height: 12),
      _KisAdvancedDetailsSection(
        controller: controller,
        initiallyExpanded: advancedInitiallyExpanded,
      ),
    ]);
  }
}

class TestLabSection extends StatelessWidget {
  const TestLabSection({
    super.key,
    required this.controller,
    this.advancedInitiallyExpanded = false,
  });

  final DashboardController controller;
  final bool advancedInitiallyExpanded;

  @override
  Widget build(BuildContext context) {
    return KisAutomationSection(
      controller: controller,
      advancedInitiallyExpanded: advancedInitiallyExpanded,
    );
  }
}

class _KisWatchlistAnalyzeBuyCard extends StatelessWidget {
  const _KisWatchlistAnalyzeBuyCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final result = controller.latestKisLimitedAutoBuyResult;
    final candidate = result?.finalCandidate;
    final primaryReason = _limitedBuyPrimaryReason(result);
    return Container(
      key: const Key('kis_watchlist_analyze_buy_card'),
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: _panelDecoration(),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.add_task_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text('Watchlist Analyze & Buy',
                style: Theme.of(context).textTheme.titleSmall),
          ),
          _SoftBadge(
            text: result?.result.toUpperCase() ?? 'NOT RUN',
            color: result?.submitted == true
                ? Colors.greenAccent
                : Colors.amberAccent,
          ),
        ]),
        const SizedBox(height: 8),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(
              text: 'USES LIMITED AUTO BUY GATES', color: Colors.white70),
          _SoftBadge(text: 'DEFAULT HOLD', color: Colors.greenAccent),
          _SoftBadge(text: 'DUPLICATE CHECK', color: Colors.lightBlueAccent),
          _SoftBadge(text: 'CASH CHECK', color: Colors.lightBlueAccent),
        ]),
        const SizedBox(height: 12),
        FilledButton.icon(
          onPressed: controller.kisLimitedAutoBuyLoading
              ? null
              : () async {
                  final actionResult =
                      await controller.runKisLimitedAutoBuyOnce();
                  if (!context.mounted) return;
                  _showDashboardSnack(context, actionResult);
                },
          icon: controller.kisLimitedAutoBuyLoading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.play_arrow, size: 18),
          label: Text(controller.kisLimitedAutoBuyLoading
              ? 'Analyzing watchlist buy...'
              : 'Analyze Watchlist & Buy'),
        ),
        if (controller.kisLimitedAutoBuyError != null) ...[
          const SizedBox(height: 10),
          _StateLine(
            text: _primaryLine(controller.kisLimitedAutoBuyError!),
            color: Colors.redAccent,
          ),
        ],
        const SizedBox(height: 12),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _ResultPair(
            label: 'Best candidate',
            value: _limitedBuyCandidateLabel(result),
          ),
          _ResultPair(
            label: 'Score vs required',
            value:
                '${_score(candidate?.finalBuyScore ?? result?.finalBuyScore)} / ${_score(candidate?.requiredBuyScore ?? result?.requiredBuyScore)}',
          ),
          _ResultPair(
            label: 'Cash check',
            value: _limitedBuyCashLabel(result),
          ),
          _ResultPair(
            label: 'Duplicate check',
            value: _limitedBuyDuplicateLabel(result),
          ),
          _ResultPair(
            label: 'Order submission',
            value: _orderSubmissionLabel(
              brokerSubmitCalled: result?.brokerSubmitCalled ?? false,
              manualSubmitCalled: result?.manualSubmitCalled ?? false,
              realOrderSubmitted: result?.realOrderSubmitted ?? false,
            ),
          ),
          _ResultPair(
            label: 'Order ID',
            value: result?.orderId?.toString() ?? 'none',
          ),
          _ResultPair(label: 'KIS ODNO', value: result?.kisOdno ?? 'none'),
        ]),
        const SizedBox(height: 10),
        _StateLine(text: 'Why no buy: $primaryReason'),
        if (result == null) ...[
          const SizedBox(height: 8),
          const _StateLine(
            text:
                'No watchlist buy analysis has run yet. Existing backend gates decide BUY or HOLD.',
          ),
        ],
      ]),
    );
  }
}

class _KisSingleSymbolAnalyzeBuyCard extends StatelessWidget {
  const _KisSingleSymbolAnalyzeBuyCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final result = controller.latestKisSingleSymbolTradingResult;
    return Container(
      key: const Key('kis_single_symbol_analyze_buy_card'),
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: _panelDecoration(),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.search_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text('Single Symbol Analyze & Buy',
                style: Theme.of(context).textTheme.titleSmall),
          ),
          _SoftBadge(
            text: result?.result.toUpperCase() ?? 'NOT RUN',
            color: result?.realOrderSubmitted == true
                ? Colors.greenAccent
                : Colors.amberAccent,
          ),
        ]),
        const SizedBox(height: 8),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(text: 'REQUESTED SYMBOL ONLY', color: Colors.white70),
          _SoftBadge(text: 'NO WATCHLIST FALLBACK', color: Colors.white70),
          _SoftBadge(text: 'FINAL CONFIRMATION', color: Colors.amberAccent),
        ]),
        const SizedBox(height: 12),
        Wrap(
            spacing: 10,
            runSpacing: 10,
            crossAxisAlignment: WrapCrossAlignment.end,
            children: [
              SizedBox(
                width: 150,
                child: TextFormField(
                  initialValue: controller.kisGuardedRunSymbol,
                  decoration: const InputDecoration(
                    labelText: 'KR symbol',
                    helperText: 'e.g. 005930',
                    isDense: true,
                  ),
                  textCapitalization: TextCapitalization.characters,
                  onChanged: controller.setKisGuardedRunSymbol,
                ),
              ),
              SizedBox(
                width: 110,
                child: TextFormField(
                  initialValue: controller.orderTicketQtyInput,
                  decoration: const InputDecoration(
                    labelText: 'Quantity',
                    isDense: true,
                  ),
                  keyboardType: TextInputType.number,
                  onChanged: controller.setOrderTicketQtyInput,
                ),
              ),
              FilledButton.icon(
                onPressed: controller.kisSingleSymbolTradingLoading
                    ? null
                    : () => _runSingleSymbolAnalyzeBuy(context, controller),
                icon: controller.kisSingleSymbolTradingLoading
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.play_arrow, size: 18),
                label: Text(controller.kisSingleSymbolTradingLoading
                    ? 'Analyzing symbol...'
                    : 'Analyze Symbol & Buy'),
              ),
            ]),
        if (controller.kisSingleSymbolTradingError != null) ...[
          const SizedBox(height: 10),
          _StateLine(
            text: _primaryLine(controller.kisSingleSymbolTradingError!),
            color: Colors.redAccent,
          ),
        ],
        const SizedBox(height: 12),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _ResultPair(
            label: 'symbol',
            value: result?.symbol ?? controller.kisGuardedRunSymbol,
          ),
          _ResultPair(
            label: 'requested/analyzed/returned',
            value: result == null
                ? 'not_run'
                : '${result.requestedSymbol ?? 'n/a'} / ${result.analyzedSymbol ?? 'n/a'} / ${result.returnedSymbol ?? 'n/a'}',
          ),
          _ResultPair(
            label: 'symbol_match',
            value: result == null ? 'n/a' : _boolText(result.symbolMatch),
          ),
          _ResultPair(
            label: 'score vs threshold',
            value:
                '${_score(result?.finalBuyScore ?? result?.finalEntryScore)} / ${_score(result?.effectiveMinEntryScore)}',
          ),
          _ResultPair(
            label: 'technical snapshot',
            value:
                '${result?.indicatorStatus ?? 'n/a'} / ${result?.indicatorBarCount?.toString() ?? 'n/a'} bars',
          ),
          _ResultPair(
            label: 'cash check',
            value: _singleSymbolCashLabel(result),
          ),
          _ResultPair(
            label: 'order submission',
            value: _orderSubmissionLabel(
              brokerSubmitCalled: result?.brokerSubmitCalled ?? false,
              manualSubmitCalled: result?.manualSubmitCalled ?? false,
              realOrderSubmitted: result?.realOrderSubmitted ?? false,
            ),
          ),
          _ResultPair(
            label: 'Order ID',
            value: result?.orderId?.toString() ?? 'none',
          ),
          _ResultPair(label: 'KIS ODNO', value: result?.kisOdno ?? 'none'),
        ]),
        const SizedBox(height: 10),
        _StateLine(text: 'Why no buy: ${_singleSymbolNoBuyReason(result)}'),
        if (result != null) ...[
          const SizedBox(height: 4),
          ExpansionTile(
            tilePadding: EdgeInsets.zero,
            childrenPadding: EdgeInsets.zero,
            title: const Text('Developer Raw Payload'),
            children: [
              _StateLine(text: _prettyJson(result.rawPayload)),
            ],
          ),
        ],
      ]),
    );
  }
}

class _KisPositionManagementCard extends StatelessWidget {
  const _KisPositionManagementCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final positions = controller.kisManagedPositions;
    final sellResult = controller.latestKisLimitedAutoSellResult;
    final sellReadyCount =
        positions.where((position) => position.isSellReady).length;
    final reviewSellCount =
        positions.where((position) => position.isReviewSell).length;
    return Container(
      key: const Key('kis_position_management_card'),
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: _panelDecoration(),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.inventory_2_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text('Position Management',
                style: Theme.of(context).textTheme.titleSmall),
          ),
          _SoftBadge(
            text: sellReadyCount > 0 ? 'SELL READY' : 'HOLD / REVIEW',
            color: sellReadyCount > 0 ? Colors.redAccent : Colors.greenAccent,
          ),
        ]),
        const SizedBox(height: 8),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(text: 'MULTI-POSITION REVIEW', color: Colors.white70),
          _SoftBadge(text: 'STOP-LOSS / TAKE-PROFIT', color: Colors.white70),
          _SoftBadge(
              text: 'HELD POSITION STATUS', color: Colors.lightBlueAccent),
        ]),
        const SizedBox(height: 10),
        const _StateLine(
          text:
              'Position Management evaluates all held KIS positions. Scheduled Position Management uses the same sell-first logic at scheduled times.',
        ),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          onPressed: controller.kisManagedPositionsLoading ||
                  controller.kisLimitedAutoSellLoading
              ? null
              : () async {
                  final actionResult =
                      await controller.refreshKisPositionManagement();
                  if (!context.mounted) return;
                  _showDashboardSnack(context, actionResult);
                },
          icon: controller.kisManagedPositionsLoading ||
                  controller.kisLimitedAutoSellLoading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.refresh, size: 18),
          label: Text(controller.kisManagedPositionsLoading ||
                  controller.kisLimitedAutoSellLoading
              ? 'Refreshing position management...'
              : 'Refresh Position Management'),
        ),
        if (controller.kisManagedPositionsError != null) ...[
          const SizedBox(height: 10),
          _StateLine(
            text: _primaryLine(controller.kisManagedPositionsError!),
            color: Colors.redAccent,
          ),
        ],
        if (controller.kisLimitedAutoSellError != null) ...[
          const SizedBox(height: 10),
          _StateLine(
            text: _primaryLine(controller.kisLimitedAutoSellError!),
            color: Colors.redAccent,
          ),
        ],
        const SizedBox(height: 12),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _ResultPair(label: 'held positions', value: '${positions.length}'),
          _ResultPair(label: 'SELL READY', value: '$sellReadyCount'),
          _ResultPair(label: 'REVIEW SELL', value: '$reviewSellCount'),
          _ResultPair(
            label: 'market sell session',
            value: sellResult == null
                ? 'n/a'
                : _yesNo(sellResult.sellSessionAllowed),
          ),
          _ResultPair(
            label: 'daily sell limit',
            value: sellResult == null
                ? 'n/a'
                : _limitedAutoSellDailyLimitLabel(sellResult),
          ),
          _ResultPair(
            label: 'duplicate open sell order',
            value: sellResult == null
                ? 'n/a'
                : _limitedAutoSellDuplicateLabel(sellResult),
          ),
          _ResultPair(
            label: 'recommended action',
            value: sellReadyCount > 0
                ? 'review sell-ready holdings'
                : 'continue monitoring',
          ),
        ]),
        const SizedBox(height: 10),
        if (positions.isEmpty)
          const _StateLine(
            text:
                'No KIS held positions loaded. Refresh Position Management to evaluate holdings.',
          )
        else
          for (final position in positions.take(8)) ...[
            _ManagedPositionTile(
              controller: controller,
              position: position,
            ),
            const SizedBox(height: 8),
          ],
      ]),
    );
  }
}

class _ManagedPositionTile extends StatelessWidget {
  const _ManagedPositionTile({
    required this.controller,
    required this.position,
  });

  final DashboardController controller;
  final ManagedPosition position;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      decoration: _panelDecoration(),
      child: ExpansionTile(
        tilePadding: const EdgeInsets.symmetric(horizontal: 12),
        childrenPadding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
        title: Text(
          '${position.symbol} / ${position.companyName}',
          style: const TextStyle(fontWeight: FontWeight.w800),
        ),
        subtitle: Text(
          '${position.humanReason}\nP/L ${_formatReviewKrwOrDash(position.unrealizedPl)} / ${_formatPercentFromDecimal(position.unrealizedPlPct)}',
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
        ),
        trailing: _SoftBadge(
          text: position.statusLabel,
          color: _managedPositionStatusColor(position),
        ),
        children: [
          Wrap(spacing: 14, runSpacing: 8, children: [
            _ResultPair(label: 'quantity', value: _qtyText(position.quantity)),
            _ResultPair(
              label: 'P/L',
              value:
                  '${_formatReviewKrwOrDash(position.unrealizedPl)} / ${_formatPercentFromDecimal(position.unrealizedPlPct)}',
            ),
            _ResultPair(
              label: 'stop-loss trigger',
              value: _yesNo(position.stopLossTriggered),
            ),
            _ResultPair(
              label: 'take-profit trigger',
              value: _yesNo(position.takeProfitTriggered),
            ),
            _ResultPair(
              label: 'weak trend',
              value: _yesNo(position.weakTrendTriggered),
            ),
            _ResultPair(
              label: 'sell pressure',
              value: _yesNo(position.sellPressureTriggered),
            ),
            _ResultPair(
              label: 'duplicate open sell order',
              value: _yesNo(position.latestManualSellOrder != null),
            ),
            _ResultPair(
              label: 'final sell score',
              value: _score(position.finalSellScore),
            ),
          ]),
          if (position.blockReasons.isNotEmpty) ...[
            const SizedBox(height: 8),
            _StateLine(
              text: 'block reasons: ${_joinList(position.blockReasons)}',
            ),
          ],
          const SizedBox(height: 10),
          const Align(
            alignment: Alignment.centerLeft,
            child: Text(
              'Advanced action',
              style: TextStyle(color: Colors.white70, fontSize: 12),
            ),
          ),
          const SizedBox(height: 6),
          OutlinedButton.icon(
            onPressed: position.canPrepareManualSell
                ? () async {
                    final actionResult = await controller
                        .prepareKisManualSellFromManagedPosition(position);
                    if (!context.mounted) return;
                    _showDashboardSnack(context, actionResult);
                  }
                : null,
            icon: const Icon(Icons.edit_note_outlined, size: 18),
            label: const Text('Prepare Manual Sell'),
          ),
        ],
      ),
    );
  }
}

class _KisScheduledPositionManagementCard extends StatelessWidget {
  const _KisScheduledPositionManagementCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final readiness = controller.latestKisSchedulerReadiness;
    final summary = readiness?.summary;
    final dryRun = controller.latestKisSchedulerDryRunOrchestration;
    final guardedSell = controller.latestKisSchedulerGuardedSellResult;
    final guardedBuy = controller.latestKisSchedulerGuardedBuyResult;
    final recentResult = dryRun?.result ??
        guardedSell?.result ??
        guardedBuy?.result ??
        summary?.readinessStatus ??
        'not_loaded';
    final brokerSubmitCount = (dryRun?.summary.brokerSubmitCount ?? 0) +
        (guardedSell?.brokerSubmitCalled == true ? 1 : 0) +
        (guardedBuy?.brokerSubmitCalled == true ? 1 : 0);
    return Container(
      key: const Key('kis_scheduled_position_management_card'),
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: _panelDecoration(),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.event_repeat_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text('Scheduled Position Management',
                style: Theme.of(context).textTheme.titleSmall),
          ),
          _SoftBadge(
            text: recentResult.toUpperCase(),
            color: recentResult == 'submitted'
                ? Colors.greenAccent
                : Colors.amberAccent,
          ),
        ]),
        const SizedBox(height: 8),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(text: 'SELL REVIEW FIRST', color: Colors.orangeAccent),
          _SoftBadge(text: 'BUY AFTER SELL REVIEW', color: Colors.white70),
          _SoftBadge(text: 'SCHEDULER DEFAULT OFF', color: Colors.amberAccent),
          _SoftBadge(text: 'NO SUBMIT IN DRY-RUN CHECK', color: Colors.white70),
        ]),
        const SizedBox(height: 10),
        const _StateLine(
          text:
              'Scheduled Position Management runs the position review first. Sell review comes before buy review. If a sell-ready position exists, new buy execution is skipped.',
        ),
        const SizedBox(height: 12),
        FilledButton.icon(
          onPressed: controller.kisSchedulerDryRunOrchestrationLoading
              ? null
              : () async {
                  final actionResult =
                      await controller.runKisSchedulerDryRunOrchestrationOnce();
                  if (!context.mounted) return;
                  _showDashboardSnack(context, actionResult);
                },
          icon: controller.kisSchedulerDryRunOrchestrationLoading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.play_arrow, size: 18),
          label: Text(controller.kisSchedulerDryRunOrchestrationLoading
              ? 'Running scheduled management check...'
              : 'Run Scheduled Management Check'),
        ),
        if (controller.kisSchedulerDryRunOrchestrationError != null) ...[
          const SizedBox(height: 10),
          _StateLine(
            text:
                _primaryLine(controller.kisSchedulerDryRunOrchestrationError!),
            color: Colors.redAccent,
          ),
        ],
        const SizedBox(height: 12),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _ResultPair(
            label: 'scheduler status',
            value: summary?.readinessStatus ?? 'not_loaded',
          ),
          _ResultPair(
            label: 'next slot',
            value: _schedulerSlotLabel(summary?.nextScheduledSlot),
          ),
          _ResultPair(
            label: 'last run',
            value: dryRun?.slotLabel ?? _latestSchedulerRunLabel(readiness),
          ),
          _ResultPair(
            label: 'guarded sell status',
            value: guardedSell?.result ?? 'not_loaded',
          ),
          _ResultPair(
            label: 'guarded buy status',
            value: guardedBuy?.result ?? 'not_loaded',
          ),
          _ResultPair(label: 'recent scheduler result', value: recentResult),
          _ResultPair(
              label: 'broker submit count', value: '$brokerSubmitCount'),
          _ResultPair(
            label: 'real submit allowed',
            value: _yesNo(dryRun?.realOrderSubmitAllowed ??
                readiness?.realOrderSubmitAllowed ??
                false),
          ),
          _ResultPair(
            label: 'scheduler real orders',
            value: _boolText(controller.settings.kisSchedulerAllowRealOrders),
          ),
          _ResultPair(
            label: 'guarded sell enabled',
            value: _boolText(controller.settings.kisSchedulerSellEnabled),
          ),
          _ResultPair(
            label: 'guarded buy enabled',
            value: _boolText(controller.settings.kisSchedulerBuyEnabled),
          ),
          _ResultPair(
            label: 'real order submitted',
            value: _yesNo(dryRun?.realOrderSubmitted == true ||
                guardedSell?.realOrderSubmitted == true ||
                guardedBuy?.realOrderSubmitted == true),
          ),
          _ResultPair(
            label: 'sell-ready blocks buy',
            value: _yesNo(guardedBuy?.sellReadyBlocksBuy ?? true),
          ),
        ]),
      ]),
    );
  }
}

class _KisAdvancedDetailsSection extends StatefulWidget {
  const _KisAdvancedDetailsSection({
    required this.controller,
    required this.initiallyExpanded,
  });

  final DashboardController controller;
  final bool initiallyExpanded;

  @override
  State<_KisAdvancedDetailsSection> createState() =>
      _KisAdvancedDetailsSectionState();
}

class _KisAdvancedDetailsSectionState
    extends State<_KisAdvancedDetailsSection> {
  late bool _expanded;

  @override
  void initState() {
    super.initState();
    _expanded = widget.initiallyExpanded;
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      key: const Key('kis_advanced_details_section'),
      width: double.infinity,
      decoration: _panelDecoration(),
      child: ExpansionTile(
        initiallyExpanded: widget.initiallyExpanded,
        onExpansionChanged: (value) => setState(() => _expanded = value),
        tilePadding: const EdgeInsets.symmetric(horizontal: 12),
        childrenPadding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
        title: Text('Advanced Details',
            style: Theme.of(context).textTheme.titleSmall),
        subtitle: const Text(
          'Detailed review, audit, dry-run, shadow, and guarded execution controls.',
        ),
        children: _expanded
            ? [
                _AdvancedDetailsGroup(
                  title: 'Advanced Buy Details',
                  children: [
                    _KisLimitedAutoBuyCard(controller: widget.controller),
                    const SizedBox(height: 12),
                    _KisLimitedAutoBuyReviewCard(controller: widget.controller),
                    const SizedBox(height: 12),
                    _KisLimitedAutoBuyExecutionReviewCard(
                        controller: widget.controller),
                    const SizedBox(height: 12),
                    _KisBuyShadowDecisionCard(controller: widget.controller),
                  ],
                ),
                const SizedBox(height: 12),
                _AdvancedDetailsGroup(
                  title: 'Advanced Position Details',
                  children: [
                    _KisLimitedAutoSellCard(controller: widget.controller),
                    const SizedBox(height: 12),
                    _KisLiveExitPreflightCard(controller: widget.controller),
                    const SizedBox(height: 12),
                    _KisExitShadowDecisionCard(controller: widget.controller),
                    const SizedBox(height: 12),
                    _KisShadowExitReviewCard(controller: widget.controller),
                    const SizedBox(height: 12),
                    _KisShadowExitReviewQueueCard(
                        controller: widget.controller),
                  ],
                ),
                const SizedBox(height: 12),
                _AdvancedDetailsGroup(
                  title: 'Advanced Scheduler Details',
                  children: [
                    _KisSchedulerReadinessCard(controller: widget.controller),
                    const SizedBox(height: 12),
                    _KisSchedulerDryRunOrchestrationCard(
                        controller: widget.controller),
                    const SizedBox(height: 12),
                    _KisSchedulerDryRunReviewCard(
                        controller: widget.controller),
                    const SizedBox(height: 12),
                    _KisSchedulerGuardedSellCard(controller: widget.controller),
                    const SizedBox(height: 12),
                    _KisSchedulerGuardedBuyCard(controller: widget.controller),
                    const SizedBox(height: 12),
                    _KisSchedulerGuardedSellReviewCard(
                        controller: widget.controller),
                    const SizedBox(height: 12),
                    _KisSchedulerLiveAutomationCard(
                        controller: widget.controller),
                  ],
                ),
                const SizedBox(height: 12),
                _AdvancedDetailsGroup(
                  title: 'Advanced Diagnostics',
                  children: [
                    _TestLabActions(controller: widget.controller),
                    const SizedBox(height: 12),
                    _KisLiveAutoReadinessCard(controller: widget.controller),
                    const SizedBox(height: 12),
                    _KisSchedulerSimulationPanel(controller: widget.controller),
                    const SizedBox(height: 12),
                    _KisAutoSimulatorPanel(controller: widget.controller),
                  ],
                ),
              ]
            : const <Widget>[],
      ),
    );
  }
}

class _AdvancedDetailsGroup extends StatelessWidget {
  const _AdvancedDetailsGroup({
    required this.title,
    required this.children,
  });

  final String title;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Align(
        alignment: Alignment.centerLeft,
        child: Text(title, style: const TextStyle(fontWeight: FontWeight.w800)),
      ),
      const SizedBox(height: 8),
      ...children,
    ]);
  }
}

class _OperationsReadinessCard extends StatelessWidget {
  const _OperationsReadinessCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return Container(
      key: const Key('kis_operations_readiness_card'),
      width: double.infinity,
      child: _OperationsReadinessCardBody(controller: controller),
    );
  }
}

class _OperationsReadinessCardBody extends StatelessWidget {
  const _OperationsReadinessCardBody({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final result = controller.latestOpsProductionReadiness;
    final status = result?.overallStatus ?? 'NOT LOADED';
    return Container(
      key: const Key('ops_production_readiness_card'),
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: _panelDecoration(),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.health_and_safety_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text('Operations Readiness',
                style: Theme.of(context).textTheme.titleSmall),
          ),
          _SoftBadge(text: status, color: _opsStatusColor(status)),
        ]),
        const SizedBox(height: 8),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(
              text: 'OPERATIONS READINESS', color: Colors.lightBlueAccent),
          _SoftBadge(text: 'SAFETY CHECK', color: Colors.greenAccent),
          _SoftBadge(text: 'READINESS ONLY', color: Colors.white70),
          _SoftBadge(text: 'NO BROKER SUBMIT', color: Colors.orangeAccent),
          _SoftBadge(text: 'PRODUCTION CHECKLIST', color: Colors.amberAccent),
          _SoftBadge(text: 'LIVE ORDER STATUS', color: Colors.redAccent),
        ]),
        const SizedBox(height: 12),
        _OperationsReadinessSummaryGrid(
          result: result,
          settings: controller.settings,
        ),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          onPressed: controller.opsProductionReadinessLoading
              ? null
              : () async {
                  final actionResult =
                      await controller.refreshOpsProductionReadiness();
                  if (!context.mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(actionResult.message),
                    backgroundColor:
                        actionResult.success ? Colors.green : Colors.redAccent,
                  ));
                },
          icon: controller.opsProductionReadinessLoading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.refresh, size: 18),
          label: Text(controller.opsProductionReadinessLoading
              ? 'Refreshing operations readiness...'
              : 'Refresh Operations Readiness'),
        ),
        if (controller.opsProductionReadinessError != null) ...[
          const SizedBox(height: 10),
          _StateLine(
            text: _primaryLine(controller.opsProductionReadinessError!),
            color: Colors.redAccent,
          ),
        ],
        if (result == null) ...[
          const SizedBox(height: 10),
          const _StateLine(
            text:
                'No operations readiness report loaded. Refresh before live review.',
          ),
        ] else ...[
          const SizedBox(height: 12),
          _OperationsTodayActivity(result: result),
          const SizedBox(height: 12),
          _OperationsProductionChecklist(result: result),
          const SizedBox(height: 12),
          _OperationsSafetyChecks(result: result),
          const SizedBox(height: 12),
          _OperationsIssuesAndActions(result: result),
          const SizedBox(height: 4),
          ExpansionTile(
            tilePadding: EdgeInsets.zero,
            childrenPadding: EdgeInsets.zero,
            title: const Text('Developer Raw Payload'),
            children: [
              _StateLine(text: _prettyJson(result.rawPayload)),
            ],
          ),
        ],
      ]),
    );
  }
}

class _OperationsReadinessSummaryGrid extends StatelessWidget {
  const _OperationsReadinessSummaryGrid({
    required this.result,
    required this.settings,
  });

  final OpsProductionReadiness? result;
  final OpsSettings settings;

  @override
  Widget build(BuildContext context) {
    return Wrap(spacing: 14, runSpacing: 8, children: [
      _ResultPair(
        label: 'overall status',
        value: result?.overallStatus ?? 'not_loaded',
      ),
      _ResultPair(
        label: 'dry_run',
        value: _boolText(result?.dryRun ?? settings.dryRun),
      ),
      _ResultPair(
        label: 'kill_switch',
        value: _boolText(result?.killSwitch ?? settings.killSwitch),
      ),
      _ResultPair(
        label: 'KIS real orders',
        value: _boolText(result?.kisRealOrderEnabled ?? false),
      ),
      _ResultPair(
        label: 'scheduler real orders',
        value: _boolText(result?.schedulerRealOrdersEnabled ??
            settings.kisSchedulerAllowRealOrders),
      ),
      _ResultPair(
        label: 'scheduler sell',
        value: _boolText(
            result?.schedulerSellEnabled ?? settings.kisSchedulerSellEnabled),
      ),
      _ResultPair(
        label: 'scheduler buy',
        value: _boolText(
            result?.schedulerBuyEnabled ?? settings.kisSchedulerBuyEnabled),
      ),
      _ResultPair(
        label: 'live auto sell',
        value: _boolText(
            result?.liveAutoSellEnabled ?? settings.kisLiveAutoSellEnabled),
      ),
      _ResultPair(
        label: 'live auto buy',
        value: _boolText(
            result?.liveAutoBuyEnabled ?? settings.kisLiveAutoBuyEnabled),
      ),
      _ResultPair(
        label: 'today broker submits',
        value: (result?.todayBrokerSubmits ?? 0).toString(),
      ),
      _ResultPair(
        label: 'today order count',
        value: (result?.todayOrderCount ?? 0).toString(),
      ),
      _ResultPair(
        label: 'critical issues',
        value: (result?.criticalIssueCount ?? 0).toString(),
      ),
      _ResultPair(
        label: 'warnings',
        value: (result?.warningCount ?? 0).toString(),
      ),
    ]);
  }
}

class _OperationsTodayActivity extends StatelessWidget {
  const _OperationsTodayActivity({required this.result});

  final OpsProductionReadiness result;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('Today Activity', style: Theme.of(context).textTheme.labelLarge),
      const SizedBox(height: 8),
      Wrap(spacing: 14, runSpacing: 8, children: [
        _ResultPair(label: 'total runs', value: '${result.totalRunsToday}'),
        _ResultPair(
            label: 'blocked count', value: '${result.blockedCountToday}'),
        _ResultPair(
            label: 'broker submit count',
            value: '${result.todayBrokerSubmits}'),
        _ResultPair(label: 'failed count', value: '${result.failedCountToday}'),
        _ResultPair(label: 'top block reason', value: result.topBlockReason),
      ]),
    ]);
  }
}

class _OperationsProductionChecklist extends StatelessWidget {
  const _OperationsProductionChecklist({required this.result});

  final OpsProductionReadiness result;

  @override
  Widget build(BuildContext context) {
    final rows = [
      _opsChecklistRow(
        'watchlist baseline',
        result.check('kr_watchlist_baseline')?.status ?? 'INFO',
      ),
      _opsChecklistRow(
        'DB writable',
        result.check('db_writable')?.status ?? 'INFO',
      ),
      _opsChecklistRow(
        'docs present',
        result.check('production_docs_present')?.status ?? 'INFO',
      ),
      _opsChecklistRow(
        'env example present',
        result.check('env_example_present')?.status ?? 'INFO',
      ),
      _opsChecklistRow(
        'recent dry-run available',
        result.hasRecentDryRun ? 'PASS' : 'WARN',
      ),
      _opsChecklistRow(
        'recent scheduler review available',
        result.hasRecentSchedulerReview ? 'PASS' : 'WARN',
      ),
    ];
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('Production Checklist',
          style: Theme.of(context).textTheme.labelLarge),
      const SizedBox(height: 8),
      Wrap(spacing: 8, runSpacing: 8, children: rows),
    ]);
  }
}

class _OperationsSafetyChecks extends StatelessWidget {
  const _OperationsSafetyChecks({required this.result});

  final OpsProductionReadiness result;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('Safety Checks', style: Theme.of(context).textTheme.labelLarge),
      const SizedBox(height: 8),
      if (result.safetyChecks.isEmpty)
        const _StateLine(text: 'No safety checks returned.')
      else
        Column(
          children: [
            for (final check in result.safetyChecks.take(12)) ...[
              _OpsSafetyCheckRow(check: check),
              const SizedBox(height: 6),
            ],
          ],
        ),
    ]);
  }
}

class _OpsSafetyCheckRow extends StatelessWidget {
  const _OpsSafetyCheckRow({required this.check});

  final OpsSafetyCheck check;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.035),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Wrap(
            spacing: 8,
            runSpacing: 8,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              _SoftBadge(
                  text: check.status, color: _opsStatusColor(check.status)),
              Text(check.label,
                  style: const TextStyle(
                      color: Colors.white70, fontWeight: FontWeight.w700)),
            ]),
        if (check.message.isNotEmpty) ...[
          const SizedBox(height: 6),
          Text(check.message, style: const TextStyle(color: Colors.white60)),
        ],
        if (check.recommendedAction.isNotEmpty) ...[
          const SizedBox(height: 4),
          Text(check.recommendedAction,
              style: const TextStyle(color: Colors.white38, fontSize: 12)),
        ],
      ]),
    );
  }
}

class _OperationsIssuesAndActions extends StatelessWidget {
  const _OperationsIssuesAndActions({required this.result});

  final OpsProductionReadiness result;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('Blocking Issues', style: Theme.of(context).textTheme.labelLarge),
      const SizedBox(height: 8),
      if (result.blockingIssues.isEmpty)
        const _StateLine(text: 'No blocking issues reported.')
      else
        _StateLine(
          text: _joinList(result.blockingIssues),
          color: Colors.amberAccent,
        ),
      const SizedBox(height: 12),
      Text('Recommended Actions',
          style: Theme.of(context).textTheme.labelLarge),
      const SizedBox(height: 8),
      if (result.recommendedActions.isEmpty)
        const _StateLine(text: 'No recommended actions returned.')
      else
        Column(children: [
          for (final action in result.recommendedActions.take(6)) ...[
            _StateLine(text: action),
            const SizedBox(height: 6),
          ],
        ]),
    ]);
  }
}

Widget _opsChecklistRow(String label, String status) {
  return Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
    decoration: BoxDecoration(
      color: Colors.black.withValues(alpha: 0.12),
      borderRadius: BorderRadius.circular(8),
      border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
    ),
    child: Row(mainAxisSize: MainAxisSize.min, children: [
      _SoftBadge(text: status, color: _opsStatusColor(status)),
      const SizedBox(width: 8),
      Text(label, style: const TextStyle(color: Colors.white70)),
    ]),
  );
}

class _GateSelector extends StatelessWidget {
  const _GateSelector({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return SegmentedButton<int>(
      segments: const [
        ButtonSegment(value: 1, label: Text('Gate 1')),
        ButtonSegment(value: 2, label: Text('Gate 2')),
        ButtonSegment(value: 3, label: Text('Gate 3')),
        ButtonSegment(value: 4, label: Text('Gate 4')),
      ],
      selected: {controller.selectedGateLevel},
      onSelectionChanged: (selection) =>
          controller.setSelectedGateLevel(selection.first),
    );
  }
}

class _TopCandidateCard extends StatelessWidget {
  const _TopCandidateCard({
    required this.candidate,
    required this.isKr,
    required this.threshold,
    this.onPrepareBuyTicket,
    this.onAnalyzeInTrading,
  });

  final Candidate? candidate;
  final bool isKr;
  final int? threshold;
  final VoidCallback? onPrepareBuyTicket;
  final VoidCallback? onAnalyzeInTrading;

  @override
  Widget build(BuildContext context) {
    final candidate = this.candidate;
    if (candidate == null) {
      return Container(
        width: double.infinity,
        padding: const EdgeInsets.all(12),
        decoration: _panelDecoration(),
        child: const _StateLine(
          text: 'No top candidate yet. Start a scan to rank the watchlist.',
        ),
      );
    }
    final entryPenalty =
        candidate.entryPenalty ?? candidate.gptContext.entryPenalty;
    final blockReason = presentation.translateReason(
      _firstText([
        candidate.blockReason,
        candidate.blockReasons.isEmpty
            ? null
            : candidate.blockReasons.join(', '),
        candidate.skipReason,
        candidate.noOrderReason,
      ]),
      entryPenalty: entryPenalty,
    );
    final statusLabel = _candidateStatusLabel(candidate, isKr: isKr);
    final statusColor = _candidateStatusColor(statusLabel);
    final nextAction = _candidateNextAction(candidate, isKr: isKr);
    final riskNotes = _candidateRiskNotes(candidate);
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: _panelDecoration(),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Text(
              '${candidate.symbol} \u00B7 ${_candidateCompanyLabel(candidate)}',
              style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800),
            ),
          ),
          _SoftBadge(
            text: statusLabel.toUpperCase(),
            color: statusColor,
          ),
        ]),
        const SizedBox(height: 2),
        Text(_candidateMarketProviderLabel(candidate, isKr: isKr),
            style: const TextStyle(color: Colors.white70)),
        const SizedBox(height: 10),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _ResultPair(
              label: 'Primary score',
              value:
                  presentation.displayScore(_candidatePrimaryScore(candidate))),
          _ResultPair(
              label: 'Threshold',
              value: presentation
                  .displayScore(_candidateRequiredScore(candidate, threshold))),
          _ResultPair(
              label: 'Confidence',
              value: presentation.displayScore(candidate.confidence,
                  fallback: 'Confidence not returned')),
          _ResultPair(
              label: 'Quant Buy',
              value: presentation.displayScore(candidate.quantBuyScore)),
          _ResultPair(
              label: 'Quant Sell',
              value: presentation.displayScore(candidate.quantSellScore)),
          _ResultPair(
              label: 'AI Buy', value: _displayNumber(candidate.aiBuyScore)),
          _ResultPair(
              label: 'AI Sell', value: _displayNumber(candidate.aiSellScore)),
          _ResultPair(
              label: 'GPT Buy',
              value: _numericGptScoreLabel(candidate.gptBuyScore)),
          _ResultPair(
              label: 'GPT Sell',
              value: _numericGptScoreLabel(candidate.gptSellScore)),
          _ResultPair(label: 'Readiness', value: statusLabel),
          _ResultPair(
              label: 'Entry readiness',
              value: candidate.entryReady ? 'Ready' : 'Not ready'),
          _ResultPair(label: 'Next Action', value: nextAction),
        ]),
        const SizedBox(height: 8),
        _StateLine(
          text:
              'GPT Advisory: ${presentation.displayText(_gptAdvisoryReason(candidate), fallback: 'GPT advisory unavailable')}',
        ),
        const SizedBox(height: 8),
        _StateLine(text: 'Block reason: $blockReason'),
        if (riskNotes.isNotEmpty) ...[
          const SizedBox(height: 8),
          _StateLine(text: 'Risk notes: ${riskNotes.join(' / ')}'),
        ],
        if (onAnalyzeInTrading != null || onPrepareBuyTicket != null) ...[
          const SizedBox(height: 12),
          Wrap(spacing: 8, runSpacing: 8, children: [
            if (onAnalyzeInTrading != null)
              OutlinedButton.icon(
                onPressed: onAnalyzeInTrading,
                icon: const Icon(Icons.search, size: 18),
                label: const Text('Analyze in Trading'),
              ),
            if (onPrepareBuyTicket != null)
              OutlinedButton.icon(
                onPressed: onPrepareBuyTicket,
                icon: const Icon(Icons.input, size: 18),
                label: const Text('Prepare Buy Ticket'),
              ),
          ]),
        ],
      ]),
    );
  }
}

class _TestLabActions extends StatelessWidget {
  const _TestLabActions({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final actions = [
      _LabAction(
        label: 'Run Buy Shadow',
        loading: controller.kisBuyShadowLoading,
        run: controller.runKisBuyShadowOnce,
      ),
      _LabAction(
        label: 'Run Exit Shadow',
        loading: controller.kisExitShadowLoading,
        run: controller.runKisExitShadowOnce,
      ),
      _LabAction(
        label: 'Run Scheduler Dry-run',
        loading: controller.kisSchedulerRunLoading,
        run: controller.runKisSchedulerDryRunOnce,
      ),
      _LabAction(
        label: 'Run KIS Preview',
        loading: controller.krWatchlistPreviewLoading,
        run: controller.runKrWatchlistPreview,
      ),
      _LabAction(
        label: 'Run Limited Auto Buy Check',
        loading: controller.kisLimitedAutoBuyLoading,
        run: controller.runKisLimitedAutoBuyOnce,
      ),
      _LabAction(
        label: 'Run Stop-Loss Preflight',
        loading: controller.kisLimitedAutoSellLoading,
        run: controller.runKisLimitedAutoSellPreflightOnce,
      ),
      _LabAction(
        label: 'Run Scheduler Live Guarded Check',
        loading: controller.kisSchedulerLiveLoading,
        run: controller.runKisSchedulerLiveOnce,
      ),
      _LabAction(
        label: 'Run Scheduler Guarded Sell',
        loading: controller.kisSchedulerGuardedSellLoading,
        run: controller.runKisSchedulerGuardedSellOnce,
      ),
      _LabAction(
        label: 'Refresh Readiness',
        loading: controller.kisAutoReadinessLoading,
        run: controller.refreshKisAutoReadiness,
      ),
    ];
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        for (final action in actions)
          OutlinedButton.icon(
            onPressed: action.loading
                ? null
                : () async {
                    final result = await action.run();
                    if (!context.mounted) return;
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                      content: Text(result.message),
                      backgroundColor:
                          result.success ? Colors.green : Colors.redAccent,
                    ));
                  },
            icon: action.loading
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.play_arrow, size: 18),
            label: Text(action.loading ? 'Running...' : action.label),
          ),
      ],
    );
  }
}

class _LabAction {
  const _LabAction({
    required this.label,
    required this.loading,
    required this.run,
  });

  final String label;
  final bool loading;
  final Future<ActionResult> Function() run;
}

class _KisLiveAutoReadinessCard extends StatelessWidget {
  const _KisLiveAutoReadinessCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final result =
        controller.kisAutoReadinessResult ?? KisAutoReadiness.safeDefault();
    final liveAutoLabel =
        result.liveAutoEnabled ? 'enabled flag / submit blocked' : 'disabled';
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
          const Icon(Icons.security_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text('KIS Live Auto Readiness',
                style: Theme.of(context).textTheme.titleSmall),
          ),
          IconButton(
            tooltip: 'Refresh KIS auto readiness',
            onPressed: controller.kisAutoReadinessLoading
                ? null
                : () async {
                    final actionResult =
                        await controller.refreshKisAutoReadiness();
                    if (!context.mounted) return;
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                      content: Text(actionResult.message),
                      backgroundColor: actionResult.success
                          ? Colors.green
                          : Colors.redAccent,
                    ));
                  },
            icon: controller.kisAutoReadinessLoading
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.refresh),
          ),
        ]),
        const SizedBox(height: 8),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(text: 'READINESS ONLY', color: Colors.lightBlueAccent),
          _SoftBadge(text: 'LIVE AUTO DISABLED', color: Colors.amberAccent),
          _SoftBadge(text: 'NO BROKER SUBMIT', color: Colors.orangeAccent),
          _SoftBadge(
              text: 'MANUAL CONFIRM REQUIRED', color: Colors.greenAccent),
        ]),
        const SizedBox(height: 10),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _ResultPair(
              label: 'auto_order_ready',
              value: _boolText(result.autoOrderReady)),
          _ResultPair(label: 'live auto order', value: liveAutoLabel),
          _ResultPair(
              label: 'real_order_submit_allowed',
              value: _boolText(result.realOrderSubmitAllowed)),
          _ResultPair(
              label: 'future readiness',
              value: _boolText(result.futureAutoOrderReady)),
          _ResultPair(label: 'preflight', value: _boolText(result.preflight)),
          _ResultPair(
              label: 'reason',
              value: result.reason.isEmpty ? 'n/a' : result.reason),
        ]),
        if (!controller.kisAutoReadinessLoaded &&
            controller.kisAutoReadinessResult == null) ...[
          const SizedBox(height: 10),
          const _StateLine(
            text: 'Readiness not loaded yet. Safe default: live auto blocked.',
          ),
        ],
        const SizedBox(height: 10),
        Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(
            text: 'auto_order_ready=${_boolText(result.autoOrderReady)}',
            color: Colors.lightBlueAccent,
          ),
          _SoftBadge(
            text:
                'real_order_submit_allowed=${_boolText(result.realOrderSubmitAllowed)}',
            color: Colors.lightBlueAccent,
          ),
          _SoftBadge(
            text:
                "real_order_submitted=${_boolText(result.safetyFlag('real_order_submitted'))}",
            color: Colors.lightBlueAccent,
          ),
          _SoftBadge(
            text:
                "broker_submit_called=${_boolText(result.safetyFlag('broker_submit_called'))}",
            color: Colors.lightBlueAccent,
          ),
          _SoftBadge(
            text:
                "manual_submit_called=${_boolText(result.safetyFlag('manual_submit_called'))}",
            color: Colors.lightBlueAccent,
          ),
          _SoftBadge(
            text:
                "scheduler_real_order_enabled=${_boolText(result.safetyFlag('scheduler_real_order_enabled'))}",
            color: Colors.lightBlueAccent,
          ),
          _SoftBadge(
            text:
                "requires_manual_confirm=${_boolText(result.safetyFlag('requires_manual_confirm'))}",
            color: Colors.greenAccent,
          ),
        ]),
        const SizedBox(height: 10),
        _KisAutoReadinessChecks(result: result),
        if (result.blockedBy.isNotEmpty) ...[
          const SizedBox(height: 8),
          _StateLine(text: 'blocked_by: ${_joinList(result.blockedBy)}'),
        ],
        if (controller.kisAutoReadinessError != null) ...[
          const SizedBox(height: 10),
          _RetryLine(
            text: _primaryLine(controller.kisAutoReadinessError!),
            onRetry: controller.kisAutoReadinessLoading
                ? null
                : controller.refreshKisAutoReadiness,
          ),
        ],
        const SizedBox(height: 12),
        Wrap(spacing: 8, runSpacing: 8, children: [
          OutlinedButton.icon(
            onPressed: controller.kisAutoReadinessLoading
                ? null
                : () async {
                    final actionResult =
                        await controller.refreshKisAutoReadiness();
                    if (!context.mounted) return;
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                      content: Text(actionResult.message),
                      backgroundColor: actionResult.success
                          ? Colors.green
                          : Colors.redAccent,
                    ));
                  },
            icon: const Icon(Icons.refresh),
            label: Text(controller.kisAutoReadinessLoading
                ? 'Refreshing...'
                : 'Refresh'),
          ),
          FilledButton.icon(
            onPressed: controller.kisAutoPreflightLoading
                ? null
                : () async {
                    final actionResult =
                        await controller.runKisAutoPreflightOnce();
                    if (!context.mounted) return;
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                      content: Text(actionResult.message),
                      backgroundColor: actionResult.success
                          ? Colors.green
                          : Colors.redAccent,
                    ));
                  },
            icon: controller.kisAutoPreflightLoading
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.fact_check_outlined),
            label: Text(controller.kisAutoPreflightLoading
                ? 'Running preflight...'
                : 'Run Preflight Once'),
          ),
        ]),
      ]),
    );
  }
}

class _KisAutoReadinessChecks extends StatelessWidget {
  const _KisAutoReadinessChecks({required this.result});

  final KisAutoReadiness result;

  @override
  Widget build(BuildContext context) {
    const keys = [
      'dry_run',
      'kill_switch',
      'kis_enabled',
      'kis_real_order_enabled',
      'kis_scheduler_enabled',
      'kis_scheduler_allow_real_orders',
      'market_open',
      'entry_allowed_now',
      'daily_loss_ok',
      'trade_limit_ok',
      'gpt_context_available',
      'risk_engine_ok',
      'live_auto_buy_enabled',
      'live_auto_sell_enabled',
    ];
    return Wrap(spacing: 14, runSpacing: 8, children: [
      for (final key in keys)
        _ResultPair(label: key, value: _boolText(result.check(key))),
    ]);
  }
}

class _KisLiveExitPreflightCard extends StatelessWidget {
  const _KisLiveExitPreflightCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final result = controller.kisLiveExitPreflightResult;
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
          const Icon(Icons.logout_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text('KIS Live Exit Manual Confirm',
                style: Theme.of(context).textTheme.titleSmall),
          ),
        ]),
        const SizedBox(height: 8),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(
              text: 'EXIT PREFLIGHT ONLY', color: Colors.lightBlueAccent),
          _SoftBadge(text: 'MANUAL CONFIRM SELL', color: Colors.greenAccent),
          _SoftBadge(text: 'NO AUTO SELL', color: Colors.amberAccent),
          _SoftBadge(text: 'NO BROKER SUBMIT', color: Colors.orangeAccent),
          _SoftBadge(
              text: 'SCHEDULER REAL ORDERS DISABLED', color: Colors.redAccent),
          _SoftBadge(
              text: 'LIVE AUTO REMAINS DISABLED', color: Colors.amberAccent),
        ]),
        const SizedBox(height: 12),
        FilledButton.icon(
          onPressed: controller.kisLiveExitPreflightLoading
              ? null
              : () async {
                  final actionResult =
                      await controller.runKisLiveExitPreflight();
                  if (!context.mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(actionResult.message),
                    backgroundColor:
                        actionResult.success ? Colors.green : Colors.redAccent,
                  ));
                },
          icon: controller.kisLiveExitPreflightLoading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.fact_check_outlined),
          label: Text(controller.kisLiveExitPreflightLoading
              ? 'Running exit preflight...'
              : 'Run Exit Preflight'),
        ),
        if (controller.kisLiveExitPreflightError != null) ...[
          const SizedBox(height: 10),
          _StateLine(
              text: _primaryLine(controller.kisLiveExitPreflightError!),
              color: Colors.redAccent),
        ],
        if (result != null) ...[
          const SizedBox(height: 10),
          _KisLiveExitPreflightResultPanel(
            result: result,
            controller: controller,
          ),
        ],
      ]),
    );
  }
}

class _KisExitShadowDecisionCard extends StatelessWidget {
  const _KisExitShadowDecisionCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final result = controller.latestKisExitShadowDecision;
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
          const Icon(Icons.manage_search_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text('KIS Exit Shadow Decision',
                style: Theme.of(context).textTheme.titleSmall),
          ),
        ]),
        const SizedBox(height: 8),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(text: 'SHADOW EXIT ONLY', color: Colors.lightBlueAccent),
          _SoftBadge(
              text: 'DRY-RUN SELL SIMULATION', color: Colors.greenAccent),
          _SoftBadge(text: 'NO BROKER SUBMIT', color: Colors.orangeAccent),
          _SoftBadge(text: 'NO MANUAL SUBMIT', color: Colors.orangeAccent),
          _SoftBadge(
              text: 'LIVE AUTO SELL DISABLED', color: Colors.amberAccent),
          _SoftBadge(
              text: 'SCHEDULER REAL ORDERS DISABLED', color: Colors.redAccent),
        ]),
        const SizedBox(height: 12),
        FilledButton.icon(
          onPressed: controller.kisExitShadowLoading
              ? null
              : () async {
                  final actionResult = await controller.runKisExitShadowOnce();
                  if (!context.mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(actionResult.message),
                    backgroundColor:
                        actionResult.success ? Colors.green : Colors.redAccent,
                  ));
                },
          icon: controller.kisExitShadowLoading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.rule_folder_outlined),
          label: Text(controller.kisExitShadowLoading
              ? 'Running shadow exit...'
              : 'Run Shadow Exit Once'),
        ),
        if (controller.kisExitShadowError != null) ...[
          const SizedBox(height: 10),
          _StateLine(
              text: _primaryLine(controller.kisExitShadowError!),
              color: Colors.redAccent),
        ],
        if (result != null) ...[
          const SizedBox(height: 10),
          _KisExitShadowDecisionPanel(
            result: result,
            controller: controller,
          ),
        ] else ...[
          const SizedBox(height: 10),
          const _StateLine(
            text:
                'No shadow decision run yet. Running this only records a dry-run decision.',
          ),
        ],
      ]),
    );
  }
}

class _KisShadowExitReviewCard extends StatelessWidget {
  const _KisShadowExitReviewCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final review = controller.latestKisShadowExitReview;
    final summary = review?.summary;
    return Container(
      key: const Key('kis_shadow_exit_review_card'),
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.analytics_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text('KIS Shadow Exit Review',
                style: Theme.of(context).textTheme.titleSmall),
          ),
        ]),
        const SizedBox(height: 8),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(text: 'REVIEW ONLY', color: Colors.lightBlueAccent),
          _SoftBadge(
              text: 'SHADOW DECISION QUALITY', color: Colors.greenAccent),
          _SoftBadge(text: 'NO BROKER SUBMIT', color: Colors.orangeAccent),
          _SoftBadge(text: 'NO MANUAL SUBMIT', color: Colors.orangeAccent),
          _SoftBadge(
              text: 'LIVE AUTO SELL DISABLED', color: Colors.amberAccent),
          _SoftBadge(
              text: 'SCHEDULER REAL ORDERS DISABLED', color: Colors.redAccent),
        ]),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          onPressed: controller.kisShadowExitReviewLoading
              ? null
              : () async {
                  final actionResult =
                      await controller.refreshKisShadowExitReview();
                  if (!context.mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(actionResult.message),
                    backgroundColor:
                        actionResult.success ? Colors.green : Colors.redAccent,
                  ));
                },
          icon: controller.kisShadowExitReviewLoading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.refresh),
          label: Text(controller.kisShadowExitReviewLoading
              ? 'Refreshing review...'
              : 'Refresh Review only'),
        ),
        if (controller.kisShadowExitReviewError != null) ...[
          const SizedBox(height: 10),
          _StateLine(
              text: _primaryLine(controller.kisShadowExitReviewError!),
              color: Colors.redAccent),
        ],
        if (summary == null) ...[
          const SizedBox(height: 10),
          const _StateLine(
            text:
                'Review not loaded yet. This card only reads historical shadow decisions.',
          ),
        ] else ...[
          const SizedBox(height: 10),
          _KisShadowExitReviewSummaryPanel(summary: summary),
          const SizedBox(height: 12),
          _StateLine(
            text: review!.safety.noSubmitInvariantOk
                ? 'No-submit invariant: OK'
                : 'No-submit invariant: historical warning found',
            color: review.safety.noSubmitInvariantOk
                ? Colors.greenAccent
                : Colors.redAccent,
          ),
          if (review.recentDecisions.isNotEmpty) ...[
            const SizedBox(height: 12),
            for (final decision in review.recentDecisions.take(5)) ...[
              _KisShadowExitReviewDecisionTile(decision: decision),
              const SizedBox(height: 8),
            ],
          ] else ...[
            const SizedBox(height: 12),
            const _StateLine(text: 'No shadow exit decisions in this window.'),
          ],
        ],
      ]),
    );
  }
}

class _KisShadowExitReviewSummaryPanel extends StatelessWidget {
  const _KisShadowExitReviewSummaryPanel({required this.summary});

  final KisShadowExitReviewSummary summary;

  @override
  Widget build(BuildContext context) {
    return Wrap(spacing: 14, runSpacing: 8, children: [
      _ResultPair(
          label: 'total shadow runs',
          value: summary.totalShadowRuns.toString()),
      _ResultPair(
          label: 'would sell count', value: summary.wouldSellCount.toString()),
      _ResultPair(label: 'hold count', value: summary.holdCount.toString()),
      _ResultPair(
          label: 'manual review count',
          value: summary.manualReviewCount.toString()),
      _ResultPair(
          label: 'would sell rate', value: _formatRate(summary.wouldSellRate)),
      _ResultPair(
          label: 'manual sell followed',
          value:
              '${summary.manualSellFollowedCount} / ${_formatRate(summary.manualSellFollowedRate)}'),
      _ResultPair(
          label: 'stop-loss count', value: summary.stopLossCount.toString()),
      _ResultPair(
          label: 'take-profit count',
          value: summary.takeProfitCount.toString()),
      _ResultPair(
          label: 'insufficient cost basis',
          value: summary.insufficientCostBasisCount.toString()),
      _ResultPair(
          label: 'no-submit invariant',
          value: summary.noSubmitInvariantOk ? 'OK' : 'WARNING'),
    ]);
  }
}

class _KisShadowExitReviewDecisionTile extends StatelessWidget {
  const _KisShadowExitReviewDecisionTile({required this.decision});

  final KisShadowExitReviewDecision decision;

  @override
  Widget build(BuildContext context) {
    final linkedStatus = decision.linkedManualOrderStatus;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Text(decision.symbol,
                style: Theme.of(context).textTheme.titleSmall),
          ),
          _SoftBadge(
            text: _shadowDecisionLabel(decision.decision),
            color: decision.decision == 'would_sell'
                ? Colors.greenAccent
                : Colors.white70,
          ),
        ]),
        const SizedBox(height: 8),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _ResultPair(label: 'trigger', value: decision.trigger ?? 'n/a'),
          _ResultPair(
            label: 'unrealized P/L',
            value:
                '${_formatReviewKrwOrDash(decision.unrealizedPl)} / ${_formatReviewPlPercent(decision)}',
          ),
          _ResultPair(
            label: 'linked manual order',
            value: linkedStatus ?? 'n/a',
          ),
          if (decision.createdAt.isNotEmpty)
            _ResultPair(
              label: 'created_at',
              value: formatTimestampWithKst(decision.createdAt),
            ),
        ]),
        if (decision.reason.isNotEmpty) ...[
          const SizedBox(height: 8),
          _StateLine(text: decision.reason),
        ],
      ]),
    );
  }
}

class _KisShadowExitReviewQueueCard extends StatelessWidget {
  const _KisShadowExitReviewQueueCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final queue = controller.latestKisShadowExitReviewQueue;
    final summary = queue?.summary;
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
          const Icon(Icons.playlist_add_check_circle_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text('KIS Shadow Exit Review Queue',
                style: Theme.of(context).textTheme.titleSmall),
          ),
        ]),
        const SizedBox(height: 8),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(text: 'OPERATOR REVIEW', color: Colors.lightBlueAccent),
          _SoftBadge(text: 'SHADOW EXIT ALERTS', color: Colors.greenAccent),
          _SoftBadge(text: 'NO BROKER SUBMIT', color: Colors.orangeAccent),
          _SoftBadge(text: 'NO MANUAL SUBMIT', color: Colors.orangeAccent),
          _SoftBadge(
              text: 'LIVE AUTO SELL DISABLED', color: Colors.amberAccent),
          _SoftBadge(
              text: 'SCHEDULER REAL ORDERS DISABLED', color: Colors.redAccent),
        ]),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          onPressed: controller.kisShadowExitReviewQueueLoading
              ? null
              : () async {
                  final actionResult =
                      await controller.refreshKisShadowExitReviewQueue();
                  if (!context.mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(actionResult.message),
                    backgroundColor:
                        actionResult.success ? Colors.green : Colors.redAccent,
                  ));
                },
          icon: controller.kisShadowExitReviewQueueLoading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.refresh),
          label: Text(controller.kisShadowExitReviewQueueLoading
              ? 'Refreshing queue...'
              : 'Refresh Queue'),
        ),
        if (controller.kisShadowExitReviewQueueError != null) ...[
          const SizedBox(height: 10),
          _StateLine(
              text: _primaryLine(controller.kisShadowExitReviewQueueError!),
              color: Colors.redAccent),
        ],
        if (summary == null) ...[
          const SizedBox(height: 10),
          const _StateLine(
            text:
                'Queue not loaded yet. Review and dismiss actions only update local operator state.',
          ),
        ] else ...[
          const SizedBox(height: 10),
          _KisShadowExitReviewQueueSummaryPanel(summary: summary),
          const SizedBox(height: 12),
          Wrap(spacing: 8, runSpacing: 8, children: [
            _SoftBadge(
              text: 'read_only=${_boolText(queue!.safety.readOnly)}',
              color: Colors.lightBlueAccent,
            ),
            _SoftBadge(
              text:
                  'real_order_submitted=${_boolText(queue.safety.realOrderSubmitted)}',
              color: Colors.lightBlueAccent,
            ),
            _SoftBadge(
              text:
                  'broker_submit_called=${_boolText(queue.safety.brokerSubmitCalled)}',
              color: Colors.lightBlueAccent,
            ),
            _SoftBadge(
              text:
                  'manual_submit_called=${_boolText(queue.safety.manualSubmitCalled)}',
              color: Colors.lightBlueAccent,
            ),
          ]),
          if (queue.items.isNotEmpty) ...[
            const SizedBox(height: 12),
            for (final item in queue.items.take(5)) ...[
              _KisShadowExitReviewQueueItemTile(
                item: item,
                controller: controller,
              ),
              const SizedBox(height: 8),
            ],
          ] else ...[
            const SizedBox(height: 12),
            const _StateLine(text: 'No open shadow exit review alerts.'),
          ],
        ],
      ]),
    );
  }
}

class _KisShadowExitReviewQueueSummaryPanel extends StatelessWidget {
  const _KisShadowExitReviewQueueSummaryPanel({required this.summary});

  final KisShadowExitReviewQueueSummary summary;

  @override
  Widget build(BuildContext context) {
    return Wrap(spacing: 14, runSpacing: 8, children: [
      _ResultPair(label: 'open count', value: summary.openCount.toString()),
      _ResultPair(
          label: 'reviewed count', value: summary.reviewedCount.toString()),
      _ResultPair(
          label: 'dismissed count', value: summary.dismissedCount.toString()),
      _ResultPair(
          label: 'would-sell open',
          value: summary.wouldSellOpenCount.toString()),
      _ResultPair(
          label: 'manual-review open',
          value: summary.manualReviewOpenCount.toString()),
      _ResultPair(
          label: 'repeated symbols',
          value: summary.repeatedSymbolCount.toString()),
      _ResultPair(
        label: 'latest open',
        value: summary.latestOpenAt == null
            ? 'n/a'
            : formatTimestampWithKst(summary.latestOpenAt),
      ),
    ]);
  }
}

class _KisShadowExitReviewQueueItemTile extends StatelessWidget {
  const _KisShadowExitReviewQueueItemTile({
    required this.item,
    required this.controller,
  });

  final KisShadowExitReviewQueueItem item;
  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final linkedStatus = item.linkedManualOrderStatus;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Text(item.symbol,
                style: Theme.of(context).textTheme.titleSmall),
          ),
          _SoftBadge(
            text: _shadowDecisionLabel(item.decision),
            color: item.decision == 'would_sell'
                ? Colors.greenAccent
                : Colors.amberAccent,
          ),
          const SizedBox(width: 8),
          _SoftBadge(
            text: _queueStatusLabel(item.status),
            color: _queueStatusColor(item.status),
          ),
        ]),
        const SizedBox(height: 8),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _ResultPair(label: 'trigger', value: item.trigger),
          _ResultPair(
              label: 'occurrences', value: item.occurrenceCount.toString()),
          _ResultPair(
            label: 'latest P/L',
            value:
                '${_formatReviewKrwOrDash(item.latestUnrealizedPl)} / ${_formatQueuePlPercent(item)}',
          ),
          _ResultPair(
            label: 'linked manual order',
            value: linkedStatus ?? 'n/a',
          ),
          if (item.latestSeenAt != null)
            _ResultPair(
              label: 'latest_seen',
              value: formatTimestampWithKst(item.latestSeenAt),
            ),
        ]),
        if (item.reason.isNotEmpty) ...[
          const SizedBox(height: 8),
          _StateLine(text: item.reason),
        ],
        if (item.riskFlags.isNotEmpty) ...[
          const SizedBox(height: 8),
          _StateLine(text: 'risk_flags: ${_joinList(item.riskFlags)}'),
        ],
        if (item.gatingNotes.isNotEmpty) ...[
          const SizedBox(height: 8),
          _StateLine(text: 'gating_notes: ${_joinList(item.gatingNotes)}'),
        ],
        if (item.operatorNote?.isNotEmpty == true) ...[
          const SizedBox(height: 8),
          _StateLine(text: 'operator_note: ${item.operatorNote!}'),
        ],
        if (item.isOpen) ...[
          const SizedBox(height: 10),
          Wrap(spacing: 8, runSpacing: 8, children: [
            OutlinedButton.icon(
              onPressed: controller.kisShadowExitReviewQueueLoading
                  ? null
                  : () async {
                      final result = await controller
                          .markKisShadowExitQueueItemReviewed(item.queueId);
                      if (!context.mounted) return;
                      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                        content: Text(result.message),
                        backgroundColor:
                            result.success ? Colors.green : Colors.redAccent,
                      ));
                    },
              icon: const Icon(Icons.check_circle_outline),
              label: const Text('Mark Reviewed'),
            ),
            TextButton.icon(
              onPressed: controller.kisShadowExitReviewQueueLoading
                  ? null
                  : () async {
                      final result = await controller
                          .dismissKisShadowExitQueueItem(item.queueId);
                      if (!context.mounted) return;
                      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                        content: Text(result.message),
                        backgroundColor:
                            result.success ? Colors.green : Colors.redAccent,
                      ));
                    },
              icon: const Icon(Icons.close),
              label: const Text('Dismiss'),
            ),
          ]),
        ],
      ]),
    );
  }
}

class _KisLimitedAutoSellCard extends StatelessWidget {
  const _KisLimitedAutoSellCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final settings = controller.settings;
    final result = controller.latestKisLimitedAutoSellResult;
    final blockReasons = result?.blockReasons ?? const <String>[];
    return Container(
      key: const Key('kis_limited_auto_sell_card'),
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.shield_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text('KIS Limited Auto Sell',
                style: Theme.of(context).textTheme.titleSmall),
          ),
        ]),
        const SizedBox(height: 8),
        Wrap(spacing: 8, runSpacing: 8, children: [
          const _SoftBadge(
              text: 'STOP-LOSS EXECUTION', color: Colors.lightBlueAccent),
          const _SoftBadge(
              text: 'TAKE-PROFIT GUARDED EXECUTION',
              color: Colors.lightBlueAccent),
          const _SoftBadge(
              text: 'TAKE-PROFIT DEFAULT OFF', color: Colors.amberAccent),
          const _SoftBadge(text: 'GUARDED EXECUTION', color: Colors.white70),
          const _SoftBadge(
              text: 'AUTO BUY DISABLED', color: Colors.orangeAccent),
          const _SoftBadge(
              text: 'SCHEDULER REAL ORDERS DISABLED', color: Colors.redAccent),
          _SoftBadge(
            text: _limitedAutoSellBrokerBadge(result),
            color: result?.brokerSubmitActuallyCalled == true
                ? Colors.redAccent
                : Colors.orangeAccent,
          ),
        ]),
        const SizedBox(height: 12),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _ResultPair(
              label: 'live_auto_sell_enabled',
              value: _boolText(result?.liveAutoSellEnabled ??
                  settings.kisLiveAutoSellEnabled)),
          _ResultPair(
              label: 'stop_loss_auto_sell_enabled',
              value: _boolText(result?.stopLossAutoSellEnabled ??
                  settings.kisLimitedAutoSellStopLossEnabled)),
          _ResultPair(
              label: 'take_profit_auto_sell_enabled',
              value: _boolText(result?.takeProfitAutoSellEnabled ?? false)),
          _ResultPair(
              label: 'dry_run',
              value: _boolText(result?.dryRun ?? settings.dryRun)),
          _ResultPair(
              label: 'kill_switch',
              value: _boolText(result?.killSwitch ?? settings.killSwitch)),
          _ResultPair(
              label: 'kis_real_order_enabled',
              value: _boolText(result?.kisRealOrderEnabled ??
                  controller.kisSafetyStatus.kisRealOrderEnabled)),
          _ResultPair(
              label: 'sell session',
              value: result?.sellSessionAllowed == true ? 'Open' : 'Blocked'),
          _ResultPair(
              label: 'daily limit',
              value: result == null
                  ? 'n/a / ${settings.kisLimitedAutoSellMaxOrdersPerDay}'
                  : _limitedAutoSellDailyLimitLabel(result)),
          _ResultPair(
              label: 'stop_loss_execution_enabled',
              value: _boolText(result?.stopLossExecutionEnabled ?? false)),
          _ResultPair(
              label: 'take_profit_readiness_enabled',
              value: _boolText(result?.takeProfitReadinessEnabled ?? true)),
          _ResultPair(
              label: 'take_profit_execution_enabled',
              value: _boolText(result?.takeProfitExecutionEnabled ?? false)),
          _ResultPair(
              label: 'take_profit_non_actionable',
              value: _boolText(result?.takeProfitNonActionable ?? true)),
          _ResultPair(
              label: 'auto_order_ready',
              value: _boolText(result?.autoOrderReady ?? false)),
          _ResultPair(
              label: 'real_order_submit_allowed',
              value: _boolText(result?.realOrderSubmitAllowed ?? false)),
          if (result != null)
            _ResultPair(
                label: 'supported triggers',
                value: _limitedAutoSellSupportedTriggerLabel(result)),
        ]),
        const SizedBox(height: 12),
        if (blockReasons.isNotEmpty) ...[
          _StateLine(text: 'Block reasons: ${_joinList(blockReasons)}'),
          const SizedBox(height: 12),
        ],
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            OutlinedButton.icon(
              onPressed: controller.kisLimitedAutoSellLoading
                  ? null
                  : () async {
                      final actionResult =
                          await controller.refreshKisLimitedAutoSellStatus();
                      if (!context.mounted) return;
                      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                        content: Text(actionResult.message),
                        backgroundColor: actionResult.success
                            ? Colors.green
                            : Colors.redAccent,
                      ));
                    },
              icon: const Icon(Icons.refresh, size: 18),
              label: const Text('Refresh Status'),
            ),
            FilledButton.icon(
              onPressed: controller.kisLimitedAutoSellLoading
                  ? null
                  : () async {
                      final actionResult =
                          await controller.runKisLimitedAutoSellPreflightOnce();
                      if (!context.mounted) return;
                      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                        content: Text(actionResult.message),
                        backgroundColor: actionResult.success
                            ? Colors.green
                            : Colors.redAccent,
                      ));
                    },
              icon: controller.kisLimitedAutoSellLoading
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.fact_check_outlined),
              label: Text(controller.kisLimitedAutoSellLoading
                  ? 'Checking stop-loss...'
                  : 'Run Stop-Loss Preflight'),
            ),
            OutlinedButton.icon(
              onPressed: controller.kisLimitedAutoSellLoading
                  ? null
                  : () async {
                      final actionResult =
                          await controller.runKisLimitedAutoSellOnce();
                      if (!context.mounted) return;
                      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                        content: Text(actionResult.message),
                        backgroundColor: actionResult.success
                            ? Colors.green
                            : Colors.redAccent,
                      ));
                    },
              icon: const Icon(Icons.play_arrow, size: 18),
              label: const Text('Run Limited Auto Sell Once'),
            ),
          ],
        ),
        if (controller.kisLimitedAutoSellError != null) ...[
          const SizedBox(height: 10),
          _StateLine(
              text: _primaryLine(controller.kisLimitedAutoSellError!),
              color: Colors.redAccent),
        ],
        if (result == null) ...[
          const SizedBox(height: 10),
          const _StateLine(
            text:
                'No limited auto sell run yet. Default backend state blocks execution.',
          ),
        ] else ...[
          const SizedBox(height: 10),
          _KisLimitedAutoSellResultPanel(result: result),
        ],
      ]),
    );
  }
}

class _KisLimitedAutoSellResultPanel extends StatelessWidget {
  const _KisLimitedAutoSellResultPanel({required this.result});

  final KisLimitedAutoSell result;

  @override
  Widget build(BuildContext context) {
    final candidate = result.finalCandidate;
    final symbol = result.symbol ?? candidate?.symbol ?? 'n/a';
    final company = candidate?.name ?? 'n/a';
    final quantity = result.quantity ?? candidate?.quantity;
    final currentPrice = result.currentPrice ?? candidate?.currentPrice;
    final costBasis = result.costBasis ?? candidate?.costBasis;
    final currentValue =
        result.notional ?? result.currentValue ?? candidate?.currentValue;
    final unrealizedPl = result.unrealizedPl ?? candidate?.unrealizedPl;
    final unrealizedPlPct =
        result.unrealizedPlPct ?? candidate?.unrealizedPlPct;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      if (result.submitted) ...[
        _StateLine(
          text:
              'LIVE SELL SUBMITTED: order ${result.orderId ?? 'n/a'} / ODNO ${result.kisOdno ?? result.brokerOrderId ?? 'n/a'}',
          color: Colors.redAccent,
        ),
        const SizedBox(height: 10),
      ],
      Wrap(spacing: 14, runSpacing: 8, children: [
        _ResultPair(label: 'result', value: result.result),
        _ResultPair(label: 'action', value: result.action),
        _ResultPair(label: 'reason', value: result.reason),
        _ResultPair(label: 'mode', value: result.mode),
        _ResultPair(label: 'trigger', value: result.trigger ?? 'n/a'),
        _ResultPair(
            label: 'candidate_count', value: result.candidateCount.toString()),
        _ResultPair(label: 'symbol', value: symbol),
        _ResultPair(label: 'company', value: company),
        _ResultPair(label: 'quantity', value: quantity?.toString() ?? 'n/a'),
        _ResultPair(
            label: 'current price',
            value: _formatReviewKrwOrDash(currentPrice)),
        _ResultPair(
            label: 'current notional',
            value: _formatReviewKrwOrDash(currentValue)),
        _ResultPair(
            label: 'cost basis', value: _formatReviewKrwOrDash(costBasis)),
        _ResultPair(
            label: 'P/L',
            value:
                '${_formatReviewKrwOrDash(unrealizedPl)} / ${_formatPercentFromDecimal(unrealizedPlPct)}'),
        _ResultPair(
            label: 'stop-loss trigger',
            value: _boolText(result.stopLossTriggered)),
        _ResultPair(
            label: 'take-profit trigger',
            value: _boolText(result.takeProfitTriggered)),
        _ResultPair(
            label: 'take-profit readiness',
            value: result.takeProfitReadinessOnly ? 'readiness only' : 'n/a'),
        _ResultPair(
            label: 'take-profit execution',
            value: result.takeProfitExecutionEnabled ? 'enabled' : 'disabled'),
        _ResultPair(label: 'dry_run', value: _boolText(result.dryRun)),
        _ResultPair(label: 'kill_switch', value: _boolText(result.killSwitch)),
        _ResultPair(
            label: 'kis_real_order_enabled',
            value: _boolText(result.kisRealOrderEnabled)),
        _ResultPair(
            label: 'live_auto_sell_enabled',
            value: _boolText(result.liveAutoSellEnabled)),
        _ResultPair(
            label: 'stop_loss_auto_sell_enabled',
            value: _boolText(result.stopLossAutoSellEnabled)),
        _ResultPair(
            label: 'daily limit',
            value: _limitedAutoSellDailyLimitLabel(result)),
        _ResultPair(
            label: 'duplicate sell',
            value: _limitedAutoSellDuplicateLabel(result)),
        _ResultPair(
            label: 'validation',
            value: result.validationStatus.isEmpty
                ? 'not_called'
                : result.validationStatus),
        _ResultPair(
            label: 'real_order_submitted',
            value: _boolText(result.realOrderSubmitted)),
        _ResultPair(
            label: 'broker_submit_called',
            value: _boolText(result.brokerSubmitCalled)),
        _ResultPair(
            label: 'manual_submit_called',
            value: _boolText(result.manualSubmitCalled)),
        if (result.orderId != null)
          _ResultPair(label: 'order id', value: result.orderId.toString()),
        if (result.kisOdno != null)
          _ResultPair(label: 'KIS ODNO', value: result.kisOdno!),
      ]),
      if (result.primaryBlockReason != null) ...[
        const SizedBox(height: 8),
        _StateLine(text: 'primary_block_reason: ${result.primaryBlockReason}'),
      ],
      if (result.primaryBlockReason == 'take_profit_auto_sell_disabled' ||
          result.reason == 'take_profit_auto_sell_disabled') ...[
        const SizedBox(height: 8),
        const _StateLine(text: 'Take-profit auto sell disabled'),
      ],
      if (result.blockReasons.isNotEmpty) ...[
        const SizedBox(height: 8),
        _StateLine(text: 'block_reasons: ${_joinList(result.blockReasons)}'),
      ],
      const SizedBox(height: 10),
      Wrap(
        spacing: 8,
        runSpacing: 8,
        children: [
          for (final label in _limitedAutoSellLabels(result))
            _SoftBadge(
              text: label,
              color: label == 'BROKER SUBMIT CALLED'
                  ? Colors.redAccent
                  : label == 'STOP-LOSS EXECUTION' ||
                          label == 'TAKE-PROFIT GUARDED EXECUTION'
                      ? Colors.lightBlueAccent
                      : label.contains('DISABLED') ||
                              label == 'TAKE-PROFIT DEFAULT OFF'
                          ? Colors.amberAccent
                          : Colors.white70,
            ),
        ],
      ),
      if (result.candidates.isNotEmpty) ...[
        const SizedBox(height: 12),
        const Text('Candidates', style: TextStyle(fontWeight: FontWeight.w700)),
        const SizedBox(height: 8),
        for (final candidate in result.candidates)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: _KisLimitedAutoSellCandidateCard(candidate: candidate),
          ),
      ],
      const SizedBox(height: 4),
      ExpansionTile(
        tilePadding: EdgeInsets.zero,
        childrenPadding: EdgeInsets.zero,
        title: const Text('Developer Raw Payload'),
        children: [
          _StateLine(text: _prettyJson(result.rawPayload)),
        ],
      ),
    ]);
  }
}

class _KisLimitedAutoSellCandidateCard extends StatelessWidget {
  const _KisLimitedAutoSellCandidateCard({required this.candidate});

  final KisLimitedAutoSellCandidate candidate;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: _panelDecoration(),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Text(
              '${candidate.symbol} \u00B7 ${candidate.name}',
              style: const TextStyle(fontWeight: FontWeight.w800),
            ),
          ),
          _SoftBadge(
            text: _autoSellTriggerBadgeLabel(candidate),
            color: _autoSellStatusColor(candidate.status),
          ),
        ]),
        const SizedBox(height: 10),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _ResultPair(
              label: 'quantity',
              value: candidate.quantity?.toString() ?? 'n/a'),
          _ResultPair(
              label: 'current price',
              value: _formatReviewKrwOrDash(candidate.currentPrice)),
          _ResultPair(
              label: 'cost basis',
              value: _formatReviewKrwOrDash(candidate.costBasis)),
          _ResultPair(
              label: 'current value',
              value: _formatReviewKrwOrDash(candidate.currentValue)),
          _ResultPair(
              label: 'P/L',
              value:
                  '${_formatReviewKrwOrDash(candidate.unrealizedPl)} / ${_formatPercentFromDecimal(candidate.unrealizedPlPct)}'),
          _ResultPair(
              label: 'stop-loss threshold',
              value: _formatThresholdPct(candidate.stopLossThresholdPct)),
          _ResultPair(
              label: 'take-profit threshold',
              value: _formatThresholdPct(candidate.takeProfitThresholdPct)),
          _ResultPair(
              label: 'status', value: _autoSellStatusLabel(candidate.status)),
          _ResultPair(
              label: 'reason',
              value: candidate.reason.isEmpty
                  ? candidate.exitReason
                  : candidate.reason),
        ]),
        if (candidate.blockReasons.isNotEmpty) ...[
          const SizedBox(height: 8),
          _StateLine(
              text: 'Block reasons: ${_joinList(candidate.blockReasons)}'),
        ],
        const SizedBox(height: 8),
        _StateLine(
          text:
              'Triggers: stop_loss=${_boolText(candidate.stopLossTriggered)}, take_profit=${_boolText(candidate.takeProfitTriggered)}, weak_trend=${_boolText(candidate.weakTrendTriggered)}, sell_pressure=${_boolText(candidate.sellPressureTriggered)}',
        ),
        if (candidate.takeProfitTriggered) ...[
          const SizedBox(height: 8),
          if (candidate.takeProfitActionable)
            const _StateLine(text: 'Guarded execution eligible')
          else ...[
            const _StateLine(text: 'Take-profit execution disabled'),
            const SizedBox(height: 4),
            const _StateLine(text: 'Readiness only'),
          ],
        ],
        const SizedBox(height: 8),
        _StateLine(
          text:
              'Safety flags: duplicate_sell=${_boolText(candidate.latestOrder.isNotEmpty)}, risk_flags=${_joinList(candidate.riskFlags)}',
        ),
        if (candidate.gatingNotes.isNotEmpty) ...[
          const SizedBox(height: 8),
          _StateLine(text: 'Gating notes: ${_joinList(candidate.gatingNotes)}'),
        ],
      ]),
    );
  }
}

class _KisLimitedAutoBuyCard extends StatelessWidget {
  const _KisLimitedAutoBuyCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final settings = controller.settings;
    final result = controller.latestKisLimitedAutoBuyResult;
    return Container(
      key: const Key('kis_limited_auto_buy_card'),
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.add_shopping_cart_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text('KIS Limited Auto Buy',
                style: Theme.of(context).textTheme.titleSmall),
          ),
        ]),
        const SizedBox(height: 8),
        Wrap(spacing: 8, runSpacing: 8, children: [
          const _SoftBadge(
              text: 'BUY GUARDED EXECUTION', color: Colors.greenAccent),
          const _SoftBadge(text: 'DEFAULT OFF', color: Colors.amberAccent),
          _SoftBadge(
            text: result?.autoBuyEnabled == true
                ? 'AUTO BUY ENABLED'
                : 'AUTO BUY DISABLED',
            color: result?.autoBuyEnabled == true
                ? Colors.greenAccent
                : Colors.amberAccent,
          ),
          _SoftBadge(
            text: result?.brokerSubmitCalled == true
                ? 'BROKER SUBMIT RECORDED'
                : 'NO BROKER SUBMIT',
            color: result?.brokerSubmitCalled == true
                ? Colors.greenAccent
                : Colors.redAccent,
          ),
          const _SoftBadge(
              text: 'SCHEDULER REAL ORDERS DISABLED', color: Colors.redAccent),
          const _SoftBadge(text: 'MAX 1 BUY / DAY', color: Colors.white70),
          const _SoftBadge(
              text: 'POSITION DUPLICATE BLOCK', color: Colors.white70),
        ]),
        const SizedBox(height: 12),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _ResultPair(
              label: 'live_auto_buy_enabled',
              value: _boolText(result?.liveAutoBuyEnabled ??
                  settings.kisLiveAutoBuyEnabled)),
          _ResultPair(
              label: 'limited_auto_buy_enabled',
              value: _boolText(result?.limitedAutoBuyEnabled ??
                  settings.kisLimitedAutoBuyEnabled)),
          _ResultPair(
              label: 'buy_readiness_enabled',
              value: _boolText(result?.buyReadinessEnabled ??
                  settings.kisLimitedAutoBuyReadinessEnabled)),
          _ResultPair(
              label: 'auto_buy_execution_enabled',
              value: _boolText(result?.autoBuyEnabled ?? false)),
          _ResultPair(
              label: 'dry_run',
              value: _boolText(result?.dryRun ?? settings.dryRun)),
          _ResultPair(
              label: 'kill_switch',
              value: _boolText(result?.killSwitch ?? settings.killSwitch)),
          _ResultPair(
              label: 'kis_real_order_enabled',
              value: _boolText(result?.kisRealOrderEnabled ?? false)),
          _ResultPair(
              label: 'market_open',
              value: _boolText(result?.marketOpen ?? false)),
          _ResultPair(
              label: 'entry_allowed_now',
              value: _boolText(result?.entryAllowedNow ?? false)),
          _ResultPair(
              label: 'no new entry after',
              value: result?.noNewEntryAfter ??
                  settings.kisLimitedAutoBuyNoNewEntryAfter),
          _ResultPair(
              label: 'cash_available',
              value: _formatReviewKrwOrDash(result?.cashAvailable)),
          _ResultPair(
              label: 'total_asset_value',
              value: _formatReviewKrwOrDash(result?.totalAssetValue)),
          _ResultPair(
              label: 'estimated max notional',
              value: _formatReviewKrwOrDash(result?.estimatedMaxNotional)),
          _ResultPair(
              label: 'daily buy limit',
              value:
                  '${result?.dailyBuyCount ?? 0}/${result?.dailyBuyLimit ?? settings.kisLimitedAutoBuyMaxOrdersPerDay}'),
          _ResultPair(
              label: 'max notional pct',
              value: _formatPercentValue((result?.maxNotionalPct ??
                      settings.kisLimitedAutoBuyMaxNotionalPct) *
                  100)),
        ]),
        const SizedBox(height: 12),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            OutlinedButton.icon(
              onPressed: controller.kisLimitedAutoBuyLoading
                  ? null
                  : () async {
                      final actionResult =
                          await controller.refreshKisLimitedAutoBuyStatus();
                      if (!context.mounted) return;
                      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                        content: Text(actionResult.message),
                        backgroundColor: actionResult.success
                            ? Colors.green
                            : Colors.redAccent,
                      ));
                    },
              icon: const Icon(Icons.refresh),
              label: const Text('Refresh Buy Status'),
            ),
            OutlinedButton.icon(
              onPressed: controller.kisLimitedAutoBuyLoading
                  ? null
                  : () async {
                      final actionResult =
                          await controller.runKisLimitedAutoBuyPreflightOnce();
                      if (!context.mounted) return;
                      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                        content: Text(actionResult.message),
                        backgroundColor: actionResult.success
                            ? Colors.green
                            : Colors.redAccent,
                      ));
                    },
              icon: const Icon(Icons.fact_check_outlined),
              label: const Text('Run Buy Preflight'),
            ),
            FilledButton.icon(
              onPressed: controller.kisLimitedAutoBuyLoading
                  ? null
                  : () async {
                      final actionResult =
                          await controller.runKisLimitedAutoBuyOnce();
                      if (!context.mounted) return;
                      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                        content: Text(actionResult.message),
                        backgroundColor: actionResult.success
                            ? Colors.green
                            : Colors.redAccent,
                      ));
                    },
              icon: controller.kisLimitedAutoBuyLoading
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.play_arrow),
              label: Text(controller.kisLimitedAutoBuyLoading
                  ? 'Running buy readiness...'
                  : 'Run Limited Buy Once'),
            ),
          ],
        ),
        if (controller.kisLimitedAutoBuyError != null) ...[
          const SizedBox(height: 10),
          _StateLine(
              text: _primaryLine(controller.kisLimitedAutoBuyError!),
              color: Colors.redAccent),
        ],
        if (result == null) ...[
          const SizedBox(height: 10),
          const _StateLine(
            text:
                'No limited buy readiness check yet. Default backend state blocks execution.',
          ),
        ] else ...[
          const SizedBox(height: 10),
          _KisLimitedAutoBuyResultPanel(result: result),
        ],
      ]),
    );
  }
}

class _KisLimitedAutoBuyReviewCard extends StatelessWidget {
  const _KisLimitedAutoBuyReviewCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final review = controller.latestKisLimitedAutoBuyReview;
    final summary = review?.summary;
    return Container(
      key: const Key('kis_limited_auto_buy_review_card'),
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: _panelDecoration(),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.rate_review_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text('KIS Limited Buy Review',
                style: Theme.of(context).textTheme.titleSmall),
          ),
        ]),
        const SizedBox(height: 8),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(text: 'BUY REVIEW ONLY', color: Colors.greenAccent),
          _SoftBadge(text: 'READINESS QUALITY', color: Colors.lightBlueAccent),
          _SoftBadge(text: 'NO BROKER SUBMIT', color: Colors.redAccent),
          _SoftBadge(text: 'AUTO BUY DISABLED', color: Colors.amberAccent),
          _SoftBadge(
              text: 'SCHEDULER REAL ORDERS DISABLED', color: Colors.redAccent),
        ]),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          onPressed: controller.kisLimitedAutoBuyReviewLoading
              ? null
              : () async {
                  final actionResult =
                      await controller.refreshKisLimitedAutoBuyReview();
                  if (!context.mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(actionResult.message),
                    backgroundColor:
                        actionResult.success ? Colors.green : Colors.redAccent,
                  ));
                },
          icon: controller.kisLimitedAutoBuyReviewLoading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.refresh),
          label: Text(controller.kisLimitedAutoBuyReviewLoading
              ? 'Refreshing review...'
              : 'Refresh Review'),
        ),
        if (controller.kisLimitedAutoBuyReviewError != null) ...[
          const SizedBox(height: 10),
          _StateLine(
            text: _primaryLine(controller.kisLimitedAutoBuyReviewError!),
            color: Colors.redAccent,
          ),
        ],
        const SizedBox(height: 12),
        if (review == null || review.recentDecisions.isEmpty) ...[
          const _StateLine(
            text:
                'No limited buy readiness decisions yet. Run Buy Preflight or Run Limited Buy Once to generate review data.',
          ),
        ] else ...[
          Wrap(spacing: 14, runSpacing: 8, children: [
            _ResultPair(
                label: 'total runs', value: summary!.totalRuns.toString()),
            _ResultPair(
                label: 'BUY READY count',
                value: summary.buyReadyCount.toString()),
            _ResultPair(
                label: 'blocked count', value: summary.blockedCount.toString()),
            _ResultPair(
                label: 'no candidate count',
                value: summary.noCandidateCount.toString()),
            _ResultPair(
                label: 'top block reason',
                value: _limitedBuyReviewTopReason(review)),
            _ResultPair(
                label: 'avg final buy score',
                value: _score(summary.avgFinalBuyScore)),
            _ResultPair(
                label: 'avg required score',
                value: _score(summary.avgRequiredBuyScore)),
            _ResultPair(
                label: 'latest run time',
                value: summary.latestRunAt == null
                    ? 'n/a'
                    : formatTimestampWithKst(summary.latestRunAt)),
            _ResultPair(
                label: 'latest candidate',
                value: _reviewCandidateLabel(
                  summary.latestCandidateSymbol,
                  summary.latestCandidateCompany,
                )),
            _ResultPair(
                label: 'no submit invariant',
                value: _yesNo(summary.noSubmitInvariantOk)),
          ]),
          if (review.topBlockReasons.isNotEmpty) ...[
            const SizedBox(height: 12),
            const Text('Top Block Reasons',
                style: TextStyle(fontWeight: FontWeight.w700)),
            const SizedBox(height: 8),
            Wrap(spacing: 8, runSpacing: 8, children: [
              for (final reason in review.topBlockReasons)
                _SoftBadge(
                  text: '${reason.label}: ${reason.count}',
                  color: Colors.amberAccent,
                ),
            ]),
          ],
          const SizedBox(height: 12),
          const Text('Recent Decisions',
              style: TextStyle(fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          for (final decision in review.recentDecisions) ...[
            _KisLimitedAutoBuyReviewDecisionCard(decision: decision),
            const SizedBox(height: 8),
          ],
          ExpansionTile(
            tilePadding: EdgeInsets.zero,
            childrenPadding: EdgeInsets.zero,
            title: const Text('Developer Raw Payload'),
            children: [
              _StateLine(text: _prettyJson(review.rawPayload)),
            ],
          ),
        ],
      ]),
    );
  }
}

class _KisLimitedAutoBuyReviewDecisionCard extends StatelessWidget {
  const _KisLimitedAutoBuyReviewDecisionCard({required this.decision});

  final KisLimitedAutoBuyReviewDecision decision;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Text(
              _reviewCandidateLabel(decision.symbol, decision.companyName),
              style: Theme.of(context).textTheme.titleSmall,
            ),
          ),
          _SoftBadge(
            text: decision.status,
            color: _reviewStatusColor(decision.status),
          ),
        ]),
        const SizedBox(height: 8),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _ResultPair(
            label: 'final buy / required',
            value:
                '${_score(decision.finalBuyScore)} / ${_score(decision.requiredBuyScore)}',
          ),
          _ResultPair(
            label: 'final sell score',
            value: _score(decision.finalSellScore),
          ),
          _ResultPair(
            label: 'estimated notional',
            value: _formatReviewKrwOrDash(decision.estimatedNotional),
          ),
          _ResultPair(
            label: 'reason',
            value: decision.reason.isEmpty ? 'n/a' : decision.reason,
          ),
          _ResultPair(
            label: 'created_at',
            value: decision.createdAt == null
                ? 'n/a'
                : formatTimestampWithKst(decision.createdAt),
          ),
        ]),
        const SizedBox(height: 8),
        _StateLine(text: 'block reasons: ${_joinList(decision.blockReasons)}'),
        const SizedBox(height: 8),
        Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(
            text: 'Broker submit: ${_yesNo(decision.brokerSubmitCalled)}',
            color: Colors.lightBlueAccent,
          ),
          _SoftBadge(
            text:
                'Real order submitted: ${_yesNo(decision.realOrderSubmitted)}',
            color: Colors.lightBlueAccent,
          ),
          _SoftBadge(
            text: 'Manual submit: ${_yesNo(decision.manualSubmitCalled)}',
            color: Colors.lightBlueAccent,
          ),
        ]),
      ]),
    );
  }
}

class _KisLimitedAutoBuyExecutionReviewCard extends StatelessWidget {
  const _KisLimitedAutoBuyExecutionReviewCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final review = controller.latestKisLimitedAutoBuyExecutionReview;
    final summary = review?.summary;
    return Container(
      key: const Key('kis_limited_auto_buy_execution_review_card'),
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: _panelDecoration(),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.verified_user_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text('KIS Limited Buy Execution Review',
                style: Theme.of(context).textTheme.titleSmall),
          ),
        ]),
        const SizedBox(height: 8),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(text: 'BUY EXECUTION REVIEW', color: Colors.greenAccent),
          _SoftBadge(text: 'OPERATOR AUDIT', color: Colors.lightBlueAccent),
          _SoftBadge(text: 'REVIEW ONLY', color: Colors.white70),
          _SoftBadge(text: 'NO BROKER SUBMIT', color: Colors.redAccent),
          _SoftBadge(
              text: 'SCHEDULER REAL ORDERS DISABLED', color: Colors.redAccent),
          _SoftBadge(text: 'SAFETY INVARIANTS', color: Colors.amberAccent),
        ]),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          onPressed: controller.kisLimitedAutoBuyExecutionReviewLoading
              ? null
              : () async {
                  final actionResult = await controller
                      .refreshKisLimitedAutoBuyExecutionReview();
                  if (!context.mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(actionResult.message),
                    backgroundColor:
                        actionResult.success ? Colors.green : Colors.redAccent,
                  ));
                },
          icon: controller.kisLimitedAutoBuyExecutionReviewLoading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.refresh),
          label: Text(controller.kisLimitedAutoBuyExecutionReviewLoading
              ? 'Refreshing execution review...'
              : 'Refresh Execution Review'),
        ),
        if (controller.kisLimitedAutoBuyExecutionReviewError != null) ...[
          const SizedBox(height: 10),
          _StateLine(
            text:
                _primaryLine(controller.kisLimitedAutoBuyExecutionReviewError!),
            color: Colors.redAccent,
          ),
        ],
        const SizedBox(height: 12),
        if (review == null ||
            (review.submittedBuys.isEmpty &&
                review.blockedDecisions.isEmpty &&
                review.safetyViolations.isEmpty)) ...[
          const _StateLine(
            text:
                'No guarded limited buy execution audit rows found for the selected window.',
          ),
        ] else ...[
          Wrap(spacing: 14, runSpacing: 8, children: [
            _ResultPair(
              label: 'submitted buy count',
              value: summary!.submittedBuyCount.toString(),
            ),
            _ResultPair(
              label: 'blocked count',
              value: summary.blockedCount.toString(),
            ),
            _ResultPair(
              label: 'readiness-only count',
              value: summary.readinessOnlyCount.toString(),
            ),
            _ResultPair(
              label: 'no-submit invariant',
              value: _yesNo(summary.noSubmitInvariantOk),
            ),
            _ResultPair(
              label: 'audit metadata',
              value: _yesNo(summary.submittedRowsHaveAuditMetadata),
            ),
            _ResultPair(
              label: 'latest submitted time',
              value: summary.latestSubmittedAt == null
                  ? 'n/a'
                  : formatTimestampWithKst(summary.latestSubmittedAt),
            ),
            _ResultPair(
              label: 'latest symbol',
              value: summary.latestSymbol ?? 'n/a',
            ),
            _ResultPair(
              label: 'max daily buy count observed',
              value: summary.maxDailyBuyCountObserved.toString(),
            ),
            _ResultPair(
              label: 'top block reason',
              value: _limitedBuyExecutionTopReason(review),
            ),
          ]),
          const SizedBox(height: 12),
          if (review.safetyViolations.isEmpty)
            const _StateLine(text: 'No safety violations detected')
          else ...[
            const Text('Safety Violations',
                style: TextStyle(fontWeight: FontWeight.w700)),
            const SizedBox(height: 8),
            for (final violation in review.safetyViolations) ...[
              _KisLimitedAutoBuySafetyViolationCard(violation: violation),
              const SizedBox(height: 8),
            ],
          ],
          if (review.submittedBuys.isNotEmpty) ...[
            const SizedBox(height: 12),
            const Text('Submitted Buy Audit',
                style: TextStyle(fontWeight: FontWeight.w700)),
            const SizedBox(height: 8),
            for (final item in review.submittedBuys) ...[
              _KisLimitedAutoBuySubmittedAuditCard(item: item),
              const SizedBox(height: 8),
            ],
          ],
          if (review.blockedDecisions.isNotEmpty) ...[
            const SizedBox(height: 12),
            const Text('Blocked Decisions',
                style: TextStyle(fontWeight: FontWeight.w700)),
            const SizedBox(height: 8),
            for (final item in review.blockedDecisions) ...[
              _KisLimitedAutoBuyBlockedAuditCard(item: item),
              const SizedBox(height: 8),
            ],
          ],
          ExpansionTile(
            tilePadding: EdgeInsets.zero,
            childrenPadding: EdgeInsets.zero,
            title: const Text('Developer Raw Payload'),
            children: [
              _StateLine(text: _prettyJson(review.rawPayload)),
            ],
          ),
        ],
      ]),
    );
  }
}

class _KisLimitedAutoBuySubmittedAuditCard extends StatelessWidget {
  const _KisLimitedAutoBuySubmittedAuditCard({required this.item});

  final KisLimitedAutoBuySubmittedAuditItem item;

  @override
  Widget build(BuildContext context) {
    final status = _firstText([
      item.internalStatus,
      item.brokerStatus,
      item.realOrderSubmitted ? 'SUBMITTED' : 'AUDIT',
    ]).toUpperCase();
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: _panelDecoration(),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Text(
              _reviewCandidateLabel(item.symbol, item.companyName),
              style: Theme.of(context).textTheme.titleSmall,
            ),
          ),
          _SoftBadge(
            text: status,
            color: item.realOrderSubmitted
                ? Colors.greenAccent
                : Colors.amberAccent,
          ),
        ]),
        const SizedBox(height: 8),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _ResultPair(
              label: 'quantity', value: item.quantity?.toString() ?? 'n/a'),
          _ResultPair(
              label: 'estimated notional',
              value: _formatReviewKrwOrDash(item.estimatedNotional)),
          _ResultPair(
              label: 'order id',
              value: item.orderId == null ? 'n/a' : item.orderId.toString()),
          _ResultPair(label: 'KIS ODNO', value: item.kisOdno ?? 'n/a'),
          _ResultPair(
            label: 'buy score / required',
            value:
                '${_score(item.finalBuyScore)} / ${_score(item.requiredBuyScore)}',
          ),
          _ResultPair(
              label: 'validation called', value: _yesNo(item.validationCalled)),
          _ResultPair(
              label: 'manual submit called',
              value: _yesNo(item.manualSubmitCalled)),
          _ResultPair(
              label: 'broker submit called',
              value: _yesNo(item.brokerSubmitCalled)),
        ]),
        const SizedBox(height: 8),
        _StateLine(
          text:
              'runtime safety snapshot: ${_auditSnapshotLabel(item.runtimeSafetySnapshot)}',
        ),
        if (item.validationSummary.isNotEmpty) ...[
          const SizedBox(height: 8),
          _StateLine(
            text:
                'validation summary: ${_auditSnapshotLabel(item.validationSummary)}',
          ),
        ],
      ]),
    );
  }
}

class _KisLimitedAutoBuyBlockedAuditCard extends StatelessWidget {
  const _KisLimitedAutoBuyBlockedAuditCard({required this.item});

  final KisLimitedAutoBuyBlockedDecisionItem item;

  @override
  Widget build(BuildContext context) {
    final primary = item.primaryBlockReason ??
        (item.blockReasons.isEmpty ? 'n/a' : item.blockReasons.first);
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: _panelDecoration(),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Text(
              _reviewCandidateLabel(item.symbol, item.companyName),
              style: Theme.of(context).textTheme.titleSmall,
            ),
          ),
          const _SoftBadge(text: 'BLOCKED', color: Colors.amberAccent),
        ]),
        const SizedBox(height: 8),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _ResultPair(label: 'primary block reason', value: primary),
          _ResultPair(
            label: 'score vs required',
            value:
                '${_score(item.finalBuyScore)} / ${_score(item.requiredBuyScore)}',
          ),
          _ResultPair(
            label: 'estimated notional',
            value: _formatReviewKrwOrDash(item.estimatedNotional),
          ),
          _ResultPair(
              label: 'Broker submit', value: _yesNo(item.brokerSubmitCalled)),
          _ResultPair(
              label: 'real order submitted',
              value: _yesNo(item.realOrderSubmitted)),
        ]),
        if (item.blockReasons.isNotEmpty) ...[
          const SizedBox(height: 8),
          _StateLine(text: 'block reasons: ${_joinList(item.blockReasons)}'),
        ],
        const SizedBox(height: 8),
        Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(
            text: 'Broker submit: ${_yesNo(item.brokerSubmitCalled)}',
            color: Colors.lightBlueAccent,
          ),
          _SoftBadge(
            text: 'Real order submitted: ${_yesNo(item.realOrderSubmitted)}',
            color: Colors.lightBlueAccent,
          ),
        ]),
      ]),
    );
  }
}

class _KisLimitedAutoBuySafetyViolationCard extends StatelessWidget {
  const _KisLimitedAutoBuySafetyViolationCard({required this.violation});

  final KisLimitedAutoBuySafetyViolation violation;

  @override
  Widget build(BuildContext context) {
    final affected = _joinList([
      if (violation.symbol != null) 'symbol ${violation.symbol}',
      if (violation.orderId != null) 'order ${violation.orderId}',
      if (violation.runId != null) 'run ${violation.runId}',
    ]);
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.redAccent.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.redAccent.withValues(alpha: 0.35)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.warning_amber_outlined,
              size: 18, color: Colors.redAccent),
          const SizedBox(width: 8),
          Expanded(
            child: Text(violation.code,
                style: Theme.of(context).textTheme.titleSmall),
          ),
          const _SoftBadge(text: 'SAFETY VIOLATION', color: Colors.redAccent),
        ]),
        const SizedBox(height: 8),
        _StateLine(text: violation.reason, color: Colors.redAccent),
        const SizedBox(height: 8),
        _StateLine(text: 'Affected: $affected'),
      ]),
    );
  }
}

class _KisLimitedAutoBuyResultPanel extends StatelessWidget {
  const _KisLimitedAutoBuyResultPanel({required this.result});

  final KisLimitedAutoBuy result;

  @override
  Widget build(BuildContext context) {
    final statusLabel = result.submitted
        ? 'SUBMITTED'
        : result.result == 'blocked'
            ? 'BLOCKED'
            : result.buyReady
                ? 'BUY READY'
                : 'HOLD';
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      if (result.submitted) ...[
        _StateLine(
          text:
              'SUBMITTED BUY: order ${result.orderId ?? 'n/a'} / ODNO ${result.kisOdno ?? result.brokerOrderId ?? 'n/a'}',
          color: Colors.greenAccent,
        ),
        const SizedBox(height: 10),
      ],
      Wrap(spacing: 8, runSpacing: 8, children: [
        _SoftBadge(
          text: statusLabel,
          color: result.submitted ? Colors.greenAccent : Colors.amberAccent,
        ),
        _SoftBadge(
          text: result.action.toUpperCase(),
          color: Colors.lightBlueAccent,
        ),
        _SoftBadge(
          text: 'Broker submit: ${_yesNo(result.brokerSubmitCalled)}',
          color:
              result.brokerSubmitCalled ? Colors.greenAccent : Colors.white70,
        ),
        _SoftBadge(
          text: 'Real order submitted: ${_yesNo(result.realOrderSubmitted)}',
          color:
              result.realOrderSubmitted ? Colors.greenAccent : Colors.white70,
        ),
        _SoftBadge(
          text: 'Validation called: ${_yesNo(result.validationCalled)}',
          color: result.validationCalled ? Colors.greenAccent : Colors.white70,
        ),
      ]),
      const SizedBox(height: 10),
      Wrap(spacing: 14, runSpacing: 8, children: [
        _ResultPair(label: 'result', value: result.result),
        _ResultPair(label: 'action', value: result.action),
        _ResultPair(label: 'reason', value: result.reason),
        _ResultPair(
            label: 'primary block', value: result.primaryBlockReason ?? 'n/a'),
        _ResultPair(label: 'symbol', value: result.symbol ?? 'n/a'),
        _ResultPair(
            label: 'quantity', value: result.quantity?.toString() ?? 'n/a'),
        _ResultPair(
            label: 'notional', value: _formatReviewKrwOrDash(result.notional)),
        _ResultPair(
            label: 'order id', value: result.orderId?.toString() ?? 'none'),
        _ResultPair(
            label: 'KIS ODNO',
            value: result.kisOdno ?? result.brokerOrderId ?? 'none'),
        _ResultPair(
            label: 'final buy score', value: _score(result.finalBuyScore)),
        _ResultPair(
            label: 'required score', value: _score(result.requiredBuyScore)),
        _ResultPair(
            label: 'final sell score', value: _score(result.finalSellScore)),
        _ResultPair(label: 'confidence', value: _score(result.confidence)),
        _ResultPair(
            label: 'buy-sell spread', value: _score(result.buySellSpread)),
        _ResultPair(
            label: 'real_order_submitted',
            value: _boolText(result.realOrderSubmitted)),
        _ResultPair(
            label: 'broker_submit_called',
            value: _boolText(result.brokerSubmitCalled)),
        _ResultPair(
            label: 'manual_submit_called',
            value: _boolText(result.manualSubmitCalled)),
        _ResultPair(
            label: 'validation_called',
            value: _boolText(result.validationCalled)),
      ]),
      if (result.blockReasons.isNotEmpty) ...[
        const SizedBox(height: 8),
        _StateLine(text: 'block_reasons: ${_joinList(result.blockReasons)}'),
      ],
      const SizedBox(height: 10),
      Wrap(spacing: 8, runSpacing: 8, children: [
        const _SoftBadge(
            text: 'BUY GUARDED EXECUTION', color: Colors.greenAccent),
        _SoftBadge(
          text:
              result.autoBuyEnabled ? 'AUTO BUY ENABLED' : 'AUTO BUY DISABLED',
          color:
              result.autoBuyEnabled ? Colors.greenAccent : Colors.amberAccent,
        ),
        _SoftBadge(
          text: result.brokerSubmitCalled
              ? 'BROKER SUBMIT RECORDED'
              : 'NO BROKER SUBMIT',
          color:
              result.brokerSubmitCalled ? Colors.greenAccent : Colors.redAccent,
        ),
        const _SoftBadge(
            text: 'SCHEDULER REAL ORDERS DISABLED', color: Colors.redAccent),
        const _SoftBadge(text: 'DEFAULT OFF', color: Colors.amberAccent),
        const _SoftBadge(text: 'MAX 1 BUY / DAY', color: Colors.white70),
        const _SoftBadge(
            text: 'POSITION DUPLICATE BLOCK', color: Colors.white70),
        _SoftBadge(
          text: 'auto_buy_enabled=${_boolText(result.autoBuyEnabled)}',
          color: Colors.orangeAccent,
        ),
        _SoftBadge(
          text:
              'scheduler_real_orders_enabled=${_boolText(result.schedulerRealOrdersEnabled)}',
          color: Colors.orangeAccent,
        ),
      ]),
      if (result.finalCandidate != null) ...[
        const SizedBox(height: 12),
        const Text('Final Candidate',
            style: TextStyle(fontWeight: FontWeight.w700)),
        const SizedBox(height: 8),
        _KisLimitedAutoBuyCandidateCard(candidate: result.finalCandidate!),
      ],
      if (result.candidates.isNotEmpty) ...[
        const SizedBox(height: 12),
        const Text('Candidates', style: TextStyle(fontWeight: FontWeight.w700)),
        const SizedBox(height: 8),
        for (final candidate in result.candidates)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: _KisLimitedAutoBuyCandidateCard(candidate: candidate),
          ),
      ],
      const SizedBox(height: 4),
      ExpansionTile(
        tilePadding: EdgeInsets.zero,
        childrenPadding: EdgeInsets.zero,
        title: const Text('Developer Raw Payload'),
        children: [
          _StateLine(text: _prettyJson(result.rawPayload)),
        ],
      ),
    ]);
  }
}

class _KisLimitedAutoBuyCandidateCard extends StatelessWidget {
  const _KisLimitedAutoBuyCandidateCard({required this.candidate});

  final KisLimitedAutoBuyCandidate candidate;

  @override
  Widget build(BuildContext context) {
    final name = candidate.companyName;
    final whyNoOrder = candidate.blockReasons.isNotEmpty
        ? _joinList(candidate.blockReasons)
        : 'auto_buy_execution_disabled';
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: _panelDecoration(),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Text(
              name == null ? candidate.symbol : '${candidate.symbol} · $name',
              style: Theme.of(context).textTheme.titleSmall,
            ),
          ),
          _SoftBadge(
            text: candidate.status,
            color: candidate.entryReady
                ? Colors.greenAccent
                : candidate.status == 'WATCH'
                    ? Colors.lightBlueAccent
                    : Colors.amberAccent,
          ),
        ]),
        const SizedBox(height: 8),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _ResultPair(
              label: 'current price',
              value: _formatReviewKrwOrDash(candidate.currentPrice)),
          _ResultPair(
              label: 'suggested quantity',
              value: candidate.suggestedQuantity?.toString() ?? 'n/a'),
          _ResultPair(
              label: 'estimated notional',
              value: _formatReviewKrwOrDash(candidate.estimatedNotional)),
          _ResultPair(
              label: 'cash available',
              value: _formatReviewKrwOrDash(candidate.availableCash)),
          _ResultPair(
              label: 'final buy / required',
              value:
                  '${_score(candidate.finalBuyScore)} / ${_score(candidate.requiredBuyScore)}'),
          _ResultPair(
              label: 'final sell score',
              value: _score(candidate.finalSellScore)),
          _ResultPair(label: 'confidence', value: _score(candidate.confidence)),
          _ResultPair(
              label: 'buy-sell spread', value: _score(candidate.buySellSpread)),
        ]),
        const SizedBox(height: 8),
        _StateLine(text: 'why no order: $whyNoOrder'),
        const SizedBox(height: 8),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _ResultPair(
              label: 'duplicate position',
              value: _boolText(candidate.duplicatePosition)),
          _ResultPair(
              label: 'duplicate open buy',
              value: _boolText(candidate.duplicateOpenOrder)),
          _ResultPair(
              label: 'cash sufficient',
              value: _boolText(candidate.cashSufficient)),
          _ResultPair(
              label: 'market session allowed',
              value: _boolText(candidate.marketSessionAllowed)),
          _ResultPair(
              label: 'no_new_entry_after blocked',
              value: _boolText(candidate.noNewEntryAfterBlocked)),
        ]),
        const SizedBox(height: 8),
        _StateLine(
          text:
              "technical: EMA20=${_tech(candidate, 'EMA20')}, EMA50=${_tech(candidate, 'EMA50')}, VWAP=${_tech(candidate, 'VWAP')}, RSI=${_tech(candidate, 'RSI')}, ATR=${_tech(candidate, 'ATR')}, volume_ratio=${_tech(candidate, 'volume_ratio')}, recent_return=${_tech(candidate, 'recent_return')}, momentum=${_tech(candidate, 'momentum')}, price_position=${_tech(candidate, 'price_position')}",
        ),
        if (candidate.gptReason != null) ...[
          const SizedBox(height: 8),
          _StateLine(text: 'GPT reason: ${candidate.gptReason}'),
        ],
      ]),
    );
  }
}

String _tech(KisLimitedAutoBuyCandidate candidate, String key) {
  final value = candidate.technicalSnapshot[key];
  if (value == null) return 'n/a';
  if (value is num) return _score(value.toDouble());
  return value.toString();
}

class _KisSchedulerReadinessCard extends StatelessWidget {
  const _KisSchedulerReadinessCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final result = controller.latestKisSchedulerReadiness;
    final summary = result?.summary;
    return Container(
      key: const Key('kis_scheduler_readiness_card'),
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: _panelDecoration(),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.event_available_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text('KIS Scheduler Readiness / Schedule Audit',
                style: Theme.of(context).textTheme.titleSmall),
          ),
        ]),
        const SizedBox(height: 8),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(
              text: 'SCHEDULER READINESS', color: Colors.lightBlueAccent),
          _SoftBadge(text: 'SCHEDULE AUDIT', color: Colors.lightBlueAccent),
          _SoftBadge(text: 'READINESS ONLY', color: Colors.greenAccent),
          _SoftBadge(text: 'REAL ORDERS DISABLED', color: Colors.redAccent),
          _SoftBadge(text: 'NO BROKER SUBMIT', color: Colors.orangeAccent),
          _SoftBadge(text: 'DRY-RUN SAFE', color: Colors.white70),
          _SoftBadge(text: 'DEFAULT OFF', color: Colors.amberAccent),
        ]),
        const SizedBox(height: 12),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _ResultPair(
            label: 'scheduler enabled',
            value: _boolText(summary?.schedulerEnabled ??
                controller.settings.schedulerEnabled),
          ),
          _ResultPair(
            label: 'KIS scheduler enabled',
            value: _boolText(summary?.kisSchedulerEnabled ?? false),
          ),
          _ResultPair(
            label: 'scheduler dry-run',
            value: _boolText(summary?.kisSchedulerDryRun ?? true),
          ),
          _ResultPair(
            label: 'real orders allowed',
            value: _yesNo(summary?.realOrderSubmitAllowed ?? false),
          ),
          _ResultPair(
            label: 'market open',
            value: _boolText(summary?.marketOpen ?? false),
          ),
          _ResultPair(
            label: 'entry allowed now',
            value: _boolText(summary?.entryAllowedNow ?? false),
          ),
          _ResultPair(
            label: 'sell session allowed',
            value: _boolText(summary?.sellSessionAllowed ?? false),
          ),
          _ResultPair(
            label: 'next scheduled slot',
            value: _schedulerSlotLabel(summary?.nextScheduledSlot),
          ),
          _ResultPair(
            label: 'readiness status',
            value: summary?.readinessStatus ?? 'DISABLED',
          ),
          _ResultPair(
            label: 'primary block reason',
            value: summary?.primaryBlockReason ?? 'not_loaded',
          ),
        ]),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          onPressed: controller.kisSchedulerReadinessLoading
              ? null
              : () async {
                  final actionResult =
                      await controller.refreshKisSchedulerReadiness();
                  if (!context.mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(actionResult.message),
                    backgroundColor:
                        actionResult.success ? Colors.green : Colors.redAccent,
                  ));
                },
          icon: controller.kisSchedulerReadinessLoading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.refresh, size: 18),
          label: Text(controller.kisSchedulerReadinessLoading
              ? 'Refreshing scheduler readiness...'
              : 'Refresh Scheduler Readiness'),
        ),
        if (controller.kisSchedulerReadinessError != null) ...[
          const SizedBox(height: 10),
          _StateLine(
            text: _primaryLine(controller.kisSchedulerReadinessError!),
            color: Colors.redAccent,
          ),
        ],
        const SizedBox(height: 12),
        if (result == null) ...[
          const _StateLine(
            text:
                'No scheduler readiness data yet. Default scheduler state remains off.',
          ),
        ] else ...[
          _KisSchedulerReadinessSummaryPanel(result: result),
          const SizedBox(height: 12),
          _KisSchedulerScheduleAudit(schedule: result.schedule),
          const SizedBox(height: 12),
          _KisSchedulerModuleAudit(modules: result.modules),
          const SizedBox(height: 12),
          _KisSchedulerRecentRuns(runs: result.recentRuns),
          const SizedBox(height: 4),
          ExpansionTile(
            tilePadding: EdgeInsets.zero,
            childrenPadding: EdgeInsets.zero,
            title: const Text('Developer Raw Payload'),
            children: [
              _StateLine(text: _prettyJson(result.rawPayload)),
            ],
          ),
        ],
      ]),
    );
  }
}

class _KisSchedulerReadinessSummaryPanel extends StatelessWidget {
  const _KisSchedulerReadinessSummaryPanel({required this.result});

  final KisSchedulerReadiness result;

  @override
  Widget build(BuildContext context) {
    final summary = result.summary;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Readiness Summary',
          style: TextStyle(fontWeight: FontWeight.w700)),
      const SizedBox(height: 8),
      Wrap(spacing: 14, runSpacing: 8, children: [
        _ResultPair(label: 'provider', value: result.provider),
        _ResultPair(label: 'market', value: result.market),
        _ResultPair(label: 'mode', value: result.mode),
        _ResultPair(
            label: 'readiness only', value: _yesNo(result.readinessOnly)),
        _ResultPair(
          label: 'real order submitted',
          value: _yesNo(result.realOrderSubmitted),
        ),
        _ResultPair(
          label: 'broker submit',
          value: _yesNo(result.brokerSubmitCalled),
        ),
        _ResultPair(
          label: 'manual submit',
          value: _yesNo(result.manualSubmitCalled),
        ),
        _ResultPair(
          label: 'current slot',
          value: summary.currentSlotLabel ?? 'n/a',
        ),
      ]),
      if (summary.blockReasons.isNotEmpty) ...[
        const SizedBox(height: 8),
        _StateLine(
          text: 'block_reasons: ${_joinList(summary.blockReasons)}',
        ),
      ],
    ]);
  }
}

class _KisSchedulerScheduleAudit extends StatelessWidget {
  const _KisSchedulerScheduleAudit({required this.schedule});

  final List<KisSchedulerScheduleItem> schedule;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Schedule Audit',
          style: TextStyle(fontWeight: FontWeight.w700)),
      const SizedBox(height: 8),
      if (schedule.isEmpty)
        const _StateLine(text: 'No scheduler slots returned.')
      else
        for (final slot in schedule)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: _panelDecoration(),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${slot.displayLabel} / ${slot.scheduledTime} / ${slot.timezone}',
                    style: const TextStyle(fontWeight: FontWeight.w800),
                  ),
                  const SizedBox(height: 8),
                  Wrap(spacing: 14, runSpacing: 8, children: [
                    _ResultPair(label: 'purpose', value: slot.purpose),
                    _ResultPair(
                        label: 'enabled', value: _boolText(slot.enabled)),
                    _ResultPair(
                        label: 'dry-run only', value: _yesNo(slot.dryRunOnly)),
                    _ResultPair(
                      label: 'real order allowed',
                      value: _yesNo(slot.realOrderAllowed),
                    ),
                  ]),
                  if (slot.notes.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    _StateLine(text: 'notes: ${_joinList(slot.notes)}'),
                  ],
                ],
              ),
            ),
          ),
    ]);
  }
}

class _KisSchedulerModuleAudit extends StatelessWidget {
  const _KisSchedulerModuleAudit({required this.modules});

  final KisSchedulerReadinessModules modules;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Modules', style: TextStyle(fontWeight: FontWeight.w700)),
      const SizedBox(height: 8),
      _KisSchedulerModulePanel(
        title: 'Limited Auto Sell',
        module: modules.limitedAutoSell,
        pairs: [
          _ResultPair(
            label: 'stop-loss execution enabled',
            value: _boolText(modules.limitedAutoSell.stopLossExecutionEnabled),
          ),
          _ResultPair(
            label: 'take-profit execution enabled',
            value:
                _boolText(modules.limitedAutoSell.takeProfitExecutionEnabled),
          ),
          _ResultPair(
            label: 'ready for scheduler dry-run',
            value: _yesNo(modules.limitedAutoSell.readyForSchedulerDryRun),
          ),
          _ResultPair(
            label: 'ready for scheduler real order',
            value: _yesNo(modules.limitedAutoSell.readyForSchedulerRealOrder),
          ),
        ],
      ),
      const SizedBox(height: 8),
      _KisSchedulerModulePanel(
        title: 'Limited Auto Buy',
        module: modules.limitedAutoBuy,
        pairs: [
          _ResultPair(
            label: 'buy execution enabled',
            value: _boolText(modules.limitedAutoBuy.autoBuyExecutionEnabled),
          ),
          _ResultPair(
            label: 'ready for scheduler dry-run',
            value: _yesNo(modules.limitedAutoBuy.readyForSchedulerDryRun),
          ),
          _ResultPair(
            label: 'ready for scheduler real order',
            value: _yesNo(modules.limitedAutoBuy.readyForSchedulerRealOrder),
          ),
        ],
      ),
      const SizedBox(height: 8),
      _KisSchedulerModulePanel(
        title: 'Execution reviews',
        module: modules.executionReview,
        pairs: [
          _ResultPair(
            label: 'read-only',
            value: _yesNo(modules.executionReview.readOnly),
          ),
          _ResultPair(
            label: 'available',
            value: _yesNo(modules.executionReview.available),
          ),
        ],
      ),
    ]);
  }
}

class _KisSchedulerModulePanel extends StatelessWidget {
  const _KisSchedulerModulePanel({
    required this.title,
    required this.module,
    required this.pairs,
  });

  final String title;
  final KisSchedulerModuleStatus module;
  final List<Widget> pairs;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: _panelDecoration(),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Text(title,
                style: const TextStyle(fontWeight: FontWeight.w800)),
          ),
          _SoftBadge(
            text: module.available ? 'AVAILABLE' : 'UNAVAILABLE',
            color: module.available ? Colors.greenAccent : Colors.amberAccent,
          ),
        ]),
        const SizedBox(height: 8),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _ResultPair(
            label: 'status endpoint',
            value:
                module.statusEndpoint.isEmpty ? 'n/a' : module.statusEndpoint,
          ),
          _ResultPair(
            label: 'daily limit remaining',
            value: module.dailyLimitRemaining?.toString() ?? 'n/a',
          ),
          ...pairs,
        ]),
        if (module.blockReasons.isNotEmpty) ...[
          const SizedBox(height: 8),
          _StateLine(text: 'block reasons: ${_joinList(module.blockReasons)}'),
        ],
      ]),
    );
  }
}

class _KisSchedulerRecentRuns extends StatelessWidget {
  const _KisSchedulerRecentRuns({required this.runs});

  final List<KisSchedulerRecentRun> runs;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Recent Runs', style: TextStyle(fontWeight: FontWeight.w700)),
      const SizedBox(height: 8),
      if (runs.isEmpty)
        const _StateLine(text: 'No recent scheduler runs returned.')
      else
        for (final run in runs.take(5))
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: _panelDecoration(),
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${run.mode} / ${run.triggerSource}',
                      style: const TextStyle(fontWeight: FontWeight.w800),
                    ),
                    const SizedBox(height: 8),
                    Wrap(spacing: 14, runSpacing: 8, children: [
                      _ResultPair(label: 'result', value: run.result),
                      _ResultPair(label: 'symbol', value: run.symbol),
                      _ResultPair(
                        label: 'broker submit',
                        value: _yesNo(run.brokerSubmitCalled),
                      ),
                      _ResultPair(
                        label: 'real order submitted',
                        value: _yesNo(run.realOrderSubmitted),
                      ),
                      _ResultPair(
                        label: 'manual submit',
                        value: _yesNo(run.manualSubmitCalled),
                      ),
                    ]),
                    const SizedBox(height: 8),
                    Wrap(spacing: 8, runSpacing: 8, children: [
                      _SoftBadge(
                        text:
                            'Broker submit: ${_yesNo(run.brokerSubmitCalled)}',
                        color: Colors.lightBlueAccent,
                      ),
                      _SoftBadge(
                        text:
                            'Real order submitted: ${_yesNo(run.realOrderSubmitted)}',
                        color: Colors.lightBlueAccent,
                      ),
                    ]),
                    if (run.blockReasons.isNotEmpty) ...[
                      const SizedBox(height: 8),
                      _StateLine(
                        text: 'block reasons: ${_joinList(run.blockReasons)}',
                      ),
                    ],
                  ]),
            ),
          ),
    ]);
  }
}

class _KisSchedulerDryRunOrchestrationCard extends StatelessWidget {
  const _KisSchedulerDryRunOrchestrationCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final result = controller.latestKisSchedulerDryRunOrchestration;
    return Container(
      key: const Key('kis_scheduler_dry_run_orchestration_card'),
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: _panelDecoration(),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.account_tree_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text('KIS Scheduler Dry-run Orchestration',
                style: Theme.of(context).textTheme.titleSmall),
          ),
        ]),
        const SizedBox(height: 8),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(text: 'SCHEDULER DRY-RUN', color: Colors.greenAccent),
          _SoftBadge(text: 'ORCHESTRATION', color: Colors.lightBlueAccent),
          _SoftBadge(text: 'READINESS ONLY', color: Colors.greenAccent),
          _SoftBadge(text: 'REAL ORDERS DISABLED', color: Colors.redAccent),
          _SoftBadge(text: 'NO BROKER SUBMIT', color: Colors.orangeAccent),
          _SoftBadge(text: 'POSITION MANAGEMENT FIRST', color: Colors.white70),
          _SoftBadge(text: 'BUY AFTER SELL REVIEW', color: Colors.amberAccent),
        ]),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          onPressed: controller.kisSchedulerDryRunOrchestrationLoading
              ? null
              : () async {
                  final actionResult =
                      await controller.runKisSchedulerDryRunOrchestrationOnce();
                  if (!context.mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(actionResult.message),
                    backgroundColor:
                        actionResult.success ? Colors.green : Colors.redAccent,
                  ));
                },
          icon: controller.kisSchedulerDryRunOrchestrationLoading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.play_circle_outline, size: 18),
          label: Text(controller.kisSchedulerDryRunOrchestrationLoading
              ? 'Running scheduler dry-run...'
              : 'Run Scheduler Dry-run Once'),
        ),
        if (controller.kisSchedulerDryRunOrchestrationError != null) ...[
          const SizedBox(height: 10),
          _StateLine(
            text:
                _primaryLine(controller.kisSchedulerDryRunOrchestrationError!),
            color: Colors.redAccent,
          ),
        ],
        const SizedBox(height: 12),
        if (result == null) ...[
          const _StateLine(
            text:
                'No scheduler dry-run orchestration result yet. Real orders remain disabled.',
          ),
        ] else ...[
          _KisSchedulerDryRunSummaryPanel(result: result),
          const SizedBox(height: 12),
          _KisSchedulerDryRunChildren(children: result.childRuns),
          const SizedBox(height: 12),
          _KisSchedulerDryRunSafety(result: result),
          const SizedBox(height: 4),
          ExpansionTile(
            tilePadding: EdgeInsets.zero,
            childrenPadding: EdgeInsets.zero,
            title: const Text('Developer Raw Payload'),
            children: [
              _StateLine(text: _prettyJson(result.rawPayload)),
            ],
          ),
        ],
      ]),
    );
  }
}

class _KisSchedulerDryRunSummaryPanel extends StatelessWidget {
  const _KisSchedulerDryRunSummaryPanel({required this.result});

  final KisSchedulerDryRunOrchestration result;

  @override
  Widget build(BuildContext context) {
    final summary = result.summary;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Dry-run Summary',
          style: TextStyle(fontWeight: FontWeight.w700)),
      const SizedBox(height: 8),
      Wrap(spacing: 14, runSpacing: 8, children: [
        _ResultPair(label: 'result', value: result.result),
        _ResultPair(label: 'slot label', value: result.slotLabel),
        _ResultPair(
          label: 'modules completed',
          value: _joinList(summary.modulesCompleted),
        ),
        _ResultPair(
          label: 'sell candidates reviewed',
          value: summary.sellCandidatesReviewed.toString(),
        ),
        _ResultPair(
          label: 'buy candidates reviewed',
          value: summary.buyCandidatesReviewed.toString(),
        ),
        _ResultPair(
          label: 'sell ready count',
          value: summary.sellReadyCount.toString(),
        ),
        _ResultPair(
          label: 'buy ready count',
          value: summary.buyReadyCount.toString(),
        ),
        _ResultPair(
          label: 'submitted order count',
          value: summary.submittedOrderCount.toString(),
        ),
        _ResultPair(
          label: 'broker submit count',
          value: summary.brokerSubmitCount.toString(),
        ),
        _ResultPair(
          label: 'manual submit count',
          value: summary.manualSubmitCount.toString(),
        ),
        _ResultPair(
          label: 'primary block reason',
          value: summary.primaryBlockReason ?? 'n/a',
        ),
        _ResultPair(
          label: 'next recommended operator action',
          value: summary.nextRecommendedOperatorAction ?? 'n/a',
        ),
      ]),
      if (summary.topBlockReasons.isNotEmpty) ...[
        const SizedBox(height: 8),
        _StateLine(
          text: 'top block reasons: ${_joinList(summary.topBlockReasons)}',
        ),
      ],
    ]);
  }
}

class _KisSchedulerDryRunChildren extends StatelessWidget {
  const _KisSchedulerDryRunChildren({required this.children});

  final List<KisSchedulerDryRunChild> children;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Child Modules',
          style: TextStyle(fontWeight: FontWeight.w700)),
      const SizedBox(height: 8),
      if (children.isEmpty)
        const _StateLine(text: 'No child module results returned.')
      else
        for (final child in children)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: _panelDecoration(),
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      child.module,
                      style: const TextStyle(fontWeight: FontWeight.w800),
                    ),
                    const SizedBox(height: 8),
                    Wrap(spacing: 14, runSpacing: 8, children: [
                      _ResultPair(label: 'result', value: child.result),
                      _ResultPair(label: 'action', value: child.action),
                      _ResultPair(label: 'status', value: child.status),
                      _ResultPair(
                        label: 'symbol',
                        value: child.symbol ?? 'n/a',
                      ),
                      _ResultPair(
                        label: 'primary block reason',
                        value: child.primaryBlockReason ?? 'n/a',
                      ),
                      _ResultPair(
                        label: 'broker submit',
                        value: _yesNo(child.brokerSubmitCalled),
                      ),
                      _ResultPair(
                        label: 'real order submitted',
                        value: _yesNo(child.realOrderSubmitted),
                      ),
                      _ResultPair(
                        label: 'manual submit',
                        value: _yesNo(child.manualSubmitCalled),
                      ),
                    ]),
                    const SizedBox(height: 8),
                    Wrap(spacing: 8, runSpacing: 8, children: [
                      _SoftBadge(
                        text:
                            'Broker submit: ${_yesNo(child.brokerSubmitCalled)}',
                        color: Colors.lightBlueAccent,
                      ),
                      _SoftBadge(
                        text:
                            'Real order submitted: ${_yesNo(child.realOrderSubmitted)}',
                        color: Colors.lightBlueAccent,
                      ),
                      _SoftBadge(
                        text:
                            'Manual submit: ${_yesNo(child.manualSubmitCalled)}',
                        color: Colors.lightBlueAccent,
                      ),
                    ]),
                    if (child.blockReasons.isNotEmpty) ...[
                      const SizedBox(height: 8),
                      _StateLine(
                        text: 'block reasons: ${_joinList(child.blockReasons)}',
                      ),
                    ],
                  ]),
            ),
          ),
    ]);
  }
}

class _KisSchedulerDryRunSafety extends StatelessWidget {
  const _KisSchedulerDryRunSafety({required this.result});

  final KisSchedulerDryRunOrchestration result;

  @override
  Widget build(BuildContext context) {
    final safety = result.safety;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Safety', style: TextStyle(fontWeight: FontWeight.w700)),
      const SizedBox(height: 8),
      Wrap(spacing: 14, runSpacing: 8, children: [
        _ResultPair(
          label: 'scheduler real orders disabled',
          value: _yesNo(!result.schedulerRealOrdersEnabled),
        ),
        _ResultPair(
          label: 'dry-run orchestration',
          value: _yesNo(_mapBool(safety, 'scheduler_dry_run_orchestration')),
        ),
        _ResultPair(
          label: 'no broker submit',
          value: _yesNo(_mapBool(safety, 'no_broker_submit')),
        ),
        _ResultPair(
          label: 'no OrderLog creation',
          value: _yesNo(_mapBool(safety, 'no_order_log_created')),
        ),
        _ResultPair(
          label: 'buy called in dry-run mode',
          value: _yesNo(_mapBool(safety, 'limited_buy_called_in_dry_run_mode')),
        ),
        _ResultPair(
          label: 'sell called in dry-run mode',
          value:
              _yesNo(_mapBool(safety, 'limited_sell_called_in_dry_run_mode')),
        ),
      ]),
    ]);
  }
}

class _KisSchedulerDryRunReviewCard extends StatelessWidget {
  const _KisSchedulerDryRunReviewCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final result = controller.latestKisSchedulerDryRunReview;
    return Container(
      key: const Key('kis_scheduler_dry_run_review_card'),
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: _panelDecoration(),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.manage_history_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text('KIS Scheduler Dry-run Review / Operator Audit',
                style: Theme.of(context).textTheme.titleSmall),
          ),
        ]),
        const SizedBox(height: 8),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(
              text: 'SCHEDULER DRY-RUN REVIEW', color: Colors.lightBlueAccent),
          _SoftBadge(text: 'OPERATOR AUDIT', color: Colors.lightBlueAccent),
          _SoftBadge(text: 'REVIEW ONLY', color: Colors.greenAccent),
          _SoftBadge(text: 'NO BROKER SUBMIT', color: Colors.orangeAccent),
          _SoftBadge(text: 'REAL ORDERS DISABLED', color: Colors.redAccent),
          _SoftBadge(text: 'SAFETY INVARIANTS', color: Colors.white70),
          _SoftBadge(text: 'SELL BEFORE BUY', color: Colors.amberAccent),
        ]),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          onPressed: controller.kisSchedulerDryRunReviewLoading
              ? null
              : () async {
                  final actionResult =
                      await controller.refreshKisSchedulerDryRunReview();
                  if (!context.mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(actionResult.message),
                    backgroundColor:
                        actionResult.success ? Colors.green : Colors.redAccent,
                  ));
                },
          icon: controller.kisSchedulerDryRunReviewLoading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.refresh, size: 18),
          label: Text(controller.kisSchedulerDryRunReviewLoading
              ? 'Refreshing dry-run review...'
              : 'Refresh Dry-run Review'),
        ),
        if (controller.kisSchedulerDryRunReviewError != null) ...[
          const SizedBox(height: 10),
          _StateLine(
            text: _primaryLine(controller.kisSchedulerDryRunReviewError!),
            color: Colors.redAccent,
          ),
        ],
        const SizedBox(height: 12),
        if (result == null) ...[
          const _StateLine(
            text:
                'No scheduler dry-run review data yet. Safety review remains read-only.',
          ),
        ] else ...[
          _KisSchedulerDryRunReviewSummaryPanel(result: result),
          const SizedBox(height: 12),
          _KisSchedulerDryRunReviewTopReasons(
            reasons: result.topBlockReasons,
          ),
          const SizedBox(height: 12),
          _KisSchedulerDryRunReviewSafetyViolations(
            violations: result.safetyViolations,
          ),
          const SizedBox(height: 12),
          _KisSchedulerDryRunReviewRecentRuns(runs: result.recentRuns),
          const SizedBox(height: 12),
          _KisSchedulerDryRunReviewSafety(result: result),
          const SizedBox(height: 4),
          ExpansionTile(
            tilePadding: EdgeInsets.zero,
            childrenPadding: EdgeInsets.zero,
            title: const Text('Developer Raw Payload'),
            children: [
              _StateLine(text: _prettyJson(result.rawPayload)),
            ],
          ),
        ],
      ]),
    );
  }
}

class _KisSchedulerDryRunReviewSummaryPanel extends StatelessWidget {
  const _KisSchedulerDryRunReviewSummaryPanel({required this.result});

  final KisSchedulerDryRunReview result;

  @override
  Widget build(BuildContext context) {
    final summary = result.summary;
    final sell = result.module('limited_auto_sell');
    final buy = result.module('limited_auto_buy');
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Dry-run Review Summary',
          style: TextStyle(fontWeight: FontWeight.w700)),
      const SizedBox(height: 8),
      Wrap(spacing: 14, runSpacing: 8, children: [
        _ResultPair(label: 'total runs', value: summary.totalRuns.toString()),
        _ResultPair(
          label: 'completed / blocked / partial',
          value:
              '${summary.completedCount} / ${summary.blockedCount} / ${summary.partialCount}',
        ),
        _ResultPair(
          label: 'sell ready count',
          value: summary.sellReadyCount.toString(),
        ),
        _ResultPair(
          label: 'buy ready count',
          value: summary.buyReadyCount.toString(),
        ),
        _ResultPair(
          label: 'buy skipped after sell review count',
          value: summary.buySkippedAfterSellReviewCount.toString(),
        ),
        _ResultPair(
          label: 'submitted order count',
          value: summary.submittedOrderCount.toString(),
        ),
        _ResultPair(
          label: 'broker submit count',
          value: summary.brokerSubmitCount.toString(),
        ),
        _ResultPair(
          label: 'manual submit count',
          value: summary.manualSubmitCount.toString(),
        ),
        _ResultPair(
          label: 'no-submit invariant',
          value: _yesNo(summary.noSubmitInvariantOk),
        ),
        _ResultPair(
          label: 'sell-before-buy ordering',
          value: _yesNo(summary.sellBeforeBuyOrderingOk),
        ),
        _ResultPair(
          label: 'latest run time',
          value: formatTimestampWithKst(summary.latestRunAt, fallback: 'n/a'),
        ),
        _ResultPair(
          label: 'latest recommended operator action',
          value: result.latestRecommendedOperatorAction,
        ),
      ]),
      const SizedBox(height: 8),
      Wrap(spacing: 14, runSpacing: 8, children: [
        _ResultPair(
          label: 'sell module runs',
          value:
              '${sell.runCount}, ready ${sell.sellReadyCount}, blocked ${sell.blockedCount}',
        ),
        _ResultPair(
          label: 'buy module runs',
          value:
              '${buy.runCount}, ready ${buy.buyReadyCount}, skipped ${buy.skippedAfterSellReviewCount}',
        ),
      ]),
    ]);
  }
}

class _KisSchedulerDryRunReviewTopReasons extends StatelessWidget {
  const _KisSchedulerDryRunReviewTopReasons({required this.reasons});

  final List<KisSchedulerDryRunBlockReason> reasons;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Top Block Reasons',
          style: TextStyle(fontWeight: FontWeight.w700)),
      const SizedBox(height: 8),
      if (reasons.isEmpty)
        const _StateLine(text: 'No scheduler dry-run block reasons recorded.')
      else
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final reason in reasons)
              _SoftBadge(
                text: '${reason.label}: ${reason.count}',
                color: Colors.amberAccent,
              ),
          ],
        ),
    ]);
  }
}

class _KisSchedulerDryRunReviewSafetyViolations extends StatelessWidget {
  const _KisSchedulerDryRunReviewSafetyViolations({
    required this.violations,
  });

  final List<KisSchedulerDryRunSafetyViolation> violations;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Safety Violations',
          style: TextStyle(fontWeight: FontWeight.w700)),
      const SizedBox(height: 8),
      if (violations.isEmpty)
        const _StateLine(
          text: 'No scheduler dry-run safety violations detected',
        )
      else
        for (final violation in violations)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.redAccent.withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(
                  color: Colors.redAccent.withValues(alpha: 0.30),
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(children: [
                    const Icon(Icons.warning_amber_outlined,
                        size: 18, color: Colors.redAccent),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        violation.label,
                        style: const TextStyle(fontWeight: FontWeight.w800),
                      ),
                    ),
                    const _SoftBadge(
                      text: 'SAFETY VIOLATION',
                      color: Colors.redAccent,
                    ),
                  ]),
                  const SizedBox(height: 8),
                  Wrap(spacing: 14, runSpacing: 8, children: [
                    _ResultPair(label: 'reason', value: violation.reason),
                    _ResultPair(label: 'run', value: violation.runId ?? 'n/a'),
                    _ResultPair(
                        label: 'module', value: violation.module ?? 'n/a'),
                    _ResultPair(
                      label: 'count',
                      value: violation.count?.toString() ?? 'n/a',
                    ),
                  ]),
                ],
              ),
            ),
          ),
    ]);
  }
}

class _KisSchedulerDryRunReviewRecentRuns extends StatelessWidget {
  const _KisSchedulerDryRunReviewRecentRuns({required this.runs});

  final List<KisSchedulerDryRunReviewRun> runs;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Recent Scheduler Dry-run Runs',
          style: TextStyle(fontWeight: FontWeight.w700)),
      const SizedBox(height: 8),
      if (runs.isEmpty)
        const _StateLine(text: 'No scheduler dry-run runs returned.')
      else
        for (final run in runs.take(5))
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: _panelDecoration(),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${run.slotLabel} / ${formatTimestampWithKst(run.createdAt, fallback: 'n/a')}',
                    style: const TextStyle(fontWeight: FontWeight.w800),
                  ),
                  const SizedBox(height: 8),
                  Wrap(spacing: 14, runSpacing: 8, children: [
                    _ResultPair(label: 'result', value: run.result),
                    _ResultPair(
                      label: 'primary block reason',
                      value: run.primaryBlockReason ?? 'n/a',
                    ),
                    _ResultPair(
                      label: 'sell candidates reviewed',
                      value: run.sellCandidatesReviewed.toString(),
                    ),
                    _ResultPair(
                      label: 'buy candidates reviewed',
                      value: run.buyCandidatesReviewed.toString(),
                    ),
                    _ResultPair(
                      label: 'sell ready / buy ready',
                      value: '${run.sellReadyCount} / ${run.buyReadyCount}',
                    ),
                    _ResultPair(
                      label: 'broker submit',
                      value: _yesNo(run.brokerSubmitCalled),
                    ),
                    _ResultPair(
                      label: 'manual submit',
                      value: _yesNo(run.manualSubmitCalled),
                    ),
                    _ResultPair(
                      label: 'real order submitted',
                      value: _yesNo(run.realOrderSubmitted),
                    ),
                  ]),
                  const SizedBox(height: 8),
                  Wrap(spacing: 8, runSpacing: 8, children: [
                    _SoftBadge(
                      text: 'Broker submit: ${_yesNo(run.brokerSubmitCalled)}',
                      color: Colors.lightBlueAccent,
                    ),
                    _SoftBadge(
                      text: 'Manual submit: ${_yesNo(run.manualSubmitCalled)}',
                      color: Colors.lightBlueAccent,
                    ),
                    _SoftBadge(
                      text:
                          'Real order submitted: ${_yesNo(run.realOrderSubmitted)}',
                      color: Colors.lightBlueAccent,
                    ),
                  ]),
                  if (run.blockReasons.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    _StateLine(
                      text: 'block reasons: ${_joinList(run.blockReasons)}',
                    ),
                  ],
                  const SizedBox(height: 10),
                  _KisSchedulerDryRunReviewChildModules(
                    children: run.childRuns,
                  ),
                ],
              ),
            ),
          ),
    ]);
  }
}

class _KisSchedulerDryRunReviewChildModules extends StatelessWidget {
  const _KisSchedulerDryRunReviewChildModules({required this.children});

  final List<KisSchedulerDryRunReviewChild> children;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Child Modules',
          style: TextStyle(fontWeight: FontWeight.w700)),
      const SizedBox(height: 8),
      if (children.isEmpty)
        const _StateLine(text: 'No scheduler dry-run child module rows.')
      else
        for (final child in children)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: _panelDecoration(),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    child.module,
                    style: const TextStyle(fontWeight: FontWeight.w800),
                  ),
                  const SizedBox(height: 8),
                  Wrap(spacing: 14, runSpacing: 8, children: [
                    _ResultPair(label: 'result', value: child.result),
                    _ResultPair(label: 'action', value: child.action),
                    _ResultPair(label: 'status', value: child.status),
                    _ResultPair(label: 'symbol', value: child.symbol ?? 'n/a'),
                    _ResultPair(
                      label: 'primary block reason',
                      value: child.primaryBlockReason ?? 'n/a',
                    ),
                    _ResultPair(
                      label: 'broker submit',
                      value: _yesNo(child.brokerSubmitCalled),
                    ),
                    _ResultPair(
                      label: 'real order submitted',
                      value: _yesNo(child.realOrderSubmitted),
                    ),
                    _ResultPair(
                      label: 'manual submit',
                      value: _yesNo(child.manualSubmitCalled),
                    ),
                  ]),
                  const SizedBox(height: 8),
                  Wrap(spacing: 8, runSpacing: 8, children: [
                    _SoftBadge(
                      text:
                          'Broker submit: ${_yesNo(child.brokerSubmitCalled)}',
                      color: Colors.lightBlueAccent,
                    ),
                    _SoftBadge(
                      text:
                          'Real order submitted: ${_yesNo(child.realOrderSubmitted)}',
                      color: Colors.lightBlueAccent,
                    ),
                    _SoftBadge(
                      text:
                          'Manual submit: ${_yesNo(child.manualSubmitCalled)}',
                      color: Colors.lightBlueAccent,
                    ),
                  ]),
                ],
              ),
            ),
          ),
    ]);
  }
}

class _KisSchedulerDryRunReviewSafety extends StatelessWidget {
  const _KisSchedulerDryRunReviewSafety({required this.result});

  final KisSchedulerDryRunReview result;

  @override
  Widget build(BuildContext context) {
    final safety = result.safety;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Safety Invariants',
          style: TextStyle(fontWeight: FontWeight.w700)),
      const SizedBox(height: 8),
      Wrap(spacing: 14, runSpacing: 8, children: [
        _ResultPair(
          label: 'review only',
          value: _yesNo(result.reviewOnly),
        ),
        _ResultPair(
          label: 'scheduler real orders disabled',
          value: _yesNo(!_mapBool(safety, 'scheduler_real_orders_enabled')),
        ),
        _ResultPair(
          label: 'no broker submit',
          value: _yesNo(_mapBool(safety, 'no_broker_submit_from_review')),
        ),
        _ResultPair(
          label: 'no-submit invariant',
          value: _yesNo(result.summary.noSubmitInvariantOk),
        ),
        _ResultPair(
          label: 'sell-before-buy ordering',
          value: _yesNo(result.summary.sellBeforeBuyOrderingOk),
        ),
        _ResultPair(
          label: 'order log created count',
          value: result.summary.orderLogCreatedCount.toString(),
        ),
      ]),
    ]);
  }
}

bool _mapBool(Map<String, dynamic> map, String key) {
  final value = map[key];
  if (value is bool) return value;
  if (value is num) return value != 0;
  final text = value?.toString().trim().toLowerCase();
  return text == 'true' || text == '1' || text == 'yes';
}

bool? _mapNullableBool(Map<String, dynamic> map, String key) {
  final value = map[key];
  if (value == null) return null;
  if (value is bool) return value;
  if (value is num) return value != 0;
  final text = value.toString().trim().toLowerCase();
  if (text == 'true' || text == '1' || text == 'yes') return true;
  if (text == 'false' || text == '0' || text == 'no') return false;
  return null;
}

String _schedulerSlotLabel(KisSchedulerScheduleItem? slot) {
  if (slot == null) return 'n/a';
  return '${slot.displayLabel} ${slot.scheduledTime} ${slot.timezone}';
}

class _KisSchedulerGuardedSellCard extends StatelessWidget {
  const _KisSchedulerGuardedSellCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final settings = controller.settings;
    final result = controller.latestKisSchedulerGuardedSellResult;
    final brokerBadge = result?.brokerSubmitCalled == true
        ? 'BROKER SUBMIT: YES'
        : 'NO BROKER SUBMIT';
    return Container(
      key: const Key('kis_scheduler_guarded_sell_card'),
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: _panelDecoration(),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.output_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text('KIS Scheduler Guarded Sell',
                style: Theme.of(context).textTheme.titleSmall),
          ),
        ]),
        const SizedBox(height: 8),
        Wrap(spacing: 8, runSpacing: 8, children: [
          const _SoftBadge(
              text: 'SCHEDULER GUARDED SELL', color: Colors.lightBlueAccent),
          const _SoftBadge(text: 'SELL ONLY', color: Colors.greenAccent),
          const _SoftBadge(text: 'DEFAULT OFF', color: Colors.amberAccent),
          const _SoftBadge(text: 'BUY DISABLED', color: Colors.orangeAccent),
          const _SoftBadge(
              text: 'REAL ORDERS REQUIRE EXPLICIT SETTINGS',
              color: Colors.redAccent),
          _SoftBadge(
            text: brokerBadge,
            color: result?.brokerSubmitCalled == true
                ? Colors.redAccent
                : Colors.orangeAccent,
          ),
          const _SoftBadge(
              text: 'USES LIMITED AUTO SELL GATES',
              color: Colors.lightGreenAccent),
        ]),
        const SizedBox(height: 12),
        _KisSchedulerGuardedSellStatusGrid(
          result: result,
          settings: settings,
        ),
        const SizedBox(height: 10),
        const _StateLine(text: 'BUY DISABLED FOR SCHEDULER SELL-ONLY'),
        const SizedBox(height: 12),
        Wrap(spacing: 8, runSpacing: 8, children: [
          OutlinedButton.icon(
            onPressed: controller.kisSchedulerGuardedSellLoading
                ? null
                : () async {
                    final actionResult =
                        await controller.refreshKisSchedulerGuardedSellStatus();
                    if (!context.mounted) return;
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                      content: Text(actionResult.message),
                      backgroundColor: actionResult.success
                          ? Colors.green
                          : Colors.redAccent,
                    ));
                  },
            icon: controller.kisSchedulerGuardedSellLoading
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.refresh, size: 18),
            label: Text(controller.kisSchedulerGuardedSellLoading
                ? 'Refreshing scheduler sell status...'
                : 'Refresh Scheduler Sell Status'),
          ),
          FilledButton.icon(
            onPressed: controller.kisSchedulerGuardedSellLoading
                ? null
                : () async {
                    final actionResult =
                        await controller.runKisSchedulerGuardedSellOnce();
                    if (!context.mounted) return;
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                      content: Text(actionResult.message),
                      backgroundColor: actionResult.success
                          ? Colors.green
                          : Colors.redAccent,
                    ));
                  },
            icon: controller.kisSchedulerGuardedSellLoading
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.play_arrow, size: 18),
            label: Text(controller.kisSchedulerGuardedSellLoading
                ? 'Running scheduler guarded sell...'
                : 'Run Scheduler Guarded Sell Once'),
          ),
        ]),
        if (controller.kisSchedulerGuardedSellError != null) ...[
          const SizedBox(height: 10),
          _StateLine(
            text: _primaryLine(controller.kisSchedulerGuardedSellError!),
            color: Colors.redAccent,
          ),
        ],
        if (result == null) ...[
          const SizedBox(height: 10),
          const _StateLine(
            text:
                'No scheduler guarded sell run yet. Default backend state blocks real orders.',
          ),
        ] else ...[
          const SizedBox(height: 10),
          _KisSchedulerGuardedSellResultPanel(result: result),
        ],
      ]),
    );
  }
}

class _KisSchedulerGuardedSellStatusGrid extends StatelessWidget {
  const _KisSchedulerGuardedSellStatusGrid({
    required this.result,
    required this.settings,
  });

  final KisSchedulerGuardedSellResult? result;
  final OpsSettings settings;

  @override
  Widget build(BuildContext context) {
    final checks = result?.checks ?? const <String, dynamic>{};
    final safety = result?.safety ?? const <String, dynamic>{};
    final dailyLimit = result?.dailyLimit ?? const <String, dynamic>{};
    final duplicate = result?.duplicateOrderCheck ?? const <String, dynamic>{};
    final market = result?.marketSessionCheck ?? const <String, dynamic>{};
    return Wrap(spacing: 14, runSpacing: 8, children: [
      _ResultPair(
        label: 'scheduler real orders enabled',
        value: _boolText(result?.schedulerRealOrdersEnabled ??
            settings.kisSchedulerAllowRealOrders),
      ),
      _ResultPair(
        label: 'scheduler sell enabled',
        value: _boolText(
            _mapNullableBool(safety, 'kis_scheduler_sell_enabled') ??
                _mapNullableBool(checks, 'kis_scheduler_sell_enabled') ??
                settings.kisSchedulerSellEnabled),
      ),
      const _ResultPair(label: 'buy execution allowed', value: 'No'),
      _ResultPair(
        label: 'dry_run',
        value:
            _boolText(_mapNullableBool(safety, 'dry_run') ?? settings.dryRun),
      ),
      _ResultPair(
        label: 'kill_switch',
        value: _boolText(
            _mapNullableBool(safety, 'kill_switch') ?? settings.killSwitch),
      ),
      _ResultPair(
        label: 'kis_real_order_enabled',
        value: _nullableBoolText(
          _mapNullableBool(safety, 'kis_real_order_enabled') ??
              _mapNullableBool(checks, 'kis_real_order_enabled'),
        ),
      ),
      _ResultPair(
        label: 'kis_live_auto_sell_enabled',
        value: _boolText(
          _mapNullableBool(safety, 'kis_live_auto_sell_enabled') ??
              _mapNullableBool(checks, 'kis_live_auto_sell_enabled') ??
              settings.kisLiveAutoSellEnabled,
        ),
      ),
      _ResultPair(
        label: 'stop-loss enabled',
        value: _boolText(
          _mapNullableBool(checks, 'kis_limited_auto_stop_loss_enabled') ??
              settings.kisLimitedAutoSellStopLossEnabled,
        ),
      ),
      _ResultPair(
        label: 'take-profit enabled',
        value: _boolText(
          _mapNullableBool(checks, 'kis_limited_auto_take_profit_enabled') ??
              settings.kisLimitedAutoSellTakeProfitEnabled,
        ),
      ),
      _ResultPair(
        label: 'market sell session',
        value: _nullableYesNo(
          _mapNullableBool(market, 'sell_session_allowed') ??
              _mapNullableBool(checks, 'sell_session_allowed'),
        ),
      ),
      _ResultPair(
        label: 'daily sell limit',
        value: _schedulerGuardedSellDailyLimitLabel(dailyLimit),
      ),
      _ResultPair(
        label: 'duplicate order status',
        value: _schedulerGuardedSellDuplicateLabel(duplicate),
      ),
      _ResultPair(
        label: 'primary block reason',
        value: result?.primaryBlockReason ?? 'not_loaded',
      ),
    ]);
  }
}

class _KisSchedulerGuardedSellResultPanel extends StatelessWidget {
  const _KisSchedulerGuardedSellResultPanel({required this.result});

  final KisSchedulerGuardedSellResult result;

  @override
  Widget build(BuildContext context) {
    final submitted = result.submitted;
    final primaryBlockReason = result.primaryBlockReason ??
        (result.blockReasons.isEmpty ? 'n/a' : result.blockReasons.first);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      _StateLine(
        text: submitted
            ? 'SUBMITTED SELL: ${result.symbol ?? 'n/a'} qty ${result.quantity?.toString() ?? 'n/a'}'
            : 'BLOCKED: $primaryBlockReason',
        color: submitted ? Colors.redAccent : Colors.amberAccent,
      ),
      const SizedBox(height: 10),
      Wrap(spacing: 8, runSpacing: 8, children: [
        _SoftBadge(
          text: 'Broker submit: ${_yesNo(result.brokerSubmitCalled)}',
          color: result.brokerSubmitCalled
              ? Colors.redAccent
              : Colors.lightBlueAccent,
        ),
        _SoftBadge(
          text: 'Manual submit: ${_yesNo(result.manualSubmitCalled)}',
          color: result.manualSubmitCalled
              ? Colors.redAccent
              : Colors.lightBlueAccent,
        ),
        _SoftBadge(
          text: 'Real order submitted: ${_yesNo(result.realOrderSubmitted)}',
          color: result.realOrderSubmitted
              ? Colors.redAccent
              : Colors.lightBlueAccent,
        ),
      ]),
      const SizedBox(height: 10),
      Wrap(spacing: 14, runSpacing: 8, children: [
        _ResultPair(label: 'result', value: result.result),
        _ResultPair(label: 'action', value: result.action),
        _ResultPair(label: 'reason', value: result.reason),
        _ResultPair(label: 'primary block reason', value: primaryBlockReason),
        _ResultPair(label: 'symbol', value: result.symbol ?? 'n/a'),
        _ResultPair(label: 'company', value: result.companyName ?? 'n/a'),
        _ResultPair(
            label: 'quantity', value: result.quantity?.toString() ?? 'n/a'),
        _ResultPair(label: 'trigger', value: result.trigger ?? 'n/a'),
        _ResultPair(
            label: 'order id', value: result.orderId?.toString() ?? 'none'),
        _ResultPair(label: 'KIS ODNO', value: result.kisOdno ?? 'none'),
        _ResultPair(
          label: 'broker order id',
          value: result.brokerOrderId ?? 'none',
        ),
      ]),
      const SizedBox(height: 10),
      _StateLine(
        text:
            'buy_result: ${result.buyResult['result'] ?? 'skipped'} / ${result.buyResult['reason'] ?? 'buy_scheduler_execution_disabled'}',
      ),
      if (result.sellResult.isNotEmpty) ...[
        const SizedBox(height: 8),
        _StateLine(
          text:
              'sell_result: ${result.sellResult['result'] ?? 'n/a'} / ${result.sellResult['reason'] ?? 'n/a'}',
        ),
      ],
      if (result.blockReasons.isNotEmpty) ...[
        const SizedBox(height: 8),
        _StateLine(text: 'block reasons: ${_joinList(result.blockReasons)}'),
      ],
      const SizedBox(height: 4),
      ExpansionTile(
        tilePadding: EdgeInsets.zero,
        childrenPadding: EdgeInsets.zero,
        title: const Text('Developer Raw Payload'),
        children: [
          _StateLine(text: _prettyJson(result.rawPayload)),
        ],
      ),
    ]);
  }
}

String _schedulerGuardedSellDailyLimitLabel(Map<String, dynamic> value) {
  if (value.isEmpty) return 'n/a';
  final remaining = value['daily_limit_remaining']?.toString();
  final maxOrders = value['max_orders_per_day']?.toString();
  final submitted = value['submitted_count_today']?.toString();
  final base =
      '${remaining == null || remaining == 'null' ? 'n/a' : remaining} remaining / ${maxOrders == null || maxOrders == 'null' ? 'n/a' : maxOrders} max';
  if (submitted == null || submitted == 'null') return base;
  return '$base, $submitted used';
}

String _schedulerGuardedSellDuplicateLabel(Map<String, dynamic> value) {
  if (value.isEmpty) return 'n/a';
  final duplicate =
      _mapNullableBool(value, 'duplicate_open_sell_order') ?? false;
  if (duplicate) return 'blocked: duplicate open sell';
  final checked = _mapNullableBool(value, 'checked');
  if (checked == false) return 'not checked';
  return 'clear';
}

class _KisSchedulerGuardedBuyCard extends StatelessWidget {
  const _KisSchedulerGuardedBuyCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final settings = controller.settings;
    final result = controller.latestKisSchedulerGuardedBuyResult;
    final brokerBadge = result?.brokerSubmitCalled == true
        ? 'BROKER SUBMIT: YES'
        : 'NO BROKER SUBMIT';
    return Container(
      key: const Key('kis_scheduler_guarded_buy_card'),
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: _panelDecoration(),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.add_shopping_cart_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text('KIS Scheduler Guarded Buy',
                style: Theme.of(context).textTheme.titleSmall),
          ),
        ]),
        const SizedBox(height: 8),
        Wrap(spacing: 8, runSpacing: 8, children: [
          const _SoftBadge(
              text: 'SCHEDULER GUARDED BUY', color: Colors.lightBlueAccent),
          const _SoftBadge(text: 'BUY ONLY', color: Colors.greenAccent),
          const _SoftBadge(text: 'DEFAULT OFF', color: Colors.amberAccent),
          const _SoftBadge(
              text: 'SELL REVIEW FIRST', color: Colors.orangeAccent),
          const _SoftBadge(
              text: 'SELL READY BLOCKS BUY', color: Colors.orangeAccent),
          const _SoftBadge(
              text: 'REAL ORDERS REQUIRE EXPLICIT SETTINGS',
              color: Colors.redAccent),
          _SoftBadge(
            text: brokerBadge,
            color: result?.brokerSubmitCalled == true
                ? Colors.redAccent
                : Colors.orangeAccent,
          ),
          const _SoftBadge(
              text: 'USES LIMITED AUTO BUY GATES',
              color: Colors.lightGreenAccent),
        ]),
        const SizedBox(height: 12),
        _KisSchedulerGuardedBuyStatusGrid(
          result: result,
          settings: settings,
        ),
        const SizedBox(height: 12),
        Wrap(spacing: 8, runSpacing: 8, children: [
          OutlinedButton.icon(
            onPressed: controller.kisSchedulerGuardedBuyLoading
                ? null
                : () async {
                    final actionResult =
                        await controller.refreshKisSchedulerGuardedBuyStatus();
                    if (!context.mounted) return;
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                      content: Text(actionResult.message),
                      backgroundColor: actionResult.success
                          ? Colors.green
                          : Colors.redAccent,
                    ));
                  },
            icon: controller.kisSchedulerGuardedBuyLoading
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.refresh, size: 18),
            label: Text(controller.kisSchedulerGuardedBuyLoading
                ? 'Refreshing scheduler buy status...'
                : 'Refresh Scheduler Buy Status'),
          ),
          FilledButton.icon(
            onPressed: controller.kisSchedulerGuardedBuyLoading
                ? null
                : () async {
                    final actionResult =
                        await controller.runKisSchedulerGuardedBuyOnce();
                    if (!context.mounted) return;
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                      content: Text(actionResult.message),
                      backgroundColor: actionResult.success
                          ? Colors.green
                          : Colors.redAccent,
                    ));
                  },
            icon: controller.kisSchedulerGuardedBuyLoading
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.play_arrow, size: 18),
            label: Text(controller.kisSchedulerGuardedBuyLoading
                ? 'Running scheduler guarded buy...'
                : 'Run Scheduler Guarded Buy Once'),
          ),
        ]),
        if (controller.kisSchedulerGuardedBuyError != null) ...[
          const SizedBox(height: 10),
          _StateLine(
            text: _primaryLine(controller.kisSchedulerGuardedBuyError!),
            color: Colors.redAccent,
          ),
        ],
        if (result == null) ...[
          const SizedBox(height: 10),
          const _StateLine(
            text:
                'No scheduler guarded buy run yet. Default backend state blocks real orders.',
          ),
        ] else ...[
          const SizedBox(height: 10),
          _KisSchedulerGuardedBuyResultPanel(result: result),
        ],
      ]),
    );
  }
}

class _KisSchedulerGuardedBuyStatusGrid extends StatelessWidget {
  const _KisSchedulerGuardedBuyStatusGrid({
    required this.result,
    required this.settings,
  });

  final KisSchedulerGuardedBuyResult? result;
  final OpsSettings settings;

  @override
  Widget build(BuildContext context) {
    final checks = result?.checks ?? const <String, dynamic>{};
    final safety = result?.safety ?? const <String, dynamic>{};
    final dailyLimit = result?.dailyLimit ?? const <String, dynamic>{};
    final duplicate = result?.duplicateOrderCheck ?? const <String, dynamic>{};
    final market = result?.marketSessionCheck ?? const <String, dynamic>{};
    return Wrap(spacing: 14, runSpacing: 8, children: [
      _ResultPair(
        label: 'scheduler real orders enabled',
        value: _boolText(result?.schedulerRealOrdersEnabled ??
            settings.kisSchedulerAllowRealOrders),
      ),
      _ResultPair(
        label: 'scheduler buy enabled',
        value: _boolText(
            result?.schedulerBuyEnabled ?? settings.kisSchedulerBuyEnabled),
      ),
      _ResultPair(
        label: 'sell priority checked',
        value: _boolText(result?.sellPriorityChecked ?? false),
      ),
      _ResultPair(
        label: 'sell ready blocks buy',
        value: _boolText(result?.sellReadyBlocksBuy ?? true),
      ),
      _ResultPair(
        label: 'dry_run',
        value:
            _boolText(_mapNullableBool(safety, 'dry_run') ?? settings.dryRun),
      ),
      _ResultPair(
        label: 'kill_switch',
        value: _boolText(
            _mapNullableBool(safety, 'kill_switch') ?? settings.killSwitch),
      ),
      _ResultPair(
        label: 'kis_real_order_enabled',
        value: _nullableBoolText(
          _mapNullableBool(safety, 'kis_real_order_enabled') ??
              _mapNullableBool(checks, 'kis_real_order_enabled'),
        ),
      ),
      _ResultPair(
        label: 'kis_live_auto_buy_enabled',
        value: _boolText(
          _mapNullableBool(safety, 'kis_live_auto_buy_enabled') ??
              _mapNullableBool(checks, 'kis_live_auto_buy_enabled') ??
              settings.kisLiveAutoBuyEnabled,
        ),
      ),
      _ResultPair(
        label: 'kis_limited_auto_buy_enabled',
        value: _boolText(
          _mapNullableBool(safety, 'kis_limited_auto_buy_enabled') ??
              _mapNullableBool(checks, 'kis_limited_auto_buy_enabled') ??
              settings.kisLimitedAutoBuyEnabled,
        ),
      ),
      _ResultPair(
        label: 'market entry session',
        value: _nullableYesNo(
          _mapNullableBool(market, 'entry_allowed_now') ??
              _mapNullableBool(checks, 'entry_allowed_now'),
        ),
      ),
      _ResultPair(
        label: 'no_new_entry_after',
        value: (market['no_new_entry_after'] ??
                checks['no_new_entry_after'] ??
                settings.kisLimitedAutoBuyNoNewEntryAfter)
            .toString(),
      ),
      _ResultPair(
        label: 'cash/notional cap',
        value:
            '${_formatPercentValue(settings.kisLimitedAutoBuyMaxNotionalPct * 100)} cap / ${_formatKrwOrDash(settings.kisLimitedAutoBuyMinCashBufferKrw)} buffer',
      ),
      _ResultPair(
        label: 'daily buy limit',
        value: _schedulerGuardedBuyDailyLimitLabel(dailyLimit),
      ),
      _ResultPair(
        label: 'duplicate order status',
        value: _schedulerGuardedBuyDuplicateLabel(duplicate),
      ),
      _ResultPair(
        label: 'primary block reason',
        value: result?.primaryBlockReason ?? 'not_loaded',
      ),
    ]);
  }
}

class _KisSchedulerGuardedBuyResultPanel extends StatelessWidget {
  const _KisSchedulerGuardedBuyResultPanel({required this.result});

  final KisSchedulerGuardedBuyResult result;

  @override
  Widget build(BuildContext context) {
    final submitted = result.submitted;
    final primaryBlockReason = result.primaryBlockReason ??
        (result.blockReasons.isEmpty ? 'n/a' : result.blockReasons.first);
    final skippedForSell = result.sellSkippedBuy;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      _StateLine(
        text: submitted
            ? 'SUBMITTED BUY: ${result.symbol ?? 'n/a'} qty ${result.quantity?.toString() ?? 'n/a'}'
            : skippedForSell
                ? 'SKIPPED: sell_review_required_before_buy'
                : 'BLOCKED: $primaryBlockReason',
        color: submitted
            ? Colors.redAccent
            : skippedForSell
                ? Colors.orangeAccent
                : Colors.amberAccent,
      ),
      const SizedBox(height: 10),
      Wrap(spacing: 8, runSpacing: 8, children: [
        _SoftBadge(
          text: 'Broker submit: ${_yesNo(result.brokerSubmitCalled)}',
          color: result.brokerSubmitCalled
              ? Colors.redAccent
              : Colors.lightBlueAccent,
        ),
        _SoftBadge(
          text: 'Manual submit: ${_yesNo(result.manualSubmitCalled)}',
          color: result.manualSubmitCalled
              ? Colors.redAccent
              : Colors.lightBlueAccent,
        ),
        _SoftBadge(
          text: 'Real order submitted: ${_yesNo(result.realOrderSubmitted)}',
          color: result.realOrderSubmitted
              ? Colors.redAccent
              : Colors.lightBlueAccent,
        ),
      ]),
      const SizedBox(height: 10),
      Wrap(spacing: 14, runSpacing: 8, children: [
        _ResultPair(label: 'result', value: result.result),
        _ResultPair(label: 'action', value: result.action),
        _ResultPair(label: 'reason', value: result.reason),
        _ResultPair(label: 'primary block reason', value: primaryBlockReason),
        _ResultPair(label: 'symbol', value: result.symbol ?? 'n/a'),
        _ResultPair(label: 'company', value: result.companyName ?? 'n/a'),
        _ResultPair(
            label: 'quantity', value: result.quantity?.toString() ?? 'n/a'),
        _ResultPair(
          label: 'estimated notional',
          value: _formatKrwOrDash(result.estimatedNotional),
        ),
        _ResultPair(
            label: 'order id', value: result.orderId?.toString() ?? 'none'),
        _ResultPair(label: 'KIS ODNO', value: result.kisOdno ?? 'none'),
        _ResultPair(
          label: 'broker order id',
          value: result.brokerOrderId ?? 'none',
        ),
      ]),
      const SizedBox(height: 10),
      _StateLine(
        text:
            'buy_result: ${result.buyResult['result'] ?? 'skipped'} / ${result.buyResult['reason'] ?? 'buy_execution_not_called'}',
      ),
      if (result.sellReviewResult.isNotEmpty) ...[
        const SizedBox(height: 8),
        _StateLine(
          text:
              'sell review: ${result.sellReviewResult['result'] ?? 'n/a'} / ${result.sellReviewResult['reason'] ?? 'n/a'}',
        ),
      ],
      if (result.blockReasons.isNotEmpty) ...[
        const SizedBox(height: 8),
        _StateLine(text: 'block reasons: ${_joinList(result.blockReasons)}'),
      ],
      const SizedBox(height: 4),
      ExpansionTile(
        tilePadding: EdgeInsets.zero,
        childrenPadding: EdgeInsets.zero,
        title: const Text('Developer Raw Payload'),
        children: [
          _StateLine(text: _prettyJson(result.rawPayload)),
        ],
      ),
    ]);
  }
}

String _schedulerGuardedBuyDailyLimitLabel(Map<String, dynamic> value) {
  if (value.isEmpty) return 'n/a';
  final remaining = value['daily_limit_remaining']?.toString();
  final maxOrders = value['max_orders_per_day']?.toString();
  final submitted = value['submitted_count_today']?.toString();
  final base =
      '${remaining == null || remaining == 'null' ? 'n/a' : remaining} remaining / ${maxOrders == null || maxOrders == 'null' ? 'n/a' : maxOrders} max';
  if (submitted == null || submitted == 'null') return base;
  return '$base, $submitted used';
}

String _schedulerGuardedBuyDuplicateLabel(Map<String, dynamic> value) {
  if (value.isEmpty) return 'n/a';
  final duplicate =
      _mapNullableBool(value, 'duplicate_open_buy_order') ?? false;
  if (duplicate) return 'blocked: duplicate open buy';
  final checked = _mapNullableBool(value, 'checked');
  if (checked == false) return 'not checked';
  return 'clear';
}

class _KisSchedulerGuardedSellReviewCard extends StatelessWidget {
  const _KisSchedulerGuardedSellReviewCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final result = controller.latestKisSchedulerGuardedSellReview;
    return Container(
      key: const Key('kis_scheduler_guarded_sell_review_card'),
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: _panelDecoration(),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.fact_check_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text('KIS Scheduler Guarded Sell Review',
                style: Theme.of(context).textTheme.titleSmall),
          ),
        ]),
        const SizedBox(height: 8),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(
              text: 'SCHEDULER GUARDED SELL REVIEW',
              color: Colors.lightBlueAccent),
          _SoftBadge(text: 'OPERATOR AUDIT', color: Colors.lightBlueAccent),
          _SoftBadge(text: 'SELL ONLY', color: Colors.greenAccent),
          _SoftBadge(text: 'BUY DISABLED', color: Colors.orangeAccent),
          _SoftBadge(text: 'REVIEW ONLY', color: Colors.greenAccent),
          _SoftBadge(text: 'NO BROKER SUBMIT', color: Colors.orangeAccent),
          _SoftBadge(text: 'SAFETY INVARIANTS', color: Colors.white70),
        ]),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          onPressed: controller.kisSchedulerGuardedSellReviewLoading
              ? null
              : () async {
                  final actionResult =
                      await controller.refreshKisSchedulerGuardedSellReview();
                  if (!context.mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(actionResult.message),
                    backgroundColor:
                        actionResult.success ? Colors.green : Colors.redAccent,
                  ));
                },
          icon: controller.kisSchedulerGuardedSellReviewLoading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.refresh, size: 18),
          label: Text(controller.kisSchedulerGuardedSellReviewLoading
              ? 'Refreshing guarded sell review...'
              : 'Refresh Guarded Sell Review'),
        ),
        if (controller.kisSchedulerGuardedSellReviewError != null) ...[
          const SizedBox(height: 10),
          _StateLine(
            text: _primaryLine(controller.kisSchedulerGuardedSellReviewError!),
            color: Colors.redAccent,
          ),
        ],
        const SizedBox(height: 12),
        if (result == null) ...[
          const _StateLine(
            text:
                'No scheduler guarded sell review data yet. Audit remains read-only.',
          ),
        ] else ...[
          _KisSchedulerGuardedSellReviewSummaryPanel(result: result),
          const SizedBox(height: 12),
          _KisSchedulerGuardedSellReviewAttempts(
            attempts: result.recentAttempts,
          ),
          const SizedBox(height: 12),
          _KisSchedulerGuardedSellSubmittedSells(
            submittedSells: result.submittedSells,
          ),
          const SizedBox(height: 12),
          _KisSchedulerGuardedSellBlockedAttempts(
            blockedAttempts: result.blockedAttempts,
          ),
          const SizedBox(height: 12),
          _KisSchedulerGuardedSellSafetyViolations(
            violations: result.safetyViolations,
          ),
          const SizedBox(height: 4),
          ExpansionTile(
            tilePadding: EdgeInsets.zero,
            childrenPadding: EdgeInsets.zero,
            title: const Text('Developer Raw Payload'),
            children: [
              _StateLine(text: _prettyJson(result.rawPayload)),
            ],
          ),
        ],
      ]),
    );
  }
}

class _KisSchedulerGuardedSellReviewSummaryPanel extends StatelessWidget {
  const _KisSchedulerGuardedSellReviewSummaryPanel({required this.result});

  final KisSchedulerGuardedSellReview result;

  @override
  Widget build(BuildContext context) {
    final summary = result.summary;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Guarded Sell Review Summary',
          style: TextStyle(fontWeight: FontWeight.w700)),
      const SizedBox(height: 8),
      Wrap(spacing: 14, runSpacing: 8, children: [
        _ResultPair(
            label: 'total attempts', value: summary.totalAttempts.toString()),
        _ResultPair(
            label: 'submitted count', value: summary.submittedCount.toString()),
        _ResultPair(
            label: 'blocked count', value: summary.blockedCount.toString()),
        _ResultPair(
          label: 'failed/skipped count',
          value: '${summary.failedCount}/${summary.skippedCount}',
        ),
        _ResultPair(
          label: 'stop-loss submit count',
          value: summary.stopLossSubmitCount.toString(),
        ),
        _ResultPair(
          label: 'take-profit submit count',
          value: summary.takeProfitSubmitCount.toString(),
        ),
        _ResultPair(
          label: 'daily limit blocks',
          value: summary.dailyLimitBlockCount.toString(),
        ),
        _ResultPair(
          label: 'duplicate order blocks',
          value: summary.duplicateOrderBlockCount.toString(),
        ),
        _ResultPair(
          label: 'no direct scheduler submit invariant',
          value: _yesNo(summary.noDirectSchedulerSubmitInvariantOk),
        ),
        _ResultPair(
          label: 'sell-only invariant',
          value: _yesNo(summary.sellOnlyInvariantOk),
        ),
        _ResultPair(
          label: 'latest attempt time',
          value: formatTimestampWithKst(
            summary.latestAttemptAt,
            fallback: 'n/a',
          ),
        ),
        _ResultPair(
          label: 'latest submitted time',
          value: formatTimestampWithKst(
            summary.latestSubmittedAt,
            fallback: 'n/a',
          ),
        ),
        _ResultPair(
          label: 'latest symbol',
          value: summary.latestSymbol ?? 'n/a',
        ),
      ]),
      if (result.topBlockReasons.isNotEmpty) ...[
        const SizedBox(height: 8),
        Wrap(spacing: 8, runSpacing: 8, children: [
          for (final reason in result.topBlockReasons.take(5))
            _SoftBadge(
              text: '${reason.label}: ${reason.count}',
              color: Colors.amberAccent,
            ),
        ]),
      ],
    ]);
  }
}

class _KisSchedulerGuardedSellReviewAttempts extends StatelessWidget {
  const _KisSchedulerGuardedSellReviewAttempts({required this.attempts});

  final List<KisSchedulerGuardedSellAttempt> attempts;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Recent Guarded Sell Attempts',
          style: TextStyle(fontWeight: FontWeight.w700)),
      const SizedBox(height: 8),
      if (attempts.isEmpty)
        const _StateLine(text: 'No scheduler guarded sell attempts recorded.')
      else
        for (final attempt in attempts.take(5))
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: _panelDecoration(),
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      _guardedSellAttemptTitle(
                          attempt.symbol, attempt.companyName),
                      style: const TextStyle(fontWeight: FontWeight.w800),
                    ),
                    const SizedBox(height: 8),
                    Wrap(spacing: 14, runSpacing: 8, children: [
                      _ResultPair(label: 'result', value: attempt.result),
                      _ResultPair(
                          label: 'trigger', value: attempt.trigger ?? 'n/a'),
                      _ResultPair(
                        label: 'primary block reason',
                        value: attempt.primaryBlockReason ?? 'n/a',
                      ),
                      _ResultPair(
                        label: 'scheduler sell enabled',
                        value: _yesNo(attempt.kisSchedulerSellEnabled),
                      ),
                      _ResultPair(
                        label: 'order id',
                        value: attempt.orderId ?? 'none',
                      ),
                      _ResultPair(
                        label: 'KIS ODNO',
                        value: attempt.kisOdno ?? 'none',
                      ),
                    ]),
                    const SizedBox(height: 8),
                    Wrap(spacing: 8, runSpacing: 8, children: [
                      _SoftBadge(
                        text:
                            'Broker submit: ${_yesNo(attempt.brokerSubmitCalled)}',
                        color: attempt.brokerSubmitCalled
                            ? Colors.redAccent
                            : Colors.lightBlueAccent,
                      ),
                      _SoftBadge(
                        text:
                            'Manual submit: ${_yesNo(attempt.manualSubmitCalled)}',
                        color: attempt.manualSubmitCalled
                            ? Colors.redAccent
                            : Colors.lightBlueAccent,
                      ),
                      _SoftBadge(
                        text:
                            'Real order submitted: ${_yesNo(attempt.realOrderSubmitted)}',
                        color: attempt.realOrderSubmitted
                            ? Colors.redAccent
                            : Colors.lightBlueAccent,
                      ),
                    ]),
                  ]),
            ),
          ),
    ]);
  }
}

class _KisSchedulerGuardedSellSubmittedSells extends StatelessWidget {
  const _KisSchedulerGuardedSellSubmittedSells({
    required this.submittedSells,
  });

  final List<KisSchedulerGuardedSellSubmittedSell> submittedSells;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Submitted Sells',
          style: TextStyle(fontWeight: FontWeight.w700)),
      const SizedBox(height: 8),
      if (submittedSells.isEmpty)
        const _StateLine(text: 'No submitted scheduler guarded sells recorded.')
      else
        for (final item in submittedSells.take(5))
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: _panelDecoration(),
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      _guardedSellAttemptTitle(item.symbol, item.companyName),
                      style: const TextStyle(fontWeight: FontWeight.w800),
                    ),
                    const SizedBox(height: 8),
                    Wrap(spacing: 14, runSpacing: 8, children: [
                      _ResultPair(
                          label: 'quantity',
                          value: item.quantity?.toString() ?? 'n/a'),
                      _ResultPair(
                          label: 'trigger', value: item.trigger ?? 'n/a'),
                      _ResultPair(
                          label: 'order id', value: item.orderId ?? 'none'),
                      _ResultPair(
                          label: 'KIS ODNO', value: item.kisOdno ?? 'none'),
                      _ResultPair(
                        label: 'parent scheduler run id',
                        value: item.parentSchedulerRunId ?? 'n/a',
                      ),
                      _ResultPair(
                        label: 'estimated notional',
                        value:
                            _displayNumber(item.estimatedNotional?.toDouble()),
                      ),
                    ]),
                    const SizedBox(height: 8),
                    Wrap(spacing: 8, runSpacing: 8, children: [
                      _SoftBadge(
                        text:
                            'Broker submit: ${_yesNo(item.brokerSubmitCalled)}',
                        color: Colors.redAccent,
                      ),
                      _SoftBadge(
                        text:
                            'Manual submit: ${_yesNo(item.manualSubmitCalled)}',
                        color: Colors.redAccent,
                      ),
                    ]),
                  ]),
            ),
          ),
    ]);
  }
}

class _KisSchedulerGuardedSellBlockedAttempts extends StatelessWidget {
  const _KisSchedulerGuardedSellBlockedAttempts({
    required this.blockedAttempts,
  });

  final List<KisSchedulerGuardedSellBlockedAttempt> blockedAttempts;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Blocked Attempts',
          style: TextStyle(fontWeight: FontWeight.w700)),
      const SizedBox(height: 8),
      if (blockedAttempts.isEmpty)
        const _StateLine(text: 'No blocked scheduler guarded sell attempts.')
      else
        for (final item in blockedAttempts.take(5))
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: _panelDecoration(),
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      item.symbol ?? 'WATCHLIST',
                      style: const TextStyle(fontWeight: FontWeight.w800),
                    ),
                    const SizedBox(height: 8),
                    Wrap(spacing: 14, runSpacing: 8, children: [
                      _ResultPair(label: 'result', value: item.result),
                      _ResultPair(
                        label: 'primary block reason',
                        value: item.primaryBlockReason ?? 'n/a',
                      ),
                    ]),
                    const SizedBox(height: 8),
                    const Wrap(spacing: 8, runSpacing: 8, children: [
                      _SoftBadge(
                        text: 'Broker submit: No',
                        color: Colors.lightBlueAccent,
                      ),
                      _SoftBadge(
                        text: 'Manual submit: No',
                        color: Colors.lightBlueAccent,
                      ),
                      _SoftBadge(
                        text: 'Real order submitted: No',
                        color: Colors.lightBlueAccent,
                      ),
                    ]),
                  ]),
            ),
          ),
    ]);
  }
}

class _KisSchedulerGuardedSellSafetyViolations extends StatelessWidget {
  const _KisSchedulerGuardedSellSafetyViolations({
    required this.violations,
  });

  final List<KisSchedulerGuardedSellSafetyViolation> violations;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Safety Violations',
          style: TextStyle(fontWeight: FontWeight.w700)),
      const SizedBox(height: 8),
      if (violations.isEmpty)
        const _StateLine(
          text: 'No scheduler guarded sell safety violations detected',
        )
      else
        for (final item in violations)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: _panelDecoration(),
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(children: [
                      const Icon(Icons.warning_amber_outlined,
                          size: 18, color: Colors.redAccent),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(item.label,
                            style:
                                const TextStyle(fontWeight: FontWeight.w800)),
                      ),
                      const _SoftBadge(
                        text: 'SAFETY VIOLATION',
                        color: Colors.redAccent,
                      ),
                    ]),
                    const SizedBox(height: 8),
                    Wrap(spacing: 14, runSpacing: 8, children: [
                      _ResultPair(label: 'reason', value: item.reason),
                      _ResultPair(label: 'run id', value: item.runId ?? 'n/a'),
                      _ResultPair(
                          label: 'order id', value: item.orderId ?? 'n/a'),
                      _ResultPair(label: 'symbol', value: item.symbol ?? 'n/a'),
                    ]),
                  ]),
            ),
          ),
    ]);
  }
}

String _guardedSellAttemptTitle(String? symbol, String? companyName) {
  final safeSymbol = symbol?.trim();
  final safeCompany = companyName?.trim();
  if (safeSymbol == null || safeSymbol.isEmpty) return 'WATCHLIST';
  if (safeCompany == null || safeCompany.isEmpty) return safeSymbol;
  return '$safeSymbol · $safeCompany';
}

class _KisSchedulerLiveAutomationCard extends StatelessWidget {
  const _KisSchedulerLiveAutomationCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final settings = controller.settings;
    final result = controller.latestKisSchedulerLiveResult;
    return Container(
      key: const Key('kis_scheduler_live_card'),
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.event_repeat_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text('KIS Scheduler Live Automation',
                style: Theme.of(context).textTheme.titleSmall),
          ),
        ]),
        const SizedBox(height: 8),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(text: 'DISABLED BY DEFAULT', color: Colors.amberAccent),
          _SoftBadge(text: 'REAL ORDERS GATED', color: Colors.redAccent),
          _SoftBadge(text: 'BUY/SELL LIMITED', color: Colors.greenAccent),
          _SoftBadge(text: 'MAX DAILY ORDERS', color: Colors.lightBlueAccent),
          _SoftBadge(text: 'KILL SWITCH PROTECTED', color: Colors.orangeAccent),
          _SoftBadge(text: 'DRY RUN BLOCKS LIVE', color: Colors.white70),
        ]),
        const SizedBox(height: 12),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _ResultPair(
              label: 'scheduler live',
              value: _boolText(settings.kisSchedulerLiveEnabled)),
          _ResultPair(
              label: 'allow real orders',
              value: _boolText(settings.kisSchedulerAllowRealOrders)),
          _ResultPair(
              label: 'allow limited buy',
              value: _boolText(settings.kisSchedulerAllowLimitedAutoBuy)),
          _ResultPair(
              label: 'allow limited sell',
              value: _boolText(settings.kisSchedulerAllowLimitedAutoSell)),
          _ResultPair(
              label: 'max live orders/day',
              value: settings.kisSchedulerMaxLiveOrdersPerDay.toString()),
        ]),
        const SizedBox(height: 12),
        FilledButton.icon(
          onPressed: controller.kisSchedulerLiveLoading
              ? null
              : () async {
                  final actionResult =
                      await controller.runKisSchedulerLiveOnce();
                  if (!context.mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(actionResult.message),
                    backgroundColor:
                        actionResult.success ? Colors.green : Colors.redAccent,
                  ));
                },
          icon: controller.kisSchedulerLiveLoading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.play_arrow),
          label: Text(controller.kisSchedulerLiveLoading
              ? 'Running scheduler live...'
              : 'Run Scheduler Live Once'),
        ),
        if (controller.kisSchedulerLiveError != null) ...[
          const SizedBox(height: 10),
          _StateLine(
              text: _primaryLine(controller.kisSchedulerLiveError!),
              color: Colors.redAccent),
        ],
        if (result == null) ...[
          const SizedBox(height: 10),
          const _StateLine(
            text:
                'No scheduler live run yet. Default backend state blocks real orders.',
          ),
        ] else ...[
          const SizedBox(height: 10),
          _KisSchedulerLiveResultPanel(result: result),
        ],
      ]),
    );
  }
}

class _KisSchedulerLiveResultPanel extends StatelessWidget {
  const _KisSchedulerLiveResultPanel({required this.result});

  final KisSchedulerLiveResult result;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      if (result.submitted) ...[
        _StateLine(
          text:
              'KIS SCHEDULER LIVE SUBMITTED: order ${result.orderId ?? 'n/a'}',
          color: Colors.redAccent,
        ),
        const SizedBox(height: 10),
      ],
      Wrap(spacing: 14, runSpacing: 8, children: [
        _ResultPair(label: 'result', value: result.result),
        _ResultPair(label: 'action', value: result.action),
        _ResultPair(label: 'reason', value: result.reason),
        _ResultPair(
            label: 'real_order_submitted',
            value: _boolText(result.realOrderSubmitted)),
        _ResultPair(
            label: 'broker_submit_called',
            value: _boolText(result.brokerSubmitCalled)),
        _ResultPair(
            label: 'manual_submit_called',
            value: _boolText(result.manualSubmitCalled)),
        _ResultPair(
            label: 'scheduler_real_order_enabled',
            value: _boolText(result.schedulerRealOrderEnabled)),
      ]),
      const SizedBox(height: 10),
      Wrap(spacing: 8, runSpacing: 8, children: [
        _SoftBadge(
          text:
              "scheduler_live_enabled=${_nullableBoolText(result.nullableCheck('kis_scheduler_live_enabled'))}",
          color: Colors.lightBlueAccent,
        ),
        _SoftBadge(
          text:
              "allow_real_orders=${_nullableBoolText(result.nullableCheck('kis_scheduler_allow_real_orders'))}",
          color: Colors.lightBlueAccent,
        ),
        _SoftBadge(
          text:
              "allow_limited_buy=${_nullableBoolText(result.nullableCheck('kis_scheduler_allow_limited_auto_buy'))}",
          color: Colors.lightBlueAccent,
        ),
        _SoftBadge(
          text:
              "allow_limited_sell=${_nullableBoolText(result.nullableCheck('kis_scheduler_allow_limited_auto_sell'))}",
          color: Colors.lightBlueAccent,
        ),
      ]),
      if (result.sellResult.isNotEmpty) ...[
        const SizedBox(height: 8),
        _StateLine(
            text:
                'sell_result: ${result.sellResult['result'] ?? 'n/a'} / ${result.sellResult['reason'] ?? 'n/a'}'),
      ],
      if (result.buyResult.isNotEmpty) ...[
        const SizedBox(height: 8),
        _StateLine(
            text:
                'buy_result: ${result.buyResult['result'] ?? 'n/a'} / ${result.buyResult['reason'] ?? 'n/a'}'),
      ],
    ]);
  }
}

class _KisBuyShadowDecisionCard extends StatelessWidget {
  const _KisBuyShadowDecisionCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final settings = controller.settings;
    final result = controller.latestKisBuyShadowDecision;
    return Container(
      key: const Key('kis_buy_shadow_decision_card'),
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.manage_search_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text('KIS Buy Shadow Decision',
                style: Theme.of(context).textTheme.titleSmall),
          ),
        ]),
        const SizedBox(height: 8),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(text: 'SHADOW BUY ONLY', color: Colors.lightBlueAccent),
          _SoftBadge(text: 'NO BROKER SUBMIT', color: Colors.greenAccent),
          _SoftBadge(text: 'NO MANUAL SUBMIT', color: Colors.greenAccent),
          _SoftBadge(text: 'LIVE AUTO BUY DISABLED', color: Colors.amberAccent),
          _SoftBadge(
              text: 'SCHEDULER REAL ORDERS DISABLED', color: Colors.redAccent),
          _SoftBadge(text: 'RISK GATED', color: Colors.white70),
        ]),
        const SizedBox(height: 12),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _ResultPair(
              label: 'shadow buy',
              value: _boolText(settings.kisLimitedAutoBuyShadowEnabled)),
          _ResultPair(
              label: 'live auto buy',
              value: _boolText(settings.kisLimitedAutoBuyEnabled)),
          _ResultPair(
              label: 'requires review',
              value: _boolText(settings.kisLimitedAutoBuyRequiresShadowReview)),
          _ResultPair(
              label: 'max orders/day',
              value: settings.kisLimitedAutoBuyMaxOrdersPerDay.toString()),
          _ResultPair(
              label: 'max notional pct',
              value: _formatPercentValue(
                  settings.kisLimitedAutoBuyMaxNotionalPct * 100)),
          _ResultPair(
              label: 'min score',
              value: _score(settings.kisLimitedAutoBuyMinFinalScore)),
          _ResultPair(
              label: 'min confidence',
              value: _score(settings.kisLimitedAutoBuyMinConfidence)),
          _ResultPair(
              label: 'max positions',
              value: settings.kisLimitedAutoBuyMaxPositions.toString()),
          _ResultPair(
              label: 'no new entry after',
              value: settings.kisLimitedAutoBuyNoNewEntryAfter),
        ]),
        const SizedBox(height: 12),
        FilledButton.icon(
          onPressed: controller.kisBuyShadowLoading
              ? null
              : () async {
                  final actionResult = await controller.runKisBuyShadowOnce();
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
              ? 'Running buy shadow...'
              : 'Run Buy Shadow Once'),
        ),
        if (controller.kisBuyShadowError != null) ...[
          const SizedBox(height: 10),
          _StateLine(
              text: _primaryLine(controller.kisBuyShadowError!),
              color: Colors.redAccent),
        ],
        if (result == null) ...[
          const SizedBox(height: 10),
          const _StateLine(
            text:
                'No buy shadow decision run yet. This card never submits KIS buy orders.',
          ),
        ] else ...[
          const SizedBox(height: 10),
          _KisBuyShadowDecisionPanel(result: result),
        ],
      ]),
    );
  }
}

class _KisBuyShadowDecisionPanel extends StatelessWidget {
  const _KisBuyShadowDecisionPanel({required this.result});

  final KisBuyShadowDecision result;

  @override
  Widget build(BuildContext context) {
    final candidate = result.candidate;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      _StateLine(
        text: candidate == null
            ? '${_buyShadowDecisionLabel(result.decision)}. ${result.reason}'
            : '${_buyShadowDecisionLabel(result.decision)}. ${candidate.symbol} is shadow-only; no buy order is submitted.',
      ),
      const SizedBox(height: 10),
      Wrap(spacing: 14, runSpacing: 8, children: [
        _ResultPair(
            label: 'decision', value: _buyShadowDecisionLabel(result.decision)),
        _ResultPair(label: 'action', value: result.action),
        _ResultPair(label: 'reason', value: result.reason),
        _ResultPair(label: 'symbol', value: candidate?.symbol ?? 'n/a'),
        _ResultPair(label: 'final score', value: _score(candidate?.finalScore)),
        _ResultPair(label: 'confidence', value: _score(candidate?.confidence)),
        _ResultPair(label: 'quant score', value: _score(candidate?.quantScore)),
        _ResultPair(
            label: 'GPT buy score', value: _score(candidate?.gptBuyScore)),
        _ResultPair(
            label: 'current price',
            value: _formatReviewKrwOrDash(candidate?.currentPrice)),
        _ResultPair(
            label: 'suggested notional',
            value: _formatReviewKrwOrDash(candidate?.suggestedNotional)),
        _ResultPair(
            label: 'suggested qty',
            value: candidate?.suggestedQuantity?.toString() ?? 'n/a'),
        _ResultPair(
            label: 'real_order_submitted',
            value: _boolText(result.realOrderSubmitted)),
        _ResultPair(
            label: 'broker_submit_called',
            value: _boolText(result.brokerSubmitCalled)),
        _ResultPair(
            label: 'manual_submit_called',
            value: _boolText(result.manualSubmitCalled)),
        if (result.createdAt != null)
          _ResultPair(
              label: 'created_at',
              value: formatTimestampWithKst(result.createdAt)),
      ]),
      if (result.failedChecks.isNotEmpty) ...[
        const SizedBox(height: 8),
        _StateLine(text: 'failed_checks: ${_joinList(result.failedChecks)}'),
      ],
      if (candidate?.riskFlags.isNotEmpty == true ||
          result.riskFlags.isNotEmpty) ...[
        const SizedBox(height: 8),
        _StateLine(
            text:
                'risk_flags: ${_joinList(candidate?.riskFlags ?? result.riskFlags)}'),
      ],
      if (candidate?.gatingNotes.isNotEmpty == true ||
          result.gatingNotes.isNotEmpty) ...[
        const SizedBox(height: 8),
        _StateLine(
            text:
                'gating_notes: ${_joinList(candidate?.gatingNotes ?? result.gatingNotes)}'),
      ],
      const SizedBox(height: 10),
      Wrap(spacing: 8, runSpacing: 8, children: [
        _SoftBadge(
          text: 'auto_buy_enabled=${_boolText(result.autoBuyEnabled)}',
          color: Colors.orangeAccent,
        ),
        _SoftBadge(
          text: 'auto_sell_enabled=${_boolText(result.autoSellEnabled)}',
          color: Colors.orangeAccent,
        ),
        _SoftBadge(
          text:
              'scheduler_real_order_enabled=${_boolText(result.schedulerRealOrderEnabled)}',
          color: Colors.orangeAccent,
        ),
      ]),
    ]);
  }
}

class _KisExitShadowDecisionPanel extends StatelessWidget {
  const _KisExitShadowDecisionPanel({
    required this.result,
    required this.controller,
  });

  final KisExitShadowDecision result;
  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final candidate = result.candidate;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      _StateLine(
        text: candidate == null
            ? 'HOLD. No shadow sell candidate was selected.'
            : '${_shadowDecisionLabel(result.decision)}. ${candidate.symbol} remains manual-confirm only.',
      ),
      const SizedBox(height: 10),
      Wrap(spacing: 8, runSpacing: 8, children: [
        _SoftBadge(
          text: 'decision=${_shadowDecisionLabel(result.decision)}',
          color: result.isWouldSell ? Colors.greenAccent : Colors.white70,
        ),
        _SoftBadge(
          text: 'real_order_submitted=${_boolText(result.realOrderSubmitted)}',
          color: Colors.lightBlueAccent,
        ),
        _SoftBadge(
          text: 'broker_submit_called=${_boolText(result.brokerSubmitCalled)}',
          color: Colors.lightBlueAccent,
        ),
        _SoftBadge(
          text: 'manual_submit_called=${_boolText(result.manualSubmitCalled)}',
          color: Colors.lightBlueAccent,
        ),
        _SoftBadge(
          text:
              'real_order_submit_allowed=${_boolText(result.realOrderSubmitAllowed)}',
          color: Colors.lightBlueAccent,
        ),
      ]),
      const SizedBox(height: 10),
      Wrap(spacing: 14, runSpacing: 8, children: [
        _ResultPair(label: 'mode', value: result.mode),
        _ResultPair(label: 'action', value: result.action),
        _ResultPair(label: 'reason', value: result.reason),
        _ResultPair(
          label: 'auto_sell_enabled',
          value: _boolText(result.autoSellEnabled),
        ),
        _ResultPair(
          label: 'scheduler_real_order_enabled',
          value: _boolText(result.schedulerRealOrderEnabled),
        ),
        _ResultPair(
          label: 'manual_confirm_required',
          value: _boolText(result.manualConfirmRequired),
        ),
        if (result.createdAt != null)
          _ResultPair(
            label: 'created_at',
            value: formatTimestampWithKst(result.createdAt),
          ),
      ]),
      if (candidate != null) ...[
        const SizedBox(height: 12),
        _KisExitShadowCandidateCard(
          candidate: candidate,
          decision: result,
          controller: controller,
        ),
      ],
      const SizedBox(height: 10),
      _StateLine(text: 'risk_flags: ${_joinList(result.riskFlags)}'),
      if (result.gatingNotes.isNotEmpty) ...[
        const SizedBox(height: 8),
        _StateLine(text: 'gating_notes: ${_joinList(result.gatingNotes)}'),
      ],
      if (result.candidatesEvaluated.isNotEmpty) ...[
        const SizedBox(height: 8),
        _StateLine(
          text:
              'candidates_evaluated: ${result.candidatesEvaluated.length.toString()}',
        ),
      ],
    ]);
  }
}

class _KisExitShadowCandidateCard extends StatelessWidget {
  const _KisExitShadowCandidateCard({
    required this.candidate,
    required this.decision,
    required this.controller,
  });

  final KisExitShadowCandidate candidate;
  final KisExitShadowDecision decision;
  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.assignment_late_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text(candidate.symbol,
                style: Theme.of(context).textTheme.titleSmall),
          ),
          _SoftBadge(text: candidate.trigger, color: Colors.greenAccent),
        ]),
        const SizedBox(height: 10),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(text: 'WOULD SELL ONLY', color: Colors.lightBlueAccent),
          _SoftBadge(
              text: 'MANUAL CONFIRM REQUIRED', color: Colors.greenAccent),
          _SoftBadge(text: 'NO AUTO SELL', color: Colors.amberAccent),
          _SoftBadge(text: 'NO BROKER SUBMIT', color: Colors.orangeAccent),
        ]),
        const SizedBox(height: 10),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _ResultPair(label: 'side', value: candidate.side),
          _ResultPair(
            label: 'quantity_available',
            value: _qtyText(candidate.quantityAvailable),
          ),
          _ResultPair(
            label: 'suggested_quantity',
            value: _qtyText(candidate.suggestedQuantity),
          ),
          _ResultPair(
            label: 'current_price',
            value: _formatKrwOrDash(candidate.currentPrice),
          ),
          _ResultPair(
            label: 'cost_basis',
            value: _formatKrwOrDash(candidate.costBasis),
          ),
          _ResultPair(
            label: 'current_value',
            value: _formatKrwOrDash(candidate.currentValue),
          ),
          _ResultPair(
            label: 'unrealized_pl',
            value: _formatKrwOrDash(candidate.unrealizedPl),
          ),
          _ResultPair(
            label: 'unrealized_pl_pct',
            value: _formatShadowPlPercent(candidate),
          ),
          _ResultPair(label: 'trigger', value: candidate.trigger),
          _ResultPair(label: 'trigger_source', value: candidate.triggerSource),
        ]),
        if (candidate.reason.isNotEmpty) ...[
          const SizedBox(height: 10),
          _StateLine(text: candidate.reason),
        ],
        if (candidate.riskFlags.isNotEmpty) ...[
          const SizedBox(height: 8),
          _StateLine(text: 'risk_flags: ${_joinList(candidate.riskFlags)}'),
        ],
        if (candidate.gatingNotes.isNotEmpty) ...[
          const SizedBox(height: 8),
          _StateLine(text: 'gating_notes: ${_joinList(candidate.gatingNotes)}'),
        ],
        const SizedBox(height: 10),
        Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(
            text:
                'real_order_submit_allowed=${_boolText(candidate.realOrderSubmitAllowed)}',
            color: Colors.lightBlueAccent,
          ),
          _SoftBadge(
            text:
                'broker_submit_called=${_boolText(candidate.brokerSubmitCalled)}',
            color: Colors.lightBlueAccent,
          ),
          _SoftBadge(
            text:
                'manual_submit_called=${_boolText(candidate.manualSubmitCalled)}',
            color: Colors.lightBlueAccent,
          ),
        ]),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          onPressed: candidate.suggestedQuantityInt == null
              ? null
              : () {
                  final actionResult =
                      controller.prepareKisManualSellFromShadowCandidate(
                    candidate,
                    decision: decision,
                  );
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(actionResult.message),
                    backgroundColor:
                        actionResult.success ? Colors.green : Colors.redAccent,
                  ));
                },
          icon: const Icon(Icons.edit_note_outlined),
          label: const Text('Prepare Manual Sell Ticket'),
        ),
      ]),
    );
  }
}

class _KisLiveExitPreflightResultPanel extends StatelessWidget {
  const _KisLiveExitPreflightResultPanel({
    required this.result,
    required this.controller,
  });

  final KisLiveExitPreflightResult result;
  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final noHeldPosition = !result.hasHeldPosition ||
        result.blockedBy.contains('no_held_position');
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      if (noHeldPosition) ...[
        const _StateLine(text: 'No held KIS position to evaluate.'),
        const SizedBox(height: 10),
      ] else if (result.candidates.isNotEmpty) ...[
        const _StateLine(
          text:
              'Exit candidate found. Manual confirmation is required before any live sell order.',
        ),
        const SizedBox(height: 10),
      ] else ...[
        const _StateLine(
          text: 'Hold / manual review only. No auto sell and no broker submit.',
        ),
        const SizedBox(height: 10),
      ],
      Wrap(spacing: 8, runSpacing: 8, children: [
        _SoftBadge(
          text: 'real_order_submitted=${_boolText(result.realOrderSubmitted)}',
          color: Colors.lightBlueAccent,
        ),
        _SoftBadge(
          text: 'broker_submit_called=${_boolText(result.brokerSubmitCalled)}',
          color: Colors.lightBlueAccent,
        ),
        _SoftBadge(
          text: 'manual_submit_called=${_boolText(result.manualSubmitCalled)}',
          color: Colors.lightBlueAccent,
        ),
        _SoftBadge(
          text:
              'real_order_submit_allowed=${_boolText(result.realOrderSubmitAllowed)}',
          color: Colors.lightBlueAccent,
        ),
        _SoftBadge(
          text:
              'manual_confirm_required=${_boolText(result.manualConfirmRequired)}',
          color: Colors.greenAccent,
        ),
        _SoftBadge(
          text: 'auto_sell_enabled=${_boolText(result.autoSellEnabled)}',
          color: Colors.amberAccent,
        ),
      ]),
      const SizedBox(height: 10),
      Wrap(spacing: 14, runSpacing: 8, children: [
        _ResultPair(label: 'status', value: result.status),
        _ResultPair(label: 'mode', value: result.executionMode),
        _ResultPair(
          label: 'live_auto_enabled',
          value: _boolText(result.liveAutoEnabled),
        ),
        _ResultPair(
          label: 'candidate_count',
          value: result.candidateCount.toString(),
        ),
        _ResultPair(label: 'action', value: result.action),
        _ResultPair(label: 'symbol', value: result.symbol ?? 'n/a'),
        _ResultPair(label: 'qty', value: _qtyText(result.qty)),
        _ResultPair(
          label: 'estimated_notional',
          value: _formatKrw(result.estimatedNotional),
        ),
        if (result.costBasis != null)
          _ResultPair(
            label: 'cost_basis',
            value: _formatKrw(result.costBasis),
          ),
        if (result.currentValue != null)
          _ResultPair(
            label: 'current_value',
            value: _formatKrw(result.currentValue),
          ),
        if (result.unrealizedPl != null)
          _ResultPair(
            label: 'unrealized_pl',
            value: _formatKrw(result.unrealizedPl),
          ),
        if (result.unrealizedPlPct != null)
          _ResultPair(
            label: 'unrealized_pl_pct',
            value: _formatPercentFromDecimal(result.unrealizedPlPct),
          ),
        if (result.takeProfitThresholdPct != null)
          _ResultPair(
            label: 'take_profit_threshold',
            value: _formatPercentValue(result.takeProfitThresholdPct),
          ),
        if (result.stopLossThresholdPct != null)
          _ResultPair(
            label: 'stop_loss_threshold',
            value: _formatPercentValue(result.stopLossThresholdPct),
          ),
        if (result.exitTriggerSource != null)
          _ResultPair(
            label: 'exit_trigger_source',
            value: result.exitTriggerSource!,
          ),
        _ResultPair(label: 'reason', value: result.reason),
        _ResultPair(
          label: 'would_submit_if_enabled',
          value: _boolText(result.wouldSubmitIfEnabled),
        ),
      ]),
      if (result.candidates.isNotEmpty) ...[
        const SizedBox(height: 12),
        for (final candidate in result.candidates) ...[
          _KisLiveExitCandidateCard(
            candidate: candidate,
            preflight: result,
            controller: controller,
          ),
          const SizedBox(height: 10),
        ],
      ],
      const SizedBox(height: 10),
      _StateLine(text: 'blocked_by: ${_joinList(result.blockedBy)}'),
      const SizedBox(height: 8),
      _StateLine(text: 'risk_flags: ${_joinList(result.riskFlags)}'),
      if (result.gatingNotes.isNotEmpty) ...[
        const SizedBox(height: 8),
        _StateLine(text: 'gating_notes: ${_joinList(result.gatingNotes)}'),
      ],
    ]);
  }
}

class _KisLiveExitCandidateCard extends StatelessWidget {
  const _KisLiveExitCandidateCard({
    required this.candidate,
    required this.preflight,
    required this.controller,
  });

  final KisLiveExitCandidate candidate;
  final KisLiveExitPreflightResult preflight;
  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.assignment_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text(candidate.symbol,
                style: Theme.of(context).textTheme.titleSmall),
          ),
          _SoftBadge(text: candidate.trigger, color: Colors.greenAccent),
        ]),
        const SizedBox(height: 10),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(text: 'PREPARE ONLY', color: Colors.lightBlueAccent),
          _SoftBadge(
              text: 'MANUAL CONFIRM REQUIRED', color: Colors.greenAccent),
          _SoftBadge(text: 'NO AUTO SELL', color: Colors.amberAccent),
          _SoftBadge(text: 'NO BROKER SUBMIT', color: Colors.orangeAccent),
        ]),
        const SizedBox(height: 10),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _ResultPair(label: 'side', value: candidate.side),
          _ResultPair(
            label: 'quantity_available',
            value: _qtyText(candidate.quantityAvailable),
          ),
          _ResultPair(
            label: 'suggested_quantity',
            value: _qtyText(candidate.suggestedQuantity),
          ),
          _ResultPair(
            label: 'current_price',
            value: _formatKrwOrDash(candidate.currentPrice),
          ),
          _ResultPair(
            label: 'cost_basis',
            value: _formatKrwOrDash(candidate.costBasis),
          ),
          _ResultPair(
            label: 'current_value',
            value: _formatKrwOrDash(candidate.currentValue),
          ),
          _ResultPair(
            label: 'unrealized_pl',
            value: _formatKrwOrDash(candidate.unrealizedPl),
          ),
          _ResultPair(
            label: 'unrealized_pl_pct',
            value: _formatSafePlPercent(candidate),
          ),
          _ResultPair(label: 'trigger_source', value: candidate.triggerSource),
          _ResultPair(label: 'severity', value: candidate.severity),
          _ResultPair(label: 'action_hint', value: candidate.actionHint),
          _ResultPair(
            label: 'submit_ready',
            value: _boolText(candidate.submitReady),
          ),
        ]),
        if (candidate.reason.isNotEmpty) ...[
          const SizedBox(height: 10),
          _StateLine(text: candidate.reason),
        ],
        if (candidate.riskFlags.isNotEmpty) ...[
          const SizedBox(height: 8),
          _StateLine(text: 'risk_flags: ${_joinList(candidate.riskFlags)}'),
        ],
        if (candidate.gatingNotes.isNotEmpty) ...[
          const SizedBox(height: 8),
          _StateLine(text: 'gating_notes: ${_joinList(candidate.gatingNotes)}'),
        ],
        const SizedBox(height: 10),
        Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(
            text:
                'real_order_submit_allowed=${_boolText(candidate.realOrderSubmitAllowed)}',
            color: Colors.lightBlueAccent,
          ),
          _SoftBadge(
            text:
                'broker_submit_called=${_boolText(candidate.brokerSubmitCalled)}',
            color: Colors.lightBlueAccent,
          ),
          _SoftBadge(
            text:
                'manual_submit_called=${_boolText(candidate.manualSubmitCalled)}',
            color: Colors.lightBlueAccent,
          ),
        ]),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          onPressed: candidate.suggestedQuantityInt == null
              ? null
              : () {
                  final actionResult =
                      controller.prepareKisManualSellFromExitCandidate(
                    candidate,
                    preflight: preflight,
                  );
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(actionResult.message),
                    backgroundColor:
                        actionResult.success ? Colors.green : Colors.redAccent,
                  ));
                },
          icon: const Icon(Icons.edit_note_outlined),
          label: const Text('Prepare Manual Sell Ticket'),
        ),
      ]),
    );
  }
}

class _KisSchedulerSimulationPanel extends StatelessWidget {
  const _KisSchedulerSimulationPanel({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final status = controller.kisSchedulerStatus;
    final result = controller.kisSchedulerRunResult;
    return Container(
      key: const Key('kis_scheduler_simulation_card'),
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.schedule_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text('KIS Scheduler Simulation',
                style: Theme.of(context).textTheme.titleSmall),
          ),
          IconButton(
            tooltip: 'Refresh KIS scheduler status',
            onPressed: controller.kisSchedulerStatusLoading
                ? null
                : () async {
                    final actionResult =
                        await controller.refreshKisSchedulerStatus();
                    if (!context.mounted) return;
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                      content: Text(actionResult.message),
                      backgroundColor: actionResult.success
                          ? Colors.green
                          : Colors.redAccent,
                    ));
                  },
            icon: controller.kisSchedulerStatusLoading
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.refresh),
          ),
        ]),
        const SizedBox(height: 8),
        Wrap(spacing: 8, runSpacing: 8, children: [
          const _SoftBadge(
              text: 'DISABLED BY DEFAULT', color: Colors.amberAccent),
          const _SoftBadge(text: 'DRY-RUN ONLY', color: Colors.greenAccent),
          const _SoftBadge(
              text: 'REAL ORDER SCHEDULER DISABLED',
              color: Colors.orangeAccent),
          _SoftBadge(
              text:
                  'real_orders_allowed=${_boolText(status.realOrdersAllowed)}',
              color: Colors.lightBlueAccent),
        ]),
        const SizedBox(height: 10),
        _KisSchedulerStatusGrid(status: status),
        if (!controller.kisSchedulerStatusLoaded &&
            controller.kisSchedulerStatusError == null) ...[
          const SizedBox(height: 10),
          const _StateLine(text: 'Status not loaded yet.'),
        ],
        if (controller.kisSchedulerStatusError != null) ...[
          const SizedBox(height: 10),
          _RetryLine(
            text: _primaryLine(controller.kisSchedulerStatusError!),
            onRetry: controller.kisSchedulerStatusLoading
                ? null
                : controller.refreshKisSchedulerStatus,
          ),
        ],
        const SizedBox(height: 12),
        FilledButton.icon(
          onPressed: controller.kisSchedulerRunLoading
              ? null
              : () async {
                  final actionResult =
                      await controller.runKisSchedulerDryRunOnce();
                  if (!context.mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(actionResult.message),
                    backgroundColor:
                        actionResult.success ? Colors.green : Colors.redAccent,
                  ));
                },
          icon: controller.kisSchedulerRunLoading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.play_circle_outline),
          label: Text(controller.kisSchedulerRunLoading
              ? 'Running scheduler dry-run...'
              : 'Run KIS Scheduler Dry-Run Once'),
        ),
        if (controller.kisSchedulerRunError != null) ...[
          const SizedBox(height: 10),
          _RetryLine(
            text: _primaryLine(controller.kisSchedulerRunError!),
            onRetry: controller.kisSchedulerRunLoading
                ? null
                : controller.runKisSchedulerDryRunOnce,
          ),
        ],
        if (result != null) ...[
          const SizedBox(height: 10),
          _KisSchedulerResultPanel(result: result),
        ],
      ]),
    );
  }
}

class _KisSchedulerStatusGrid extends StatelessWidget {
  const _KisSchedulerStatusGrid({required this.status});

  final KisSchedulerSimulationStatus status;

  @override
  Widget build(BuildContext context) {
    return Wrap(spacing: 14, runSpacing: 8, children: [
      _ResultPair(label: 'enabled', value: _boolText(status.enabled)),
      _ResultPair(label: 'dry_run', value: _boolText(status.dryRun)),
      _ResultPair(
          label: 'allow_real_orders', value: _boolText(status.allowRealOrders)),
      _ResultPair(
          label: 'real_orders_allowed',
          value: _boolText(status.realOrdersAllowed)),
      _ResultPair(
        label: 'real_order_scheduler_enabled',
        value: _boolText(status.realOrderSchedulerEnabled),
      ),
      _ResultPair(
        label: 'runtime_scheduler_enabled',
        value: _nullableBoolText(status.runtimeSchedulerEnabled),
      ),
      _ResultPair(
        label: 'runtime_dry_run',
        value: _nullableBoolText(status.runtimeDryRun),
      ),
      _ResultPair(
        label: 'kill_switch',
        value: _nullableBoolText(status.killSwitch),
      ),
      _ResultPair(
        label: 'live_scheduler_ready',
        value: _nullableBoolText(status.liveSchedulerReady),
      ),
      _ResultPair(
        label: 'scheduler_live_enabled',
        value: _nullableBoolText(status.kisSchedulerLiveEnabled),
      ),
      _ResultPair(
        label: 'allow_limited_auto_buy',
        value: _nullableBoolText(status.kisSchedulerAllowLimitedAutoBuy),
      ),
      _ResultPair(
        label: 'allow_limited_auto_sell',
        value: _nullableBoolText(status.kisSchedulerAllowLimitedAutoSell),
      ),
      _ResultPair(
        label: 'max_live_orders/day',
        value: status.kisSchedulerMaxLiveOrdersPerDay?.toString() ?? 'n/a',
      ),
    ]);
  }
}

class _KisSchedulerResultPanel extends StatelessWidget {
  const _KisSchedulerResultPanel({required this.result});

  final KisSchedulerRunResult result;

  @override
  Widget build(BuildContext context) {
    final reason = result.reason.isNotEmpty
        ? result.reason
        : result.triggerBlockReason ?? '';
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Wrap(spacing: 8, runSpacing: 8, children: [
        _SoftBadge(
          text: 'real_order_submitted=${_boolText(result.realOrderSubmitted)}',
          color: Colors.lightBlueAccent,
        ),
        _SoftBadge(
          text: 'broker_submit_called=${_boolText(result.brokerSubmitCalled)}',
          color: Colors.lightBlueAccent,
        ),
        _SoftBadge(
          text: 'manual_submit_called=${_boolText(result.manualSubmitCalled)}',
          color: Colors.lightBlueAccent,
        ),
      ]),
      const SizedBox(height: 10),
      Wrap(spacing: 14, runSpacing: 8, children: [
        _ResultPair(label: 'action', value: result.action),
        _ResultPair(label: 'result', value: result.result),
        _ResultPair(
            label: 'triggered symbol', value: result.triggeredSymbol ?? 'n/a'),
        _ResultPair(
            label: 'signal_id', value: result.signalId?.toString() ?? 'n/a'),
        _ResultPair(
            label: 'order_id', value: result.orderId?.toString() ?? 'n/a'),
        if (result.createdAt?.isNotEmpty == true)
          _ResultPair(
              label: 'created_at',
              value: formatTimestampWithKst(result.createdAt)),
        _ResultPair(label: 'reason', value: reason.isEmpty ? 'n/a' : reason),
      ]),
      const SizedBox(height: 10),
      Wrap(spacing: 14, runSpacing: 8, children: [
        _ResultPair(label: 'dry_run', value: _boolText(result.dryRun)),
        _ResultPair(label: 'simulated', value: _boolText(result.simulated)),
        _ResultPair(
            label: 'scheduler_dry_run',
            value: _boolText(result.schedulerDryRun)),
        _ResultPair(
          label: 'scheduler_allow_real_orders',
          value: _boolText(result.schedulerAllowRealOrders),
        ),
      ]),
      if (result.aiBuyScore != null ||
          result.aiSellScore != null ||
          result.confidence != null ||
          result.riskFlags.isNotEmpty ||
          result.gatingNotes.isNotEmpty) ...[
        const SizedBox(height: 10),
        const _StateLine(
            text: 'GPT Advisory Context - Preview Only - No Broker Submit'),
        const SizedBox(height: 8),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _ResultPair(label: 'ai_buy_score', value: _score(result.aiBuyScore)),
          _ResultPair(
              label: 'ai_sell_score', value: _score(result.aiSellScore)),
          _ResultPair(label: 'confidence', value: _score(result.confidence)),
          _ResultPair(
              label: 'final_entry_score',
              value: _score(result.finalEntryScore)),
          _ResultPair(
              label: 'event_risk', value: _eventRiskLabel(result.eventRisk)),
          _ResultPair(
              label: 'indicator_status',
              value: result.indicatorStatus ?? 'n/a'),
        ]),
        if (result.gptReason?.isNotEmpty == true) ...[
          const SizedBox(height: 8),
          _StateLine(text: 'gpt_reason: ${result.gptReason!}'),
        ],
        const SizedBox(height: 8),
        if (result.riskFlags.isNotEmpty)
          _StateLine(text: 'risk_flags: ${_joinList(result.riskFlags)}'),
        if (result.gatingNotes.isNotEmpty) ...[
          const SizedBox(height: 8),
          _StateLine(text: 'gating_notes: ${_joinList(result.gatingNotes)}'),
        ],
      ],
    ]);
  }
}

// ignore: unused_element
class _KisPreviewAdvisoryPanel extends StatelessWidget {
  const _KisPreviewAdvisoryPanel({required this.candidate});

  final Candidate candidate;

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
          const Icon(Icons.psychology_alt_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text('KIS GPT Advisory Context',
                style: Theme.of(context).textTheme.titleSmall),
          ),
        ]),
        const SizedBox(height: 8),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(text: 'PREVIEW ONLY', color: Colors.lightBlueAccent),
          _SoftBadge(text: 'NO BROKER SUBMIT', color: Colors.orangeAccent),
        ]),
        const SizedBox(height: 10),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _ResultPair(label: 'symbol', value: candidate.symbol),
          _ResultPair(
              label: 'ai_buy_score', value: _score(candidate.aiBuyScore)),
          _ResultPair(
              label: 'ai_sell_score', value: _score(candidate.aiSellScore)),
          _ResultPair(label: 'confidence', value: _score(candidate.confidence)),
          _ResultPair(
              label: 'event_risk', value: candidate.eventRiskLevel ?? 'n/a'),
          _ResultPair(
              label: 'indicator_status',
              value: candidate.indicatorStatus.isEmpty
                  ? 'n/a'
                  : candidate.indicatorStatus),
          _ResultPair(
              label: 'final_buy_score', value: _score(candidate.finalBuyScore)),
          _ResultPair(
              label: 'final_sell_score',
              value: _score(candidate.finalSellScore)),
        ]),
        if (candidate.gptReason.isNotEmpty) ...[
          const SizedBox(height: 8),
          _StateLine(text: 'gpt_reason: ${candidate.gptReason}'),
        ],
        if (candidate.riskFlags.isNotEmpty) ...[
          const SizedBox(height: 8),
          _StateLine(text: 'risk_flags: ${_joinList(candidate.riskFlags)}'),
        ],
        if (candidate.gatingNotes.isNotEmpty) ...[
          const SizedBox(height: 8),
          _StateLine(text: 'gating_notes: ${_joinList(candidate.gatingNotes)}'),
        ],
      ]),
    );
  }
}

class _RetryLine extends StatelessWidget {
  const _RetryLine({required this.text, required this.onRetry});

  final String text;
  final Future<ActionResult> Function()? onRetry;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.redAccent.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.redAccent.withValues(alpha: 0.20)),
      ),
      child: Wrap(
        spacing: 8,
        runSpacing: 6,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          Text(text, style: const TextStyle(color: Colors.redAccent)),
          TextButton.icon(
            onPressed: onRetry == null
                ? null
                : () async {
                    final result = await onRetry!();
                    if (!context.mounted) return;
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                      content: Text(result.message),
                      backgroundColor:
                          result.success ? Colors.green : Colors.redAccent,
                    ));
                  },
            icon: const Icon(Icons.refresh, size: 16),
            label: const Text('Retry'),
          ),
        ],
      ),
    );
  }
}

class _KisAutoSimulatorPanel extends StatelessWidget {
  const _KisAutoSimulatorPanel({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final result = controller.kisAutoSimulatorResult;
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
          const Icon(Icons.science_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text('KIS Auto Simulator',
                style: Theme.of(context).textTheme.titleSmall),
          ),
          const _SoftBadge(text: 'Dry-run only', color: Colors.greenAccent),
        ]),
        const SizedBox(height: 10),
        FilledButton.icon(
          onPressed: controller.kisAutoSimulatorLoading
              ? null
              : () async {
                  final actionResult = await controller.runKisDryRunAuto();
                  if (!context.mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(actionResult.message),
                    backgroundColor:
                        actionResult.success ? Colors.green : Colors.redAccent,
                  ));
                },
          icon: controller.kisAutoSimulatorLoading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.play_circle_outline),
          label: Text(controller.kisAutoSimulatorLoading
              ? 'Running KIS dry-run...'
              : 'Run KIS Dry-Run Auto'),
        ),
        if (controller.kisAutoSimulatorError != null) ...[
          const SizedBox(height: 10),
          _StateLine(
              text: _primaryLine(controller.kisAutoSimulatorError!),
              color: Colors.redAccent),
        ],
        if (result != null) ...[
          const SizedBox(height: 10),
          _KisAutoSimulatorResultPanel(result: result),
        ],
      ]),
    );
  }
}

class _KisAutoSimulatorResultPanel extends StatelessWidget {
  const _KisAutoSimulatorResultPanel({required this.result});

  final KisAutoSimulatorResult result;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Wrap(spacing: 8, runSpacing: 8, children: [
        const _SoftBadge(
            text: 'real_order_submitted=false', color: Colors.lightBlueAccent),
        _SoftBadge(
          text: result.result.isEmpty ? 'skipped' : result.result,
          color:
              result.orderId == null ? Colors.amberAccent : Colors.greenAccent,
        ),
      ]),
      const SizedBox(height: 10),
      Wrap(spacing: 14, runSpacing: 8, children: [
        _ResultPair(label: 'Action', value: result.action.toUpperCase()),
        _ResultPair(label: 'Result', value: result.result),
        _ResultPair(label: 'Symbol', value: result.triggeredSymbol ?? 'n/a'),
        _ResultPair(
            label: 'Signal', value: result.signalId?.toString() ?? 'n/a'),
        _ResultPair(
            label: 'Sim Order', value: result.orderId?.toString() ?? 'n/a'),
        _ResultPair(label: 'Quant', value: _score(result.quantBuyScore)),
        _ResultPair(label: 'GPT', value: _gptScore(result)),
        _ResultPair(label: 'Final', value: _score(result.finalEntryScore)),
      ]),
      if (result.reason.isNotEmpty) ...[
        const SizedBox(height: 8),
        _StateLine(text: result.reason),
      ],
    ]);
  }
}

class _ResultPair extends StatelessWidget {
  const _ResultPair({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(label.toUpperCase(),
          style: const TextStyle(
              color: Colors.white38,
              fontSize: 10,
              fontWeight: FontWeight.w700)),
      const SizedBox(height: 3),
      Text(value,
          style: const TextStyle(
              color: Colors.white70, fontWeight: FontWeight.w700)),
    ]);
  }
}

class _WatchlistSymbols extends StatelessWidget {
  const _WatchlistSymbols({required this.watchlist, required this.isKr});

  final MarketWatchlist watchlist;
  final bool isKr;

  @override
  Widget build(BuildContext context) {
    final visible = watchlist.symbols.take(isKr ? 8 : 16).toList();
    return Wrap(spacing: 8, runSpacing: 8, children: [
      for (final item in visible) _SymbolChip(item: item, isKr: isKr),
    ]);
  }
}

class _SymbolChip extends StatelessWidget {
  const _SymbolChip({required this.item, required this.isKr});

  final WatchlistSymbol item;
  final bool isKr;

  @override
  Widget build(BuildContext context) {
    final marketLabel = item.marketLabel.isNotEmpty
        ? item.marketLabel
        : _marketCodeLabel(item.market);
    final companyName = _firstText([item.companyName, item.name]);
    final hasCompanyName = companyName.isNotEmpty && companyName != item.symbol;
    final label = isKr && hasCompanyName
        ? '${item.symbol} - $companyName - $marketLabel'
        : hasCompanyName
            ? '${item.symbol} - $companyName'
            : item.symbol;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Text(label,
          style: const TextStyle(
              color: Colors.white70, fontWeight: FontWeight.w700)),
    );
  }
}

String _watchlistGroupLabel(Map<String, dynamic> payload) {
  final direct = payload['group_label']?.toString().trim();
  if (direct != null && direct.isNotEmpty) return direct;
  final mode = payload['mode']?.toString().trim();
  if (mode != null && mode.contains('balanced')) {
    return '코스피 Top 30 + 코스닥 Top 20';
  }
  final sourceLabel = _displayMarketLabel(payload);
  return sourceLabel.isEmpty ? 'Watchlist Update' : '$sourceLabel Top 50';
}

String _displayMarketLabel(Map<String, dynamic> payload) {
  final direct = payload['market_label']?.toString().trim();
  if (direct != null && direct.isNotEmpty) return direct;
  final source = payload['source_market_label']?.toString().trim();
  if (source != null && source.isNotEmpty) return source;
  final market = payload['market'] ?? payload['source_market'];
  return _marketCodeLabel(market?.toString() ?? '');
}

String _marketCodeLabel(String value) {
  switch (value.trim().toUpperCase()) {
    case 'KOSPI':
      return '코스피';
    case 'KOSDAQ':
      return '코스닥';
    case 'KONEX':
      return '코넥스';
    case 'KR':
      return '한국';
    case 'US':
      return '미국';
    default:
      return value;
  }
}

String _groupCountLabel(Map<String, dynamic> group) {
  final label = _displayMarketLabel(group);
  final count = _intFromPayload(group, 'count');
  final target = _intFromPayload(group, 'target_count');
  if (count != null && target != null) return '$label $count / $target';
  if (count != null) return '$label $count';
  return label.isEmpty ? 'Group' : label;
}

int? _intFromPayload(Map<String, dynamic> payload, String key) {
  final value = payload[key];
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '');
}

List<Map<String, dynamic>> _listFromPayload(
  Map<String, dynamic> payload,
  String key,
) {
  final raw = payload[key];
  if (raw is! List) return const [];
  return [
    for (final item in raw)
      if (item is Map) Map<String, dynamic>.from(item.cast<String, dynamic>()),
  ];
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

BoxDecoration _panelDecoration() {
  return BoxDecoration(
    color: Colors.black.withValues(alpha: 0.18),
    borderRadius: BorderRadius.circular(8),
    border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
  );
}

Candidate? _topWatchlistCandidate(WatchlistRunResult result) {
  final candidates = _candidatePreviewList(result);
  if (candidates.isNotEmpty) return candidates.first;
  return null;
}

List<Candidate> _candidatePreviewList(WatchlistRunResult result) {
  final seen = <String>{};
  final candidates = <Candidate>[];
  void addAll(List<Candidate> values) {
    for (final candidate in values) {
      final key = candidate.symbol.trim().toUpperCase();
      if (key.isEmpty || seen.contains(key)) continue;
      seen.add(key);
      candidates.add(candidate);
    }
  }

  addAll(result.finalRankedCandidates);
  addAll(result.researchedCandidates);
  addAll(result.topQuantCandidates);
  return candidates;
}

double? _candidatePrimaryScore(Candidate? candidate) {
  return candidate?.finalEntryScore ??
      candidate?.entryScore ??
      candidate?.finalBuyScore ??
      candidate?.finalScore ??
      candidate?.buyScore ??
      (candidate?.score == null ? null : candidate!.score!.toDouble());
}

double? _candidateBuyScore(Candidate? candidate) {
  return candidate?.finalBuyScore ??
      candidate?.finalEntryScore ??
      candidate?.entryScore ??
      candidate?.buyScore ??
      candidate?.finalScore ??
      (candidate?.score == null ? null : candidate!.score!.toDouble());
}

double? _candidateSellScore(Candidate? candidate) {
  return candidate?.finalSellScore ??
      candidate?.sellScore ??
      candidate?.quantSellScore ??
      candidate?.aiSellScore;
}

double? _candidateRequiredScore(Candidate candidate, int? fallbackThreshold) {
  return candidate.effectiveMinEntryScore ??
      (fallbackThreshold == null ? null : fallbackThreshold.toDouble());
}

String _candidateCompanyLabel(Candidate candidate) {
  final name = candidate.name.trim();
  if (name.isEmpty || name.toLowerCase() == 'null') return 'Unknown company';
  return name;
}

String _candidateMarketProviderLabel(
  Candidate candidate, {
  required bool isKr,
}) {
  final provider = presentation.displayText(
    candidate.provider,
    fallback: isKr ? 'KIS' : 'Alpaca',
  );
  final rawMarket = presentation.displayText(
    candidate.marketLabel.isNotEmpty ? candidate.marketLabel : candidate.market,
    fallback: isKr ? 'KR' : 'US',
  );
  final market = _marketCodeLabel(rawMarket);
  return '${_providerLabel(provider)} / $market';
}

String _providerLabel(String value) {
  final normalized = value.trim().toLowerCase();
  if (normalized == 'kis') return 'KIS';
  if (normalized == 'alpaca') return 'Alpaca';
  return value;
}

String _candidateActionStatus(Candidate candidate) {
  final hint = candidate.actionHint.trim();
  if (candidate.entryReady) return 'Ready';
  if (hint.isNotEmpty) return _titleCaseWords(hint.replaceAll('_', ' '));
  final action = candidate.action.trim();
  if (action.isNotEmpty) return _titleCaseWords(action.replaceAll('_', ' '));
  return 'Watch';
}

({String label, Color color}) _candidateTradability(
  Candidate candidate, {
  required bool isKr,
}) {
  if (candidate.tradeAllowed == true) {
    return (label: 'Tradable', color: Colors.greenAccent);
  }
  if (candidate.entryReady) {
    return (
      label: isKr ? 'Preview ready' : 'Ready',
      color: Colors.greenAccent,
    );
  }
  if (_entryBlockedByGptOrRisk(candidate)) {
    return (label: 'Blocked', color: Colors.redAccent);
  }
  return (label: 'Blocked', color: Colors.amberAccent);
}

String _candidateDisplayReason(Candidate candidate) {
  return presentation.translateReason(
    _firstText([
      candidate.blockReason,
      candidate.blockReasons.isEmpty ? null : candidate.blockReasons.join(', '),
      candidate.skipReason,
      candidate.noOrderReason,
      candidate.reason,
    ]),
    entryPenalty: candidate.entryPenalty ?? candidate.gptContext.entryPenalty,
  );
}

List<String> _candidateTranslatedNotes(List<String> values) {
  final result = <String>[];
  for (final value in values) {
    final translated = presentation.translateReason(value);
    if (translated != 'Not available' && !result.contains(translated)) {
      result.add(translated);
    }
  }
  return result;
}

String _candidatePriceLabel(Candidate candidate) {
  final value = candidate.currentPrice;
  if (value == null) return 'Price unavailable';
  final currency = candidate.currency.trim().toUpperCase();
  if (currency == 'KRW' || RegExp(r'^\d{6}$').hasMatch(candidate.symbol)) {
    return _formatKrw(value);
  }
  final decimals = value >= 100 ? 2 : 4;
  return '\$${value.toStringAsFixed(decimals)}';
}

String _candidateIndicatorLabel(
  Candidate candidate,
  List<String> keys, {
  bool percentLike = false,
}) {
  for (final key in keys) {
    final value = candidate.indicatorPayload[key];
    final text = value?.toString().trim();
    if (text == null || text.isEmpty || text == 'null') continue;
    final numeric = double.tryParse(text.replaceAll(',', ''));
    if (numeric == null) return text;
    if (percentLike && numeric.abs() < 1) {
      return '${(numeric * 100).toStringAsFixed(2)}%';
    }
    return _displayNumber(numeric);
  }
  return 'Not available';
}

String _watchlistOrderStatus(String? orderId, {required bool isKr}) {
  if (orderId != null && orderId.trim().isNotEmpty) {
    return isKr ? 'KIS order reference $orderId' : 'Paper order created';
  }
  return isKr ? 'Preview only, no real order' : 'No order created';
}

String _watchlistNextAction(
  Candidate? candidate,
  WatchlistRunResult result, {
  required bool isKr,
}) {
  if (candidate == null) return 'Review again next scan';
  if (isKr) {
    return candidate.entryReady ? 'Prepare manual ticket' : 'Keep on watchlist';
  }
  if (candidate.entryReady && result.shouldTrade) {
    return 'Review risk gates before paper order follow-up';
  }
  return 'Review again next scan';
}

String _watchlistDecision(Candidate? candidate, WatchlistRunResult result) {
  final action = result.action.trim().toLowerCase();
  if (candidate == null) return 'NO TRADE';
  if (candidate.entryReady || action == 'buy') return 'BUY CANDIDATE';
  if (action == 'watch' || candidate.actionHint.toLowerCase() == 'watch') {
    return 'WATCH';
  }
  return 'HOLD';
}

String _watchlistResultLabel(String status, {required bool isKr}) {
  final normalized = status.trim().toLowerCase();
  if (isKr && (normalized.isEmpty || normalized == 'run completed')) {
    return 'Preview only';
  }
  if (normalized.contains('block')) return 'Blocked';
  if (normalized.contains('skip')) return 'Skipped';
  if (normalized.contains('preview')) return 'Preview only';
  if (normalized.contains('hold')) return 'Hold';
  if (normalized.contains('complete') || normalized.contains('success')) {
    return 'Completed';
  }
  if (normalized.isEmpty) return 'Completed';
  return presentation.translateReason(status);
}

String _candidateStatusLabel(Candidate candidate, {required bool isKr}) {
  if (candidate.previewOnly == true || isKr) return 'Preview only';
  if (_entryBlockedByGptOrRisk(candidate)) return 'Blocked';
  if (candidate.entryReady) return 'Ready';
  if (candidate.actionHint.toLowerCase() == 'watch') return 'Watch';
  return 'Not ready';
}

Color _candidateStatusColor(String label) {
  final normalized = label.toLowerCase();
  if (normalized.contains('ready')) return Colors.greenAccent;
  if (normalized.contains('preview')) return Colors.lightBlueAccent;
  if (normalized.contains('block')) return Colors.redAccent;
  if (normalized.contains('watch')) return Colors.amberAccent;
  return Colors.white70;
}

String _candidateNextAction(Candidate candidate, {required bool isKr}) {
  if (isKr) {
    return candidate.entryReady ? 'Prepare manual ticket' : 'Keep on watchlist';
  }
  return candidate.entryReady
      ? 'Review risk gates before paper order follow-up'
      : 'Review again next scan';
}

List<String> _candidateRiskNotes(Candidate? candidate) {
  if (candidate == null) return const [];
  final notes = <String>[];
  for (final value in [
    ...candidate.riskFlags,
    ...candidate.gatingNotes,
    ...candidate.blockReasons,
  ]) {
    final text = presentation.translateReason(value,
        entryPenalty:
            candidate.entryPenalty ?? candidate.gptContext.entryPenalty);
    if (text != 'Not available' && !notes.contains(text)) notes.add(text);
    if (notes.length >= 3) break;
  }
  return notes;
}

class _CountPill extends StatelessWidget {
  const _CountPill({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 6),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.07),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
      ),
      child: Text(text,
          style: const TextStyle(
              color: Colors.white70,
              fontSize: 11,
              fontWeight: FontWeight.w700)),
    );
  }
}

Future<void> _runSingleSymbolAnalyzeBuy(
  BuildContext context,
  DashboardController controller,
) async {
  final symbol = controller.kisGuardedRunSymbol.trim().toUpperCase();
  final quantity = int.tryParse(controller.orderTicketQtyInput.trim());
  if (symbol.isEmpty || quantity == null || quantity <= 0) {
    _showDashboardSnack(
      context,
      const ActionResult(
        success: false,
        message: 'Enter a KR symbol and positive quantity.',
      ),
    );
    return;
  }

  final confirmed = await showDialog<bool>(
    context: context,
    builder: (dialogContext) => AlertDialog(
      title: const Text('Analyze Symbol & Buy'),
      content: Text(
        'Analyze only $symbol and submit only if every KIS guarded safety gate passes.',
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(dialogContext).pop(false),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: () => Navigator.of(dialogContext).pop(true),
          child: const Text('Confirm Analyze & Buy'),
        ),
      ],
    ),
  );
  if (confirmed != true || !context.mounted) return;

  final actionResult = await controller.runKisSingleSymbolAnalyzeBuy(
    symbol: symbol,
    quantity: quantity,
    gateLevel: controller.selectedGateLevel,
    confirmLive: true,
  );
  if (!context.mounted) return;
  _showDashboardSnack(context, actionResult);
}

void _showDashboardSnack(BuildContext context, ActionResult result) {
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
    content: Text(result.message),
    backgroundColor: result.success ? Colors.green : Colors.redAccent,
  ));
}

String _limitedBuyCandidateLabel(KisLimitedAutoBuy? result) {
  if (result == null) return 'not_run';
  final candidate = result.finalCandidate;
  final symbol = candidate?.symbol ?? result.symbol;
  if (symbol == null || symbol.trim().isEmpty) return 'none';
  final company = candidate?.companyName;
  if (company == null || company.trim().isEmpty) return symbol;
  return '$symbol / $company';
}

String _limitedBuyPrimaryReason(KisLimitedAutoBuy? result) {
  if (result == null) return 'not_run';
  final reason = result.primaryBlockReason ??
      (result.blockReasons.isNotEmpty ? result.blockReasons.first : null) ??
      result.reason;
  final trimmed = reason.trim();
  return trimmed.isEmpty ? 'n/a' : trimmed;
}

String _limitedBuyCashLabel(KisLimitedAutoBuy? result) {
  if (result == null) return 'n/a';
  final candidate = result.finalCandidate;
  final cashSufficient = candidate?.cashSufficient;
  final available = candidate?.availableCash ?? result.cashAvailable;
  final notional = candidate?.estimatedNotional ?? result.notional;
  final status = cashSufficient == null ? 'unknown' : _yesNo(cashSufficient);
  return '$status / ${_formatReviewKrwOrDash(notional)} <= ${_formatReviewKrwOrDash(available)}';
}

String _limitedBuyDuplicateLabel(KisLimitedAutoBuy? result) {
  if (result == null) return 'n/a';
  final candidate = result.finalCandidate;
  if (candidate == null) return 'not checked';
  if (candidate.duplicatePosition) return 'blocked: held position';
  if (candidate.duplicateOpenOrder) return 'blocked: open buy order';
  return 'clear';
}

String _singleSymbolCashLabel(KisSingleSymbolTradingResult? result) {
  if (result == null) return 'n/a';
  final shortfall = result.cashShortfall;
  if (shortfall != null) {
    return 'short ${_formatReviewKrwOrDash(shortfall)}';
  }
  return '${_formatReviewKrwOrDash(result.estimatedOrderAmount)} <= ${_formatReviewKrwOrDash(result.availableCash)}';
}

String _singleSymbolNoBuyReason(KisSingleSymbolTradingResult? result) {
  if (result == null) return 'not_run';
  final reason =
      result.noOrderReason ?? result.blockReason ?? result.reason.trim();
  if (reason.isEmpty) return result.action;
  return reason;
}

String _orderSubmissionLabel({
  required bool brokerSubmitCalled,
  required bool manualSubmitCalled,
  required bool realOrderSubmitted,
}) {
  return 'Broker submit: ${_yesNo(brokerSubmitCalled)} / Manual submit: ${_yesNo(manualSubmitCalled)} / Real order: ${_yesNo(realOrderSubmitted)}';
}

String _latestSchedulerRunLabel(KisSchedulerReadiness? readiness) {
  final run = readiness?.recentRuns.isEmpty == false
      ? readiness!.recentRuns.first
      : null;
  if (run == null) return 'not_loaded';
  return '${run.mode} / ${run.result}';
}

Color _managedPositionStatusColor(ManagedPosition position) {
  if (position.isSellReady) return Colors.redAccent;
  if (position.isReviewSell) return Colors.amberAccent;
  return Colors.greenAccent;
}

String _score(double? value) {
  if (value == null) return '--';
  return value.toStringAsFixed(value.truncateToDouble() == value ? 0 : 1);
}

String _displayNumber(double? value) {
  if (value == null) return '--';
  return value.toStringAsFixed(value.truncateToDouble() == value ? 0 : 2);
}

String _numericGptScoreLabel(double? value) {
  if (value == null) return 'No numeric GPT score returned';
  return _displayNumber(value);
}

bool _entryBlockedByGptOrRisk(Candidate? candidate) {
  if (candidate == null) return false;
  final penalty = candidate.entryPenalty ?? candidate.gptContext.entryPenalty;
  return candidate.hardBlocked ||
      candidate.hardBlockNewBuy ||
      candidate.gptContext.hardBlockNewBuy ||
      (penalty != null && penalty >= 900);
}

String _gptAdvisoryReason(Candidate? candidate) {
  return _firstText([
    candidate?.gptContext.reason,
    candidate?.marketResearchReason,
    candidate?.gptReason,
  ]);
}

String _firstText(List<String?> values) {
  for (final value in values) {
    final text = value?.trim();
    if (text != null && text.isNotEmpty && text != 'null') return text;
  }
  return '';
}

String _boolText(bool value) => value ? 'true' : 'false';

Color _opsStatusColor(String value) {
  final normalized = value.trim().toUpperCase();
  if (normalized == 'PASS' ||
      normalized == 'SAFE_DRY_RUN' ||
      normalized == 'LIVE_READY') {
    return Colors.greenAccent;
  }
  if (normalized == 'WARN' || normalized == 'REVIEW_REQUIRED') {
    return Colors.amberAccent;
  }
  if (normalized == 'FAIL' ||
      normalized == 'BLOCKED' ||
      normalized == 'LIVE_ENABLED') {
    return Colors.redAccent;
  }
  return Colors.lightBlueAccent;
}

String _nullableBoolText(bool? value) {
  if (value == null) return 'n/a';
  return _boolText(value);
}

String _yesNo(bool value) => value ? 'Yes' : 'No';

String _nullableYesNo(bool? value) {
  if (value == null) return 'Unknown';
  return _yesNo(value);
}

String _titleCaseWords(String value) {
  final words = value
      .trim()
      .split(RegExp(r'\s+'))
      .where((word) => word.trim().isNotEmpty)
      .toList();
  if (words.isEmpty) return value;
  return words
      .map((word) => word.length == 1
          ? word.toUpperCase()
          : '${word[0].toUpperCase()}${word.substring(1).toLowerCase()}')
      .join(' ');
}

String _qtyText(double? value) {
  if (value == null) return 'n/a';
  return value.truncateToDouble() == value
      ? value.toStringAsFixed(0)
      : value.toStringAsFixed(2);
}

String _formatKrw(double? value) {
  if (value == null) return 'n/a';
  final sign = value < 0 ? '-' : '';
  final rounded = value.abs().round().toString();
  final buffer = StringBuffer();
  for (var index = 0; index < rounded.length; index += 1) {
    final remaining = rounded.length - index;
    buffer.write(rounded[index]);
    if (remaining > 1 && remaining % 3 == 1) {
      buffer.write(',');
    }
  }
  return '${sign}₩${buffer.toString()}';
}

String _formatKrwOrDash(double? value) {
  if (value == null) return '--';
  return _formatKrw(value);
}

String _formatPercentFromDecimal(double? value) {
  if (value == null) return 'n/a';
  return _formatPercentValue(value * 100, signed: true);
}

String _limitedAutoSellBrokerBadge(KisLimitedAutoSell? result) {
  if (result?.brokerSubmitActuallyCalled == true) {
    return 'BROKER SUBMIT CALLED';
  }
  return 'NO BROKER SUBMIT';
}

List<String> _limitedAutoSellLabels(KisLimitedAutoSell result) {
  final brokerBadge = _limitedAutoSellBrokerBadge(result);
  final labels = <String>[];
  void add(String label) {
    final normalized = label.trim();
    if (normalized.isEmpty) return;
    if (normalized == 'NO BROKER SUBMIT' && brokerBadge != normalized) return;
    if (normalized == 'BROKER SUBMIT CALLED' && brokerBadge != normalized) {
      return;
    }
    if (!labels.contains(normalized)) labels.add(normalized);
  }

  add('STOP-LOSS EXECUTION');
  add('TAKE-PROFIT GUARDED EXECUTION');
  add('TAKE-PROFIT DEFAULT OFF');
  add('GUARDED EXECUTION');
  add('AUTO BUY DISABLED');
  add('SCHEDULER REAL ORDERS DISABLED');
  add(brokerBadge);
  for (final label in result.readinessLabels) {
    add(label);
  }
  return labels;
}

String _limitedAutoSellSupportedTriggerLabel(KisLimitedAutoSell result) {
  final value = result.rawPayload['supported_triggers'];
  if (value is! Map) return 'n/a';
  String modeFor(String trigger) {
    final item = value[trigger];
    if (item is Map && item['mode'] != null) {
      return item['mode'].toString();
    }
    return 'unknown';
  }

  return 'stop_loss: ${modeFor('stop_loss')} / take_profit: ${modeFor('take_profit')}';
}

String _limitedAutoSellDailyLimitLabel(KisLimitedAutoSell result) {
  final remaining = result.dailyLimitRemaining ??
      result.dailyLimitInt('daily_limit_remaining');
  final maxOrders = result.dailyLimitInt('max_orders_per_day') ??
      result.safetyInt('max_orders_per_day');
  final submitted = result.dailyLimitInt('submitted_count_today');
  final base =
      '${remaining?.toString() ?? 'n/a'} remaining / ${maxOrders?.toString() ?? 'n/a'} max';
  if (submitted == null) return base;
  return '$base, $submitted used';
}

String _limitedAutoSellDuplicateLabel(KisLimitedAutoSell result) {
  final duplicate = result.duplicateOrderFlag('duplicate_open_sell_order') ||
      (result.finalCandidate?.latestOrder.isNotEmpty ?? false);
  if (duplicate) return 'blocked: duplicate open sell';
  return 'clear';
}

String _limitedBuyReviewTopReason(KisLimitedAutoBuyReview review) {
  if (review.topBlockReasons.isEmpty) return 'n/a';
  final top = review.topBlockReasons.first;
  return '${top.label} (${top.count})';
}

String _limitedBuyExecutionTopReason(KisLimitedAutoBuyExecutionReview review) {
  if (review.topBlockReasons.isEmpty) return 'n/a';
  final top = review.topBlockReasons.first;
  return '${top.label} (${top.count})';
}

String _auditSnapshotLabel(Map<String, dynamic> value) {
  if (value.isEmpty) return 'n/a';
  final parts = <String>[];
  for (final key in value.keys.take(4)) {
    final item = value[key];
    if (item == null || item.toString() == 'null') continue;
    parts.add('$key=$item');
  }
  return parts.isEmpty ? 'n/a' : parts.join(', ');
}

String _reviewCandidateLabel(String? symbol, String? companyName) {
  final safeSymbol = symbol?.trim();
  final safeCompany = companyName?.trim();
  if (safeSymbol == null || safeSymbol.isEmpty) return 'n/a';
  if (safeCompany == null || safeCompany.isEmpty) return safeSymbol;
  return '$safeSymbol · $safeCompany';
}

Color _reviewStatusColor(String status) {
  final normalized = status.trim().toUpperCase();
  if (normalized == 'SUBMITTED') return Colors.greenAccent;
  if (normalized == 'BUY_READY') return Colors.greenAccent;
  if (normalized == 'WATCH') return Colors.lightBlueAccent;
  if (normalized == 'BLOCKED') return Colors.amberAccent;
  return Colors.white70;
}

String _formatSafePlPercent(KisLiveExitCandidate candidate) {
  if (!candidate.hasSafePlPct) return '--';
  return _formatPercentFromDecimal(candidate.unrealizedPlPct);
}

String _formatShadowPlPercent(KisExitShadowCandidate candidate) {
  if (!candidate.hasSafePlPct) return '--';
  return _formatPercentFromDecimal(candidate.unrealizedPlPct);
}

String _formatReviewPlPercent(KisShadowExitReviewDecision decision) {
  if (decision.unrealizedPlPct == null) return '--';
  return _formatPercentFromDecimal(decision.unrealizedPlPct);
}

String _formatQueuePlPercent(KisShadowExitReviewQueueItem item) {
  if (item.latestUnrealizedPlPct == null) return '--';
  return _formatPercentFromDecimal(item.latestUnrealizedPlPct);
}

String _formatThresholdPct(double? value) {
  if (value == null) return 'n/a';
  return _formatPercentValue(value);
}

String _autoSellStatusLabel(String value) {
  final normalized = value.trim().toUpperCase().replaceAll('_', ' ');
  if (normalized == 'TAKE PROFIT READY') return 'TAKE PROFIT READY';
  if (normalized == 'REVIEW SELL') return 'REVIEW SELL';
  if (normalized == 'SELL READY') return 'SELL READY';
  if (normalized == 'HOLD') return 'HOLD';
  return normalized.isEmpty ? 'HOLD' : normalized;
}

String _autoSellTriggerBadgeLabel(KisLimitedAutoSellCandidate candidate) {
  if (candidate.stopLossTriggered) return 'STOP-LOSS READY';
  if (candidate.takeProfitTriggered) return 'TAKE-PROFIT READY';
  return _autoSellStatusLabel(candidate.status);
}

Color _autoSellStatusColor(String value) {
  final normalized = value.trim().toUpperCase();
  if (normalized == 'SELL_READY') return Colors.greenAccent;
  if (normalized == 'TAKE_PROFIT_READY') return Colors.lightBlueAccent;
  if (normalized == 'REVIEW_SELL') return Colors.amberAccent;
  return Colors.white70;
}

String _prettyJson(Map<String, dynamic> payload) {
  if (payload.isEmpty) return '{}';
  return const JsonEncoder.withIndent('  ').convert(payload);
}

String _formatReviewKrwOrDash(double? value) {
  if (value == null) return '--';
  final sign = value < 0 ? '-' : '';
  final rounded = value.abs().round().toString();
  final buffer = StringBuffer();
  for (var index = 0; index < rounded.length; index += 1) {
    final remaining = rounded.length - index;
    buffer.write(rounded[index]);
    if (remaining > 1 && remaining % 3 == 1) {
      buffer.write(',');
    }
  }
  return 'KRW $sign${buffer.toString()}';
}

String _shadowDecisionLabel(String value) {
  final normalized = value.trim().toLowerCase();
  if (normalized == 'would_sell') return 'WOULD SELL';
  if (normalized == 'manual_review') return 'MANUAL REVIEW';
  return 'HOLD';
}

String _buyShadowDecisionLabel(String value) {
  final normalized = value.trim().toLowerCase();
  if (normalized == 'would_buy') return 'WOULD BUY';
  if (normalized == 'blocked') return 'BLOCKED';
  return 'HOLD';
}

String _queueStatusLabel(String value) {
  final normalized = value.trim().toLowerCase();
  if (normalized == 'reviewed') return 'REVIEWED';
  if (normalized == 'dismissed') return 'DISMISSED';
  return 'OPEN';
}

Color _queueStatusColor(String value) {
  final normalized = value.trim().toLowerCase();
  if (normalized == 'reviewed') return Colors.greenAccent;
  if (normalized == 'dismissed') return Colors.white54;
  return Colors.lightBlueAccent;
}

String _formatPercentValue(double? value, {bool signed = false}) {
  if (value == null) return 'n/a';
  final sign = signed && value > 0 ? '+' : '';
  return '$sign${value.toStringAsFixed(2)}%';
}

String _formatRate(double value) {
  return _formatPercentValue(value * 100);
}

String _joinList(List<String> values) {
  final items = values.where((item) => item.trim().isNotEmpty).toList();
  return items.isEmpty ? 'n/a' : items.join(', ');
}

// ignore: unused_element
bool _isKisPreviewCandidate(Candidate candidate) {
  final market = candidate.market.trim().toUpperCase();
  return candidate.currency.trim().toUpperCase() == 'KRW' ||
      market == 'KR' ||
      market == 'KOSPI' ||
      market == 'KOSDAQ' ||
      candidate.riskFlags.contains('kr_trading_disabled') ||
      candidate.riskFlags.contains('preview_only');
}

String _eventRiskLabel(Map<String, dynamic>? value) {
  if (value == null || value.isEmpty) return 'n/a';
  final riskLevel = value['risk_level']?.toString();
  final eventType = value['event_type']?.toString();
  if (riskLevel == null || riskLevel.isEmpty) return 'n/a';
  if (eventType == null || eventType.isEmpty || eventType == 'null') {
    return riskLevel;
  }
  return '$riskLevel / $eventType';
}

String _gptScore(KisAutoSimulatorResult result) {
  if (result.aiBuyScore != null) return _score(result.aiBuyScore);
  if (result.confidence != null) {
    return 'conf ${result.confidence!.toStringAsFixed(2)}';
  }
  return 'n/a';
}

String _primaryLine(String value) {
  final lines = value
      .split(RegExp(r'[\r\n]+'))
      .map((line) => line.trim())
      .where((line) => line.isNotEmpty);
  return lines.isEmpty ? value.trim() : lines.first;
}
