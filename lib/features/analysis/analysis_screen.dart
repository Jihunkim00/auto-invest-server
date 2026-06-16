import 'package:flutter/material.dart';

import '../../core/widgets/section_card.dart';
import '../../models/candidate.dart';
import '../../models/watchlist_operator_summary.dart';
import '../../models/watchlist_run_result.dart';
import '../dashboard/dashboard_controller.dart';
import '../dashboard/widgets/broker_context_controls.dart';
import '../dashboard/widgets/result_presentation_helpers.dart' as presentation;

class AnalysisScreen extends StatefulWidget {
  const AnalysisScreen({
    super.key,
    required this.controller,
    this.onOpenManualOrder,
    this.onOpenDashboard,
  });

  final DashboardController controller;
  final VoidCallback? onOpenManualOrder;
  final VoidCallback? onOpenDashboard;

  @override
  State<AnalysisScreen> createState() => _AnalysisScreenState();
}

class _AnalysisScreenState extends State<AnalysisScreen> {
  int _selectedCandidateIndex = 0;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: widget.controller,
      builder: (context, _) {
        final review = _latestDecisionReview(widget.controller);
        final candidates = review.candidates;
        final selectedIndex = candidates.isEmpty
            ? 0
            : _selectedCandidateIndex.clamp(0, candidates.length - 1).toInt();
        final selected = candidates.isEmpty ? null : candidates[selectedIndex];
        final selectedDetail = selected == null
            ? null
            : _detailedCandidateFor(selected, review.result) ?? selected;

        return SafeArea(
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Expanded(
                  child: Text(
                    'KIS Decision Review',
                    style: TextStyle(fontSize: 28, fontWeight: FontWeight.w700),
                  ),
                ),
                BrokerContextBadge(controller: widget.controller),
              ]),
              const SizedBox(height: 6),
              const Text(
                'Candidate comparison, hold rationale, GPT context, and manual next action review.',
                style: TextStyle(color: Colors.white70),
              ),
              const SizedBox(height: 12),
              if (widget.controller.krWatchlistPreviewLoading) ...[
                const _LoadingReviewCard(),
                const SizedBox(height: 12),
              ],
              if (widget.controller.krWatchlistPreviewError != null) ...[
                _ErrorReviewCard(
                    message: widget.controller.krWatchlistPreviewError!),
                const SizedBox(height: 12),
              ],
              if (review.summary == null)
                _EmptyReviewCard(onOpenDashboard: widget.onOpenDashboard)
              else ...[
                _KisWatchlistSummaryCard(
                  result: review.result,
                  summary: review.summary!,
                ),
                if (review.summary!.failedCount > 0) ...[
                  const SizedBox(height: 12),
                  _GptFailureCard(failedCount: review.summary!.failedCount),
                ],
                const SizedBox(height: 12),
                _CandidateComparisonCard(
                  candidates: candidates,
                  selectedIndex: selectedIndex,
                  onSelect: (index) {
                    setState(() => _selectedCandidateIndex = index);
                  },
                ),
                const SizedBox(height: 12),
                if (selectedDetail == null)
                  const _EmptyCandidateCard()
                else ...[
                  _SelectedCandidateDeepDive(candidate: selectedDetail),
                  const SizedBox(height: 12),
                  _ManualDecisionRationaleCard(candidate: selectedDetail),
                  const SizedBox(height: 12),
                  _ManualNextActionCard(
                    candidate: selectedDetail,
                    candidateRank: selectedIndex + 1,
                    onOpenManualOrder: widget.onOpenManualOrder,
                    controller: widget.controller,
                  ),
                ],
              ],
            ],
          ),
        );
      },
    );
  }
}

class _DecisionReviewData {
  const _DecisionReviewData({
    required this.result,
    required this.summary,
    required this.candidates,
  });

  final WatchlistRunResult? result;
  final WatchlistOperatorSummary? summary;
  final List<Candidate> candidates;
}

_DecisionReviewData _latestDecisionReview(DashboardController controller) {
  final preview = controller.krWatchlistPreview;
  if (preview?.operatorSummary != null) {
    return _DecisionReviewData(
      result: preview,
      summary: preview!.operatorSummary!,
      candidates: _reviewCandidates(preview, preview.operatorSummary!),
    );
  }

  final latest = controller.runResult;
  if (latest.operatorSummary != null) {
    return _DecisionReviewData(
      result: latest,
      summary: latest.operatorSummary!,
      candidates: _reviewCandidates(latest, latest.operatorSummary!),
    );
  }

  return const _DecisionReviewData(
    result: null,
    summary: null,
    candidates: <Candidate>[],
  );
}

