import 'package:flutter/material.dart';

import '../../../core/utils/timestamp_formatter.dart';
import '../../../core/widgets/section_card.dart';
import '../../../models/candidate.dart';
import '../../../models/kis_auto_readiness.dart';
import '../../../models/kis_auto_simulator_result.dart';
import '../../../models/kis_buy_shadow_decision.dart';
import '../../../models/kis_exit_shadow_decision.dart';
import '../../../models/kis_limited_auto_buy.dart';
import '../../../models/kis_limited_auto_sell.dart';
import '../../../models/kis_shadow_exit_review.dart';
import '../../../models/kis_shadow_exit_review_queue.dart';
import '../../../models/kis_live_exit_preflight.dart';
import '../../../models/kis_scheduler_simulation.dart';
import '../../../models/kis_scheduler_live.dart';
import '../../../models/market_watchlist.dart';
import '../../../models/watchlist_run_result.dart';
import '../../dashboard/dashboard_controller.dart';

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
    final title = isKr ? 'KR new-buy scan / KIS' : 'US new-buy scan / Alpaca';
    final topCandidate = controller.hasLatestRunResult &&
            controller.runResult.finalRankedCandidates.isNotEmpty
        ? controller.runResult.finalRankedCandidates.first
        : null;

    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.manage_search_outlined, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text('New Buy Candidates',
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
            const _SoftBadge(
                text: 'PREVIEW ONLY', color: Colors.lightBlueAccent),
            const _SoftBadge(
                text: 'TRADING DISABLED', color: Colors.amberAccent),
            const _SoftBadge(text: 'NO AUTO ORDER', color: Colors.orangeAccent),
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
            label:
                Text(controller.runOnceLoading ? 'Scanning...' : 'Start Scan'),
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
            label:
                Text(controller.watchlistLoading ? 'Refreshing...' : 'Refresh'),
          ),
        ]),
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
        const SizedBox(height: 12),
        _TopCandidateCard(
          candidate: topCandidate,
          isKr: isKr,
          onPrepareBuyTicket: topCandidate == null || !isKr
              ? null
              : () {
                  controller.useKrCandidateInOrderTicket(topCandidate);
                  onOpenManualOrder?.call();
                  ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                    content: Text(
                        'Manual buy ticket prepared. Validate in Manual Order before submit.'),
                    backgroundColor: Colors.green,
                  ));
                },
        ),
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

class _WatchlistRunResultSummary extends StatelessWidget {
  const _WatchlistRunResultSummary({
    required this.runResult,
    required this.candidate,
    required this.isKr,
    required this.providerLabel,
    required this.marketLabel,
  });

  final WatchlistRunResult runResult;
  final Candidate? candidate;
  final bool isKr;
  final String providerLabel;
  final String marketLabel;

