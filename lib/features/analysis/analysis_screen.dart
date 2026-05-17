import 'package:flutter/material.dart';

import '../../core/widgets/section_card.dart';
import '../../models/candidate.dart';
import '../dashboard/dashboard_controller.dart';
import 'widgets/analysis_metrics_section.dart';
import 'widgets/candidate_card.dart';
import 'widgets/final_candidate_section.dart';

class AnalysisScreen extends StatelessWidget {
  const AnalysisScreen({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final r = controller.runResult;
        final hasDisplayRun =
            controller.hasLatestRunResult || controller.showingOfflineFallback;
        return SafeArea(
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              const Text(
                'Analysis',
                style: TextStyle(fontSize: 28, fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 6),
              const Text(
                'Decision summary first. Raw candidate data stays in Advanced Details.',
                style: TextStyle(color: Colors.white70),
              ),
              const SizedBox(height: 12),
              _DecisionSummaryCard(controller: controller),
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
                SectionCard(
                  child: ExpansionTile(
                    initiallyExpanded: false,
                    title: const Text('Advanced Details'),
                    subtitle: const Text(
                      'Metrics, raw candidate lists, flags, and payload-derived details.',
                    ),
                    childrenPadding: const EdgeInsets.only(top: 8),
                    children: [
                      AnalysisMetricsSection(controller: controller),
                      const SizedBox(height: 12),
                      FinalCandidateSection(controller: controller),
                      const SizedBox(height: 12),
                      _CandidateList(
                        title: 'Top Quant Candidates',
                        candidates: r.topQuantCandidates,
                      ),
                      const SizedBox(height: 12),
                      _CandidateList(
                        title: 'Researched Candidates',
                        candidates: r.researchedCandidates,
                      ),
                      const SizedBox(height: 12),
                      _CandidateList(
                        title: 'Final Ranked Candidates',
                        candidates: r.finalRankedCandidates,
                      ),
                    ],
                  ),
                ),
              ],
            ],
          ),
        );
      },
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
          value: blockReason.isEmpty ? 'No block reason' : blockReason,
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

class _CandidateList extends StatelessWidget {
  const _CandidateList({required this.title, required this.candidates});

  final String title;
  final List<Candidate> candidates;

  @override
  Widget build(BuildContext context) {
    return ExpansionTile(
      initiallyExpanded: false,
      tilePadding: EdgeInsets.zero,
      title: Text(title),
      children: [
        if (candidates.isEmpty)
          const Padding(
            padding: EdgeInsets.only(bottom: 8),
            child:
                Text('No candidates.', style: TextStyle(color: Colors.white70)),
          )
        else
          for (var i = 0; i < candidates.length; i++)
            CandidateCard(index: i, candidate: candidates[i]),
      ],
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
  return 'Prepare a manual ticket, then validate and confirm in Manual Order.';
}