List<Candidate> _reviewCandidates(
  WatchlistRunResult result,
  WatchlistOperatorSummary summary,
) {
  final bySymbol = <String, Candidate>{};

  void add(Candidate? candidate) {
    if (candidate == null) return;
    final symbol = candidate.symbol.trim().toUpperCase();
    if (symbol.isEmpty || bySymbol.containsKey(symbol)) return;
    bySymbol[symbol] = candidate;
  }

  for (final candidate in summary.topGptCandidates) {
    add(candidate);
  }
  add(summary.bestCandidate);
  for (final candidate in result.finalRankedCandidates) {
    add(candidate);
  }
  for (final candidate in result.researchedCandidates) {
    add(candidate);
  }
  for (final candidate in result.topQuantCandidates) {
    add(candidate);
  }

  return bySymbol.values.take(5).toList(growable: false);
}

Candidate? _detailedCandidateFor(
    Candidate candidate, WatchlistRunResult? result) {
  if (result == null) return null;
  final symbol = candidate.symbol.trim().toUpperCase();
  if (symbol.isEmpty) return null;
  final pool = <Candidate>[
    ...result.finalRankedCandidates,
    ...result.researchedCandidates,
    ...result.topQuantCandidates,
  ];
  for (final item in pool) {
    if (item.symbol.trim().toUpperCase() != symbol) continue;
    if (item.hasIndicatorValues ||
        item.whyHold.isNotEmpty ||
        item.whyNotBuy.isNotEmpty ||
        item.operatorSummary.isNotEmpty ||
        item.gptReason.isNotEmpty ||
        item.aiReason.isNotEmpty) {
      return item;
    }
  }
  return null;
}

class _KisWatchlistSummaryCard extends StatelessWidget {
  const _KisWatchlistSummaryCard({
    required this.result,
    required this.summary,
  });

  final WatchlistRunResult? result;
  final WatchlistOperatorSummary summary;

  @override
  Widget build(BuildContext context) {
    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.psychology_alt_outlined, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              'KIS Watchlist GPT Summary',
              style: Theme.of(context).textTheme.titleMedium,
            ),
          ),
          const _SoftBadge(text: 'OPERATOR REVIEW', color: Colors.greenAccent),
        ]),
        const SizedBox(height: 10),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(text: 'PREVIEW ONLY', color: Colors.lightBlueAccent),
          _SoftBadge(text: 'GPT TOP 5', color: Colors.cyanAccent),
          _SoftBadge(text: 'NO ORDER SUBMIT', color: Colors.orangeAccent),
          _SoftBadge(text: 'HOLD / WATCH', color: Colors.amberAccent),
        ]),
        const SizedBox(height: 12),
        Wrap(spacing: 10, runSpacing: 10, children: [
          _MetricTile(
            label: 'Completed GPT',
            value: summary.completedGptCount.toString(),
          ),
          _MetricTile(
              label: 'Failed GPT', value: summary.failedCount.toString()),
          _MetricTile(label: 'Not Run', value: summary.notRunCount.toString()),
          _MetricTile(
              label: 'Best Candidate',
              value: _bestCandidateLabel(summary, result)),
          const _MetricTile(label: 'Decision', value: 'HOLD / REVIEW ONLY'),
        ]),
        const SizedBox(height: 12),
        _InfoLine(
          label: 'Conservative Decision Summary',
          value: presentation.displayText(
            summary.conservativeDecisionSummary,
            fallback: 'Review top GPT candidates before any manual action.',
          ),
        ),
        _InfoLine(
          label: 'Next Manual Action Hint',
          value: presentation.displayText(
            summary.nextManualActionHint,
            fallback: 'Open Trading for manual review only.',
          ),
        ),
        const SizedBox(height: 10),
        _DetailGroup(
          title: 'Safety Flags',
          children: [
            _MiniMetric(
                label: 'preview_only',
                value: presentation.boolStatus(summary.previewOnly)),
            _MiniMetric(
                label: 'real_order',
                value: presentation.boolStatus(summary.realOrderSubmitted)),
            _MiniMetric(
                label: 'broker_submit',
                value: presentation.boolStatus(summary.brokerSubmitCalled)),
            _MiniMetric(
                label: 'manual_submit',
                value: presentation.boolStatus(summary.manualSubmitCalled)),
          ],
        ),
        if (summary.topRiskFlags.isNotEmpty)
          _InfoLine(
            label: 'Top Risk Flags',
            value: _translatedList(summary.topRiskFlags),
            color: Colors.orangeAccent,
          ),
        if (summary.topGatingNotes.isNotEmpty)
          _InfoLine(
            label: 'Gating Notes',
            value: _translatedList(summary.topGatingNotes),
            color: Colors.amberAccent,
          ),
      ]),
    );
  }
}