  @override
  Widget build(BuildContext context) {
    final status = _firstText([
      candidate?.result,
      candidate?.status,
      runResult.result,
      runResult.action,
      'run completed',
    ]);
    final reason = _firstText([
      runResult.reason,
      candidate?.noOrderReason,
      candidate?.skipReason,
      candidate?.reason,
      'No additional reason.',
    ]);
    final orderId =
        candidate?.orderId ?? candidate?.relatedOrderId ?? runResult.orderId;
    final orderStatus =
        orderId == null ? 'No order created' : 'Order ID $orderId';
    final topSymbol = candidate?.symbol.isNotEmpty == true
        ? candidate!.symbol
        : runResult.finalBestCandidate.isNotEmpty
            ? runResult.finalBestCandidate
            : 'No top candidate';
    final score =
        _displayNumber(_candidateEntryScore(candidate) ?? runResult.bestScore);
    final confidence = _displayNumber(candidate?.confidence);
    final readiness = candidate != null
        ? (candidate!.entryReady ? 'ready' : 'not ready')
        : runResult.finalEntryReady
            ? 'ready'
            : 'not ready';
    final nextAction = candidate?.entryReady == true
        ? 'Candidate is ready for review.'
        : candidate != null
            ? 'Review block reason before any order action.'
            : 'Run a watchlist scan for candidate ranking.';
    final blockReason = _notAvailable(_firstText([
      candidate?.blockReason,
      candidate?.blockReasons.isNotEmpty == true
          ? candidate!.blockReasons.join(', ')
          : null,
      candidate?.skipReason,
      candidate?.noOrderReason,
      runResult.triggerBlockReason,
      runResult.reason,
    ]));
    final noOrderReason = _notAvailable(_firstText([
      candidate?.noOrderReason,
      candidate?.skipReason,
      runResult.reason,
      runResult.triggerBlockReason,
    ]));
    final entryStatus = _entryStatus(candidate);
    final gptSummary = _gptAdvisoryReason(candidate);
    final previewCandidates =
        runResult.finalRankedCandidates.take(5).toList(growable: false);

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
            child: Text('Latest Watchlist Scan',
                style: Theme.of(context).textTheme.titleSmall),
          ),
          _SoftBadge(
            text: status.toUpperCase(),
            color: status.contains('skip') || status.contains('hold')
                ? Colors.amberAccent
                : Colors.lightBlueAccent,
          ),
        ]),
        const SizedBox(height: 10),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _ResultPair(label: 'Provider', value: providerLabel),
          _ResultPair(label: 'Market', value: marketLabel),
          _ResultPair(
              label: 'Analyzed',
              value:
                  '${runResult.analyzedSymbolCount}/${runResult.configuredSymbolCount}'),
          _ResultPair(label: 'Top candidate', value: topSymbol),
          _ResultPair(label: 'Run result', value: _notAvailable(status)),
          _ResultPair(
              label: 'Action',
              value: runResult.action.isEmpty ? 'hold' : runResult.action),
          _ResultPair(label: 'Order status', value: orderStatus),
          _ResultPair(label: 'Entry score', value: score),
          _ResultPair(
              label: 'Quant score',
              value: _displayNumber(_candidateQuantScore(candidate))),
          _ResultPair(
              label: 'Quant Buy',
              value: _displayNumber(candidate?.quantBuyScore)),
          _ResultPair(
              label: 'Quant Sell',
              value: _displayNumber(candidate?.quantSellScore)),
          _ResultPair(
              label: 'AI Buy', value: _displayNumber(candidate?.aiBuyScore)),
          _ResultPair(
              label: 'AI Sell', value: _displayNumber(candidate?.aiSellScore)),
          _ResultPair(label: 'Confidence', value: confidence),
          _ResultPair(label: 'Readiness', value: readiness),
          _ResultPair(label: 'Entry status', value: entryStatus),
          _ResultPair(label: 'Next action', value: nextAction),
          _ResultPair(
              label: 'Action hint',
              value: candidate?.actionHint ?? runResult.finalActionHint),
          _ResultPair(
              label: 'Trade allowed',
              value: _nullableBoolText(candidate?.tradeAllowed)),
          _ResultPair(
              label: 'Hard blocked',
              value: candidate?.hardBlocked == true ||
                      candidate?.hardBlockNewBuy == true
                  ? 'true'
                  : 'false'),
          _ResultPair(label: 'Block reason', value: blockReason),
          _ResultPair(label: 'No-order reason', value: noOrderReason),
          _ResultPair(
              label: 'GPT Numeric Buy',
              value: _numericGptScoreLabel(candidate?.gptBuyScore)),
          _ResultPair(
              label: 'GPT Numeric Sell',
              value: _numericGptScoreLabel(candidate?.gptSellScore)),
          _ResultPair(
              label: 'Final buy',
              value: _displayNumber(candidate?.finalBuyScore)),
          _ResultPair(
              label: 'Final sell',
              value: _displayNumber(candidate?.finalSellScore)),
        ]),
        const SizedBox(height: 10),
        _StateLine(text: 'Reason: $reason'),
        if (gptSummary.isNotEmpty) ...[
          const SizedBox(height: 10),
          _StateLine(text: 'GPT Advisory Reason: $gptSummary'),
        ],
        if (_hardBlockReason(candidate).isNotEmpty) ...[
          const SizedBox(height: 10),
          _StateLine(text: 'Hard block reason: ${_hardBlockReason(candidate)}'),
        ],
        if (previewCandidates.isNotEmpty) ...[
          const SizedBox(height: 10),
          _WatchlistCandidatePreview(candidates: previewCandidates),
        ],
        const SizedBox(height: 10),
        _StateLine(
          text: isKr
              ? 'KR preview results are read-only and do not submit live orders.'
              : 'US watchlist scan uses Alpaca paper mode; no live submit from Watchlist.',
          color: Colors.white70,
        ),
      ]),
    );
  }
}