class _CandidateComparisonCard extends StatelessWidget {
  const _CandidateComparisonCard({
    required this.candidates,
    required this.selectedIndex,
    required this.onSelect,
  });

  final List<Candidate> candidates;
  final int selectedIndex;
  final ValueChanged<int> onSelect;

  @override
  Widget build(BuildContext context) {
    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.compare_arrows_outlined, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              'Top 5 GPT Candidate Comparison',
              style: Theme.of(context).textTheme.titleMedium,
            ),
          ),
        ]),
        const SizedBox(height: 10),
        if (candidates.isEmpty)
          const Text(
            'No GPT candidate comparison returned.',
            style: TextStyle(color: Colors.white70),
          )
        else
          for (final entry in candidates.asMap().entries)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: _CandidateComparisonRow(
                rank: entry.key + 1,
                candidate: entry.value,
                selected: entry.key == selectedIndex,
                onTap: () => onSelect(entry.key),
              ),
            ),
      ]),
    );
  }
}

class _CandidateComparisonRow extends StatelessWidget {
  const _CandidateComparisonRow({
    required this.rank,
    required this.candidate,
    required this.selected,
    required this.onTap,
  });

  final int rank;
  final Candidate candidate;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final status = _gptStatus(candidate);
    final statusColor = status == 'failed'
        ? Colors.redAccent
        : status == 'completed'
            ? Colors.greenAccent
            : Colors.amberAccent;
    final reason = presentation.displayText(
      _firstText([
        candidate.reason,
        candidate.operatorSummary,
        candidate.gptReason,
        candidate.aiReason,
        candidate.note,
      ]),
      fallback: status == 'not_run'
          ? 'GPT not run for this candidate.'
          : 'No summary reason returned.',
    );

    return InkWell(
      borderRadius: BorderRadius.circular(8),
      onTap: onTap,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: selected
              ? Colors.lightBlueAccent.withValues(alpha: 0.12)
              : Colors.white.withValues(alpha: 0.04),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(
            color: selected
                ? Colors.lightBlueAccent.withValues(alpha: 0.65)
                : Colors.white.withValues(alpha: 0.10),
          ),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            _RankPill(text: '#$rank'),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                '${candidate.symbol} / ${_candidateName(candidate)}',
                style: const TextStyle(fontWeight: FontWeight.w800),
              ),
            ),
            _SoftBadge(text: status.toUpperCase(), color: statusColor),
          ]),
          const SizedBox(height: 8),
          Wrap(spacing: 12, runSpacing: 8, children: [
            _MiniMetric(
                label: 'Quant Buy',
                value: presentation.compactScore(candidate.quantBuyScore)),
            _MiniMetric(
                label: 'Quant Sell',
                value: presentation.compactScore(candidate.quantSellScore)),
            _MiniMetric(
                label: 'GPT Buy',
                value: presentation.compactScore(
                    candidate.gptBuyScore ?? candidate.aiBuyScore)),
            _MiniMetric(
                label: 'GPT Sell',
                value: presentation.compactScore(
                    candidate.gptSellScore ?? candidate.aiSellScore)),
            _MiniMetric(
                label: 'Final Buy',
                value: presentation.compactScore(
                    candidate.finalBuyScore ?? candidate.finalEntryScore)),
            _MiniMetric(
                label: 'Final Sell',
                value: presentation.compactScore(candidate.finalSellScore)),
            _MiniMetric(
                label: 'Confidence',
                value: presentation.compactScore(candidate.confidence)),
            _MiniMetric(
                label: 'Action Hint',
                value: presentation.displayText(candidate.actionHint,
                    fallback: 'watch')),
          ]),
          if (candidate.riskFlags.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(
              'Main risk flags: ${_translatedList(candidate.riskFlags)}',
              style: const TextStyle(color: Colors.orangeAccent),
            ),
          ],
          const SizedBox(height: 6),
          Text(
            'Short reason: $reason',
            style: const TextStyle(color: Colors.white70),
          ),
          if (status == 'not_run') ...[
            const SizedBox(height: 4),
            const Text(
              'Only top KIS watchlist candidates receive GPT analysis.',
              style: TextStyle(color: Colors.white60),
            ),
          ],
        ]),
      ),
    );
  }
}

class _SelectedCandidateDeepDive extends StatelessWidget {
  const _SelectedCandidateDeepDive({required this.candidate});

  final Candidate candidate;

  @override
  Widget build(BuildContext context) {
    final status = _gptStatus(candidate);
    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.manage_search_outlined, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              'Selected Candidate Deep Dive',
              style: Theme.of(context).textTheme.titleMedium,
            ),
          ),
          _SoftBadge(
              text: _decisionLabel(candidate), color: Colors.amberAccent),
        ]),
        const SizedBox(height: 12),
        Wrap(spacing: 10, runSpacing: 10, children: [
          _MetricTile(label: 'Symbol', value: candidate.symbol),
          _MetricTile(label: 'Name', value: _candidateName(candidate)),
          _MetricTile(label: 'GPT Status', value: status.toUpperCase()),
          _MetricTile(label: 'Decision', value: _decisionLabel(candidate)),
        ]),
        const SizedBox(height: 12),
        _DetailGroup(
          title: 'Score Breakdown',
          children: [
            _MiniMetric(
                label: 'Quant Buy',
                value: presentation.compactScore(candidate.quantBuyScore)),
            _MiniMetric(
                label: 'Quant Sell',
                value: presentation.compactScore(candidate.quantSellScore)),
            _MiniMetric(
                label: 'GPT Buy',
                value: presentation.compactScore(
                    candidate.gptBuyScore ?? candidate.aiBuyScore)),
            _MiniMetric(
                label: 'GPT Sell',
                value: presentation.compactScore(
                    candidate.gptSellScore ?? candidate.aiSellScore)),
            _MiniMetric(
                label: 'Final Buy',
                value: presentation.compactScore(
                    candidate.finalBuyScore ?? candidate.finalEntryScore)),
            _MiniMetric(
                label: 'Final Sell',
                value: presentation.compactScore(candidate.finalSellScore)),
            _MiniMetric(
                label: 'Confidence',
                value: presentation.compactScore(candidate.confidence)),
          ],
        ),
        const SizedBox(height: 12),
        _DetailGroup(
          title: 'Technical Snapshot',
          children: [
            _MiniMetric(label: 'Current Price', value: _priceLabel(candidate)),
            _MiniMetric(
                label: 'EMA20',
                value: _indicatorLabel(candidate, const ['ema20', 'ema_20'])),
            _MiniMetric(
                label: 'EMA50',
                value: _indicatorLabel(candidate, const ['ema50', 'ema_50'])),
            _MiniMetric(
                label: 'RSI', value: _indicatorLabel(candidate, const ['rsi'])),
            _MiniMetric(
                label: 'VWAP',
                value: _indicatorLabel(candidate, const ['vwap'])),
            _MiniMetric(
                label: 'ATR', value: _indicatorLabel(candidate, const ['atr'])),
            _MiniMetric(
                label: 'Volume Ratio',
                value: _indicatorLabel(
                    candidate, const ['volume_ratio', 'volumeRatio'])),
            _MiniMetric(
                label: 'Momentum',
                value: _indicatorLabel(candidate, const ['momentum'],
                    percentLike: true)),
            _MiniMetric(
                label: 'Indicator Status',
                value: presentation.displayText(candidate.indicatorStatus,
                    fallback: '--')),
            _MiniMetric(
                label: 'Indicator Bars',
                value: candidate.indicatorBarCount?.toString() ?? '--'),
          ],
        ),
        const SizedBox(height: 12),
        _InfoLine(
          label: 'GPT Reason',
          value: presentation.displayText(
            _gptReason(candidate),
            fallback: status == 'failed'
                ? 'GPT analysis unavailable'
                : status == 'not_run'
                    ? 'GPT not run. Only top KIS watchlist candidates receive GPT analysis.'
                    : 'No GPT reason returned.',
          ),
        ),
        _InfoLine(
          label: 'Quant Reason',
          value: presentation.displayText(_quantReason(candidate),
              fallback: 'No quant reason returned.'),
        ),
        if (candidate.riskFlags.isNotEmpty)
          _InfoLine(
              label: 'Risk Flags',
              value: _translatedList(candidate.riskFlags),
              color: Colors.orangeAccent),
        if (candidate.gatingNotes.isNotEmpty)
          _InfoLine(
              label: 'Gating Notes',
              value: _translatedList(candidate.gatingNotes),
              color: Colors.amberAccent),
        if (candidate.warnings.isNotEmpty)
          _InfoLine(
              label: 'Warnings',
              value: _translatedList(candidate.warnings),
              color: Colors.orangeAccent),
        if (_blockReasons(candidate).isNotEmpty)
          _InfoLine(
              label: 'Block Reasons',
              value: _translatedList(_blockReasons(candidate)),
              color: Colors.redAccent),
      ]),
    );
  }
}