class _WatchlistCandidatePreview extends StatelessWidget {
  const _WatchlistCandidatePreview({required this.candidates});

  final List<Candidate> candidates;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Top Watchlist Candidates',
          style: TextStyle(fontWeight: FontWeight.w700)),
      const SizedBox(height: 8),
      for (final candidate in candidates)
        Padding(
          padding: const EdgeInsets.only(bottom: 6),
          child: Wrap(spacing: 12, runSpacing: 6, children: [
            _ResultPair(label: 'Symbol', value: candidate.symbol),
            _ResultPair(
                label: 'Entry score',
                value: _displayNumber(_candidateEntryScore(candidate))),
            _ResultPair(label: 'Action hint', value: candidate.actionHint),
            _ResultPair(
                label: 'Block reason',
                value: _notAvailable(_firstText([
                  candidate.blockReason,
                  candidate.blockReasons.isEmpty
                      ? null
                      : candidate.blockReasons.join(', '),
                ]))),
          ]),
        ),
    ]);
  }
}

class TestLabSection extends StatelessWidget {
  const TestLabSection({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return Column(children: [
      SectionCard(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            const Icon(Icons.science_outlined, size: 20),
            const SizedBox(width: 8),
            Expanded(
              child: Text('Advanced Diagnostics',
                  style: Theme.of(context).textTheme.titleMedium),
            ),
          ]),
          const SizedBox(height: 8),
          const Wrap(spacing: 8, runSpacing: 8, children: [
            _SoftBadge(text: 'TEST', color: Colors.lightBlueAccent),
            _SoftBadge(text: 'SHADOW', color: Colors.greenAccent),
            _SoftBadge(text: 'DRY-RUN', color: Colors.amberAccent),
            _SoftBadge(text: 'READINESS ONLY', color: Colors.white70),
            _SoftBadge(text: 'NO BROKER SUBMIT', color: Colors.orangeAccent),
          ]),
          const SizedBox(height: 12),
          _TestLabActions(controller: controller),
        ]),
      ),
      const SizedBox(height: 12),
      _KisLiveAutoReadinessCard(controller: controller),
      const SizedBox(height: 12),
      _KisBuyShadowDecisionCard(controller: controller),
      const SizedBox(height: 12),
      _KisExitShadowDecisionCard(controller: controller),
      const SizedBox(height: 12),
      _KisSchedulerSimulationPanel(controller: controller),
      const SizedBox(height: 12),
      _KisAutoSimulatorPanel(controller: controller),
      const SizedBox(height: 12),
      _KisLimitedAutoBuyCard(controller: controller),
      const SizedBox(height: 12),
      _KisLimitedAutoSellCard(controller: controller),
      const SizedBox(height: 12),
      _KisSchedulerLiveAutomationCard(controller: controller),
      const SizedBox(height: 12),
      _KisLiveExitPreflightCard(controller: controller),
      const SizedBox(height: 12),
      _KisShadowExitReviewCard(controller: controller),
      const SizedBox(height: 12),
      _KisShadowExitReviewQueueCard(controller: controller),
    ]);
  }
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
    this.onPrepareBuyTicket,
  });

  final Candidate? candidate;
  final bool isKr;
  final VoidCallback? onPrepareBuyTicket;

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
    final blockReason = candidate.blockReason ??
        (candidate.blockReasons.isEmpty
            ? 'No block reason'
            : candidate.blockReasons.join(', '));
    final entryStatus = _entryStatus(candidate);
    final nextAction = candidate.entryReady
        ? (isKr
            ? 'Prepare a manual buy ticket, then validate on Manual Order.'
            : 'Review candidate before any trading action.')
        : 'Review block reason before preparing a ticket.';
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: _panelDecoration(),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Text(
              candidate.symbol,
              style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800),
            ),
          ),
          _SoftBadge(
            text: candidate.entryReady ? 'READY' : 'BLOCKED',
            color:
                candidate.entryReady ? Colors.greenAccent : Colors.amberAccent,
          ),
        ]),
        if (candidate.name.isNotEmpty) ...[
          const SizedBox(height: 2),
          Text(candidate.name, style: const TextStyle(color: Colors.white70)),
        ],
        const SizedBox(height: 10),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _ResultPair(
              label: 'entry score',
              value: _displayNumber(_candidateEntryScore(candidate))),
          _ResultPair(
              label: 'AI Buy', value: _displayNumber(candidate.aiBuyScore)),
          _ResultPair(
              label: 'AI Sell', value: _displayNumber(candidate.aiSellScore)),
          _ResultPair(label: 'confidence', value: _score(candidate.confidence)),
          _ResultPair(
              label: 'readiness',
              value: candidate.entryReady ? 'entry ready' : 'not ready'),
          _ResultPair(label: 'entry status', value: entryStatus),
          _ResultPair(label: 'next action', value: nextAction),
        ]),
        const SizedBox(height: 8),
        _StateLine(text: 'Block reason: $blockReason'),
        if (onPrepareBuyTicket != null) ...[
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: onPrepareBuyTicket,
            icon: const Icon(Icons.input, size: 18),
            label: const Text('Prepare Buy Ticket'),
          ),
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
        label: 'Run Limited Auto Sell Check',
        loading: controller.kisLimitedAutoSellLoading,
        run: controller.runKisLimitedAutoSellOnce,
      ),
      _LabAction(
        label: 'Run Scheduler Live Guarded Check',
        loading: controller.kisSchedulerLiveLoading,
        run: controller.runKisSchedulerLiveOnce,
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
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(text: 'SELL ONLY', color: Colors.greenAccent),
          _SoftBadge(text: 'DISABLED BY DEFAULT', color: Colors.amberAccent),
          _SoftBadge(text: 'STOP-LOSS ONLY', color: Colors.lightBlueAccent),
          _SoftBadge(text: 'NO AUTO BUY', color: Colors.orangeAccent),
          _SoftBadge(
              text: 'SCHEDULER REAL ORDERS DISABLED', color: Colors.redAccent),
          _SoftBadge(text: 'GUARDED EXECUTION', color: Colors.white70),
        ]),
        const SizedBox(height: 12),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _ResultPair(
              label: 'limited auto sell',
              value: _boolText(settings.kisLimitedAutoSellEnabled)),
          _ResultPair(
              label: 'stop-loss enabled',
              value: _boolText(settings.kisLimitedAutoSellStopLossEnabled)),
          _ResultPair(
              label: 'take-profit auto sell',
              value: _boolText(settings.kisLimitedAutoSellTakeProfitEnabled)),
          _ResultPair(
              label: 'queue review required',
              value: _boolText(settings.kisLimitedAutoSellRequiresQueueReview)),
          _ResultPair(
              label: 'max orders/day',
              value: settings.kisLimitedAutoSellMaxOrdersPerDay.toString()),
          _ResultPair(
              label: 'max notional pct',
              value: _formatPercentValue(
                  settings.kisLimitedAutoSellMaxNotionalPct * 100)),
          _ResultPair(
              label: 'min shadow occurrences',
              value:
                  settings.kisLimitedAutoSellMinShadowOccurrences.toString()),
        ]),
        const SizedBox(height: 12),
        FilledButton.icon(
          onPressed: controller.kisLimitedAutoSellLoading
              ? null
              : () async {
                  final actionResult =
                      await controller.runKisLimitedAutoSellOnce();
                  if (!context.mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(actionResult.message),
                    backgroundColor:
                        actionResult.success ? Colors.green : Colors.redAccent,
                  ));
                },
          icon: controller.kisLimitedAutoSellLoading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.play_arrow),
          label: Text(controller.kisLimitedAutoSellLoading
              ? 'Running limited auto sell...'
              : 'Run Limited Auto Sell Once'),
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
        _ResultPair(label: 'symbol', value: result.symbol ?? 'n/a'),
        _ResultPair(label: 'trigger', value: result.trigger ?? 'n/a'),
        _ResultPair(
            label: 'latest P/L',
            value:
                '${_formatReviewKrwOrDash(result.unrealizedPl)} / ${_formatLimitedAutoSellPlPercent(result)}'),
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
          _ResultPair(label: 'ODNO', value: result.kisOdno!),
      ]),
      if (result.blockedBy.isNotEmpty) ...[
        const SizedBox(height: 8),
        _StateLine(text: 'blocked_by: ${_joinList(result.blockedBy)}'),
      ],
      const SizedBox(height: 10),
      Wrap(spacing: 8, runSpacing: 8, children: [
        _SoftBadge(
          text:
              "limited_auto_sell_enabled=${_nullableBoolText(result.nullableCheck('kis_limited_auto_sell_enabled'))}",
          color: Colors.lightBlueAccent,
        ),
        _SoftBadge(
          text:
              "stop_loss_enabled=${_nullableBoolText(result.nullableCheck('kis_limited_auto_sell_stop_loss_enabled'))}",
          color: Colors.lightBlueAccent,
        ),
        _SoftBadge(
          text:
              "queue_review_required=${_nullableBoolText(result.nullableCheck('queue_review_required'))}",
          color: Colors.lightBlueAccent,
        ),
        _SoftBadge(
          text: 'auto_buy_enabled=${_boolText(result.autoBuyEnabled)}',
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
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(text: 'BUY ONLY', color: Colors.greenAccent),
          _SoftBadge(text: 'DISABLED BY DEFAULT', color: Colors.amberAccent),
          _SoftBadge(
              text: 'NO AUTO BUY UNLESS ENABLED',
              color: Colors.lightBlueAccent),
          _SoftBadge(text: 'RISK GATED', color: Colors.white70),
          _SoftBadge(text: 'POSITION CAPPED', color: Colors.orangeAccent),
          _SoftBadge(
              text: 'SCHEDULER REAL ORDERS DISABLED', color: Colors.redAccent),
        ]),
        const SizedBox(height: 12),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _ResultPair(
              label: 'limited auto buy',
              value: _boolText(settings.kisLimitedAutoBuyEnabled)),
          _ResultPair(
              label: 'min score',
              value: _score(settings.kisLimitedAutoBuyMinFinalScore)),
          _ResultPair(
              label: 'min confidence',
              value: _score(settings.kisLimitedAutoBuyMinConfidence)),
          _ResultPair(
              label: 'max orders/day',
              value: settings.kisLimitedAutoBuyMaxOrdersPerDay.toString()),
          _ResultPair(
              label: 'max notional pct',
              value: _formatPercentValue(
                  settings.kisLimitedAutoBuyMaxNotionalPct * 100)),
          _ResultPair(
              label: 'max positions',
              value: settings.kisLimitedAutoBuyMaxPositions.toString()),
          _ResultPair(
              label: 'block position exists',
              value:
                  _boolText(settings.kisLimitedAutoBuyBlockIfPositionExists)),
          _ResultPair(
              label: 'block open order',
              value:
                  _boolText(settings.kisLimitedAutoBuyBlockIfOpenOrderExists)),
          _ResultPair(
              label: 'no new entry after',
              value: settings.kisLimitedAutoBuyNoNewEntryAfter),
        ]),
        const SizedBox(height: 12),
        FilledButton.icon(
          onPressed: controller.kisLimitedAutoBuyLoading
              ? null
              : () async {
                  final actionResult =
                      await controller.runKisLimitedAutoBuyOnce();
                  if (!context.mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(actionResult.message),
                    backgroundColor:
                        actionResult.success ? Colors.green : Colors.redAccent,
                  ));
                },
          icon: controller.kisLimitedAutoBuyLoading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.play_arrow),
          label: Text(controller.kisLimitedAutoBuyLoading
              ? 'Running limited auto buy...'
              : 'Run Limited Auto Buy Once'),
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
                'No limited auto buy run yet. Default backend state blocks execution.',
          ),
        ] else ...[
          const SizedBox(height: 10),
          _KisLimitedAutoBuyResultPanel(result: result),
        ],
      ]),
    );
  }
}