class _ManualDecisionRationaleCard extends StatelessWidget {
  const _ManualDecisionRationaleCard({required this.candidate});

  final Candidate candidate;

  @override
  Widget build(BuildContext context) {
    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.rule_outlined, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              'Why Hold / Why Not Buy / Next Manual Action',
              style: Theme.of(context).textTheme.titleMedium,
            ),
          ),
        ]),
        const SizedBox(height: 12),
        _InfoLine(
          label: 'Why Hold',
          value: presentation.displayText(
            candidate.whyHold,
            fallback:
                'KIS watchlist preview is advisory-only and no order was submitted.',
          ),
          color: Colors.amberAccent,
        ),
        _InfoLine(
          label: 'Why Not Buy',
          value: candidate.whyNotBuy.isEmpty
              ? presentation.translateReason(
                  presentation.firstText([
                    candidate.noOrderReason,
                    candidate.skipReason,
                    candidate.blockReason,
                  ]),
                  entryPenalty: candidate.entryPenalty ??
                      candidate.gptContext.entryPenalty,
                )
              : _translatedList(candidate.whyNotBuy),
          color: Colors.orangeAccent,
        ),
        _InfoLine(
          label: 'Next Manual Action',
          value: presentation.displayText(
            candidate.nextManualActionHint,
            fallback:
                'Open Trading, review this symbol manually, then validate and confirm live only if all safety gates pass.',
          ),
          color: Colors.lightBlueAccent,
        ),
      ]),
    );
  }
}

class _ManualNextActionCard extends StatelessWidget {
  const _ManualNextActionCard({
    required this.candidate,
    required this.candidateRank,
    required this.controller,
    required this.onOpenManualOrder,
  });

  final Candidate candidate;
  final int candidateRank;
  final DashboardController controller;
  final VoidCallback? onOpenManualOrder;

  @override
  Widget build(BuildContext context) {
    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.open_in_new_outlined, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              'Manual Next Action',
              style: Theme.of(context).textTheme.titleMedium,
            ),
          ),
          const _SoftBadge(text: 'PREFILL ONLY', color: Colors.lightBlueAccent),
        ]),
        const SizedBox(height: 10),
        const Text(
          'Trading opens with the selected symbol prepared for manual review. No validation, live confirmation, or order submission is triggered from this screen.',
          style: TextStyle(color: Colors.white70),
        ),
        const SizedBox(height: 12),
        Align(
          alignment: Alignment.centerLeft,
          child: OutlinedButton.icon(
            key: const Key('analysis_open_in_trading_button'),
            onPressed: () {
              final result = controller.prepareKisTradingFromWatchlistCandidate(
                candidate,
                candidateRank: candidateRank,
              );
              if (result.success) {
                onOpenManualOrder?.call();
              }
              ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                content: Text(result.message),
                backgroundColor:
                    result.success ? Colors.green : Colors.redAccent,
              ));
            },
            icon: const Icon(Icons.search, size: 18),
            label: const Text('Open in Trading for Manual Review'),
          ),
        ),
      ]),
    );
  }
}

class _LoadingReviewCard extends StatelessWidget {
  const _LoadingReviewCard();