class _KisLimitedAutoBuyResultPanel extends StatelessWidget {
  const _KisLimitedAutoBuyResultPanel({required this.result});

  final KisLimitedAutoBuy result;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      if (result.submitted) ...[
        _StateLine(
          text:
              'LIVE BUY SUBMITTED: order ${result.orderId ?? 'n/a'} / ODNO ${result.kisOdno ?? result.brokerOrderId ?? 'n/a'}',
          color: Colors.redAccent,
        ),
        const SizedBox(height: 10),
      ],
      Wrap(spacing: 14, runSpacing: 8, children: [
        _ResultPair(label: 'result', value: result.result),
        _ResultPair(label: 'action', value: result.action),
        _ResultPair(label: 'reason', value: result.reason),
        _ResultPair(label: 'symbol', value: result.symbol ?? 'n/a'),
        _ResultPair(
            label: 'quantity', value: result.quantity?.toString() ?? 'n/a'),
        _ResultPair(
            label: 'notional', value: _formatReviewKrwOrDash(result.notional)),
        _ResultPair(label: 'final score', value: _score(result.finalScore)),
        _ResultPair(label: 'confidence', value: _score(result.confidence)),
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
          _ResultPair(label: 'ODNO', value: result.kisOdno!),
      ]),
      if (result.blockedBy.isNotEmpty) ...[
        const SizedBox(height: 8),
        _StateLine(text: 'blocked_by: ${_joinList(result.blockedBy)}'),
      ],
      const SizedBox(height: 10),
      Wrap(spacing: 8, runSpacing: 8, children: [
        _SoftBadge(
          text:
              "limited_auto_buy_enabled=${_nullableBoolText(result.nullableCheck('kis_limited_auto_buy_enabled'))}",
          color: Colors.lightBlueAccent,
        ),
        _SoftBadge(
          text:
              "shadow_review_required=${_nullableBoolText(result.nullableCheck('shadow_review_required'))}",
          color: Colors.lightBlueAccent,
        ),
        _SoftBadge(
          text: 'auto_buy_enabled=${_boolText(result.autoBuyEnabled)}',
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
    final label = isKr && item.name.isNotEmpty
        ? '${item.symbol} - ${item.name} - ${item.market}'
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

double? _candidateEntryScore(Candidate? candidate) {
  return candidate?.entryScore ??
      candidate?.finalEntryScore ??
      candidate?.finalScore ??
      candidate?.finalBuyScore ??
      candidate?.buyScore ??
      (candidate?.score == null ? null : candidate!.score!.toDouble());
}

double? _candidateQuantScore(Candidate? candidate) {
  return candidate?.quantScore ?? candidate?.quantBuyScore;
}

bool _entryBlockedByGptOrRisk(Candidate? candidate) {
  if (candidate == null) return false;
  final penalty = candidate.entryPenalty ?? candidate.gptContext.entryPenalty;
  return candidate.hardBlocked ||
      candidate.hardBlockNewBuy ||
      candidate.gptContext.hardBlockNewBuy ||
      (penalty != null && penalty >= 900);
}

String _entryStatus(Candidate? candidate) {
  if (_entryBlockedByGptOrRisk(candidate)) {
    return 'Entry blocked by GPT/risk context';
  }
  if (candidate == null) return '--';
  return candidate.entryReady ? 'entry ready' : 'not ready';
}

String _gptAdvisoryReason(Candidate? candidate) {
  return _firstText([
    candidate?.gptContext.reason,
    candidate?.marketResearchReason,
    candidate?.gptReason,
  ]);
}

String _hardBlockReason(Candidate? candidate) {
  if (!_entryBlockedByGptOrRisk(candidate)) return '';
  return _firstText([
    candidate?.hardBlockReason,
    candidate?.gptContext.reason,
    candidate?.blockReason,
  ]);
}

String _firstText(List<String?> values) {
  for (final value in values) {
    final text = value?.trim();
    if (text != null && text.isNotEmpty && text != 'null') return text;
  }
  return '';
}

String _notAvailable(String value) {
  final text = value.trim();
  return text.isEmpty || text == 'null' ? 'Not available' : text;
}

String _boolText(bool value) => value ? 'true' : 'false';

String _nullableBoolText(bool? value) {
  if (value == null) return 'n/a';
  return _boolText(value);
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

String _formatLimitedAutoSellPlPercent(KisLimitedAutoSell result) {
  if (result.unrealizedPlPct == null) return '--';
  return _formatPercentFromDecimal(result.unrealizedPlPct);
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