  @override
  Widget build(BuildContext context) {
    return const SectionCard(
      child: Row(children: [
        SizedBox(
          width: 18,
          height: 18,
          child: CircularProgressIndicator(strokeWidth: 2),
        ),
        SizedBox(width: 10),
        Expanded(
          child: Text(
            'Loading KIS watchlist decision review...',
            style:
                TextStyle(color: Colors.white70, fontWeight: FontWeight.w600),
          ),
        ),
      ]),
    );
  }
}

class _ErrorReviewCard extends StatelessWidget {
  const _ErrorReviewCard({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return SectionCard(
      child: Text(
        message,
        style: const TextStyle(
            color: Colors.redAccent, fontWeight: FontWeight.w700),
      ),
    );
  }
}

class _EmptyReviewCard extends StatelessWidget {
  const _EmptyReviewCard({required this.onOpenDashboard});

  final VoidCallback? onOpenDashboard;

  @override
  Widget build(BuildContext context) {
    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text(
          'No KIS watchlist summary yet.',
          style: TextStyle(color: Colors.white, fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 6),
        const Text(
          'Run KIS Watchlist Preview from Dashboard first.',
          style: TextStyle(color: Colors.white70, fontWeight: FontWeight.w600),
        ),
        if (onOpenDashboard != null) ...[
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: onOpenDashboard,
            icon: const Icon(Icons.dashboard_outlined, size: 18),
            label: const Text('Go to Dashboard'),
          ),
        ],
      ]),
    );
  }
}

class _GptFailureCard extends StatelessWidget {
  const _GptFailureCard({required this.failedCount});

  final int failedCount;

  @override
  Widget build(BuildContext context) {
    return SectionCard(
      child: Text(
        'GPT failed for $failedCount candidates.\nQuant preview was preserved.\nNo order was submitted.',
        style: const TextStyle(
            color: Colors.orangeAccent, fontWeight: FontWeight.w700),
      ),
    );
  }
}

class _EmptyCandidateCard extends StatelessWidget {
  const _EmptyCandidateCard();

  @override
  Widget build(BuildContext context) {
    return const SectionCard(
      child: Text(
        'No selected candidate details returned.',
        style: TextStyle(color: Colors.white70),
      ),
    );
  }
}

class _DetailGroup extends StatelessWidget {
  const _DetailGroup({
    required this.title,
    required this.children,
  });

  final String title;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(title, style: const TextStyle(fontWeight: FontWeight.w700)),
      const SizedBox(height: 8),
      Wrap(spacing: 10, runSpacing: 10, children: children),
    ]);
  }
}

class _MetricTile extends StatelessWidget {
  const _MetricTile({
    required this.label,
    required this.value,
  });

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(minWidth: 132),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(
          label.toUpperCase(),
          style: const TextStyle(
            color: Colors.white54,
            fontSize: 11,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 4),
        Text(
          value,
          style: const TextStyle(
            color: Colors.white,
            fontWeight: FontWeight.w800,
          ),
        ),
      ]),
    );
  }
}

class _MiniMetric extends StatelessWidget {
  const _MiniMetric({
    required this.label,
    required this.value,
  });

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 118,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(
          label,
          style: const TextStyle(color: Colors.white54, fontSize: 12),
        ),
        const SizedBox(height: 2),
        Text(
          value,
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(fontWeight: FontWeight.w800),
        ),
      ]),
    );
  }
}

class _InfoLine extends StatelessWidget {
  const _InfoLine({
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
      padding: const EdgeInsets.only(top: 8),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(
          label,
          style: const TextStyle(
              color: Colors.white54, fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 3),
        Text(
          value,
          style: TextStyle(
            color: color ?? Colors.white,
            fontWeight: FontWeight.w700,
          ),
        ),
      ]),
    );
  }
}

class _RankPill extends StatelessWidget {
  const _RankPill({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
      ),
      child: Text(text, style: const TextStyle(fontWeight: FontWeight.w800)),
    );
  }
}

class _SoftBadge extends StatelessWidget {
  const _SoftBadge({
    required this.text,
    required this.color,
  });

  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.45)),
      ),
      child: Text(
        text,
        style: TextStyle(
          color: color,
          fontSize: 11,
          fontWeight: FontWeight.w800,
        ),
      ),
    );
  }
}

String _bestCandidateLabel(
  WatchlistOperatorSummary summary,
  WatchlistRunResult? result,
) {
  final best = summary.bestCandidate;
  if (best != null && best.symbol.isNotEmpty) {
    return '${best.symbol} ${_candidateName(best)}';
  }
  final symbol = result?.finalBestCandidate.trim() ?? '';
  return symbol.isEmpty ? 'None' : symbol;
}

String _candidateName(Candidate candidate) {
  final name = candidate.name.trim();
  if (name.isEmpty || name.toUpperCase() == candidate.symbol.toUpperCase()) {
    return candidate.symbol;
  }
  return name;
}

String _gptStatus(Candidate candidate) {
  final status = candidate.gptAnalysisStatus.trim().toLowerCase();
  if (status == 'completed' || status == 'failed' || status == 'not_run') {
    return status;
  }
  if (candidate.gptUsed == false) return 'not_run';
  if (candidate.gptUsed == true && _gptReason(candidate).isNotEmpty) {
    return 'completed';
  }
  return 'not_run';
}

String _decisionLabel(Candidate candidate) {
  final action = candidate.action.trim().toUpperCase();
  if (candidate.previewOnly == true || candidate.tradingEnabled == false) {
    return 'HOLD / WATCH';
  }
  if (action.isNotEmpty && action != 'NULL') return action;
  return 'HOLD / WATCH';
}

String _gptReason(Candidate candidate) {
  return _firstText([
    candidate.aiReason,
    candidate.gptReason,
    candidate.gptContext.reason,
    candidate.marketResearchReason,
    candidate.operatorSummary,
  ]);
}

String _quantReason(Candidate candidate) {
  return _firstText([
    candidate.reason,
    candidate.note,
    candidate.noOrderReason,
    candidate.skipReason,
    candidate.blockReason,
  ]);
}

List<String> _blockReasons(Candidate candidate) {
  final values = <String>[
    ...candidate.blockReasons,
    if (candidate.hardBlockReason != null) candidate.hardBlockReason!,
    if (candidate.blockReason != null) candidate.blockReason!,
    if (candidate.noOrderReason != null) candidate.noOrderReason!,
    if (candidate.skipReason != null) candidate.skipReason!,
  ];
  return values.where((item) => item.trim().isNotEmpty).toSet().toList();
}

String _translatedList(List<String> values) {
  final translated = values
      .where((item) => item.trim().isNotEmpty)
      .map((item) => presentation.translateReason(item))
      .toSet()
      .toList();
  return translated.isEmpty ? 'None' : translated.join(', ');
}

String _priceLabel(Candidate candidate) {
  final price = candidate.currentPrice ??
      _nullableDouble(candidate.indicatorPayload['current_price']) ??
      _nullableDouble(candidate.indicatorPayload['price']) ??
      _nullableDouble(candidate.indicatorPayload['close']);
  return _numberLabel(price);
}

String _indicatorLabel(
  Candidate candidate,
  List<String> keys, {
  bool percentLike = false,
}) {
  for (final key in keys) {
    final value = candidate.indicatorPayload[key];
    if (value == null) continue;
    if (percentLike) return _percentLabel(value);
    return _valueLabel(value);
  }
  return '--';
}

String _valueLabel(Object? value) {
  if (value == null) return '--';
  final number = _nullableDouble(value);
  if (number != null) return _numberLabel(number);
  final text = value.toString().trim();
  return text.isEmpty || text == 'null' ? '--' : text;
}

String _numberLabel(num? value) {
  if (value == null) return '--';
  final number = value.toDouble();
  if (number.abs() >= 1000) return number.toStringAsFixed(0);
  if (number.truncateToDouble() == number) return number.toStringAsFixed(0);
  return number.toStringAsFixed(2);
}

String _percentLabel(Object? value) {
  final number = _nullableDouble(value);
  if (number == null) return _valueLabel(value);
  return '${(number * 100).toStringAsFixed(2)}%';
}

double? _nullableDouble(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  final text = value.toString().trim().replaceAll(',', '');
  if (text.isEmpty || text == 'null') return null;
  return double.tryParse(text);
}

String _firstText(List<String?> values) {
  for (final value in values) {
    final text = value?.trim();
    if (text != null && text.isNotEmpty && text != 'null') return text;
  }
  return '';
}
