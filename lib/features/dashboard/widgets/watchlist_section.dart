import 'package:flutter/material.dart';

import '../../../core/widgets/section_card.dart';
import '../../../models/candidate.dart';
import '../../../models/market_watchlist.dart';
import '../../../models/watchlist_run_result.dart';
import '../../analysis/widgets/candidate_card.dart';
import '../../dashboard/dashboard_controller.dart';

class WatchlistSection extends StatelessWidget {
  const WatchlistSection({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final isKr = controller.selectedWatchlistMarket == PortfolioMarket.kr;
    final watchlist = isKr ? controller.krWatchlist : controller.usWatchlist;
    final title = isKr ? 'KR Watchlist / KIS' : 'US Watchlist / Alpaca';

    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.format_list_bulleted, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text('Watchlist',
                style: Theme.of(context).textTheme.titleMedium),
          ),
          _CountPill(text: '${watchlist.count} symbols'),
        ]),
        const SizedBox(height: 12),
        SegmentedButton<PortfolioMarket>(
          segments: const [
            ButtonSegment(
                value: PortfolioMarket.us, label: Text('US / Alpaca')),
            ButtonSegment(value: PortfolioMarket.kr, label: Text('KR / KIS')),
          ],
          selected: {controller.selectedWatchlistMarket},
          onSelectionChanged: (selection) =>
              controller.selectWatchlistMarket(selection.first),
        ),
        const SizedBox(height: 10),
        Wrap(spacing: 8, runSpacing: 8, children: [
          Text(title,
              style: const TextStyle(
                  color: Colors.white70, fontWeight: FontWeight.w800)),
          if (isKr) ...[
            const _SoftBadge(text: 'READ-ONLY', color: Colors.lightBlueAccent),
            const _SoftBadge(
                text: 'TRADING DISABLED', color: Colors.amberAccent),
          ],
        ]),
        const SizedBox(height: 12),
        if (controller.watchlistLoading)
          const LinearProgressIndicator(minHeight: 2)
        else if (watchlist.symbols.isEmpty)
          _StateLine(
              text: isKr
                  ? 'No KR watchlist symbols available'
                  : 'No US watchlist symbols available')
        else
          _WatchlistSymbols(watchlist: watchlist, isKr: isKr),
        if (controller.watchlistError != null) ...[
          const SizedBox(height: 10),
          _StateLine(text: controller.watchlistError!, color: Colors.redAccent),
        ],
        const SizedBox(height: 12),
        if (isKr)
          _KrPreviewControls(controller: controller)
        else
          _UsRunControls(controller: controller),
      ]),
    );
  }
}

class _KrPreviewControls extends StatelessWidget {
  const _KrPreviewControls({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      FilledButton.icon(
        onPressed: controller.krWatchlistPreviewLoading
            ? null
            : () async {
                final result = await controller.runKrWatchlistPreview();
                if (!context.mounted) return;
                ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                  content: Text(result.message),
                  backgroundColor:
                      result.success ? Colors.green : Colors.redAccent,
                ));
              },
        icon: controller.krWatchlistPreviewLoading
            ? const SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(strokeWidth: 2))
            : const Icon(Icons.preview_outlined),
        label: Text(controller.krWatchlistPreviewLoading
            ? 'Running KR preview...'
            : 'Run KR Preview'),
      ),
      const SizedBox(height: 10),
      const _StateLine(text: 'Quant-first \u00B7 GPT advisory only'),
      if (controller.krWatchlistPreviewError != null) ...[
        const SizedBox(height: 10),
        _StateLine(
            text: controller.krWatchlistPreviewError!, color: Colors.redAccent),
      ],
      if (controller.krWatchlistPreview != null) ...[
        const SizedBox(height: 10),
        _PreviewResult(preview: controller.krWatchlistPreview!),
      ],
    ]);
  }
}

class _UsRunControls extends StatelessWidget {
  const _UsRunControls({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return FilledButton.icon(
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
          ? 'Running watchlist...'
          : 'Run US Watchlist Once'),
    );
  }
}

class _PreviewResult extends StatelessWidget {
  const _PreviewResult({required this.preview});

  final WatchlistRunResult preview;

  @override
  Widget build(BuildContext context) {
    final blockReason = preview.triggerBlockReason.isEmpty
        ? preview.reason
        : preview.triggerBlockReason;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(text: 'PREVIEW ONLY', color: Colors.lightBlueAccent),
          _SoftBadge(text: 'TRADING DISABLED', color: Colors.amberAccent),
          _SoftBadge(
              text: 'NO REAL ORDER SUBMITTED', color: Colors.orangeAccent),
          _SoftBadge(text: 'GPT ADVISORY', color: Colors.greenAccent),
        ]),
        const SizedBox(height: 12),
        Wrap(spacing: 14, runSpacing: 8, children: [
          const _DataPair(label: 'Market', value: 'KR / KIS'),
          _DataPair(label: 'Result', value: preview.result),
          _DataPair(label: 'Action', value: preview.action.toUpperCase()),
          _DataPair(
              label: 'Should Trade', value: preview.shouldTrade ? 'YES' : 'NO'),
          _DataPair(
              label: 'Entry Ready',
              value: preview.finalEntryReady ? 'YES' : 'NO'),
          _DataPair(
              label: 'Best Score',
              value: _valueOrNotCalculated(preview.bestScore)),
          _DataPair(label: 'Analyzed', value: '${preview.analyzedSymbolCount}'),
        ]),
        const SizedBox(height: 10),
        _StateLine(text: 'Why no trade: $blockReason'),
        if (preview.finalCandidateSelectionReason.isNotEmpty) ...[
          const SizedBox(height: 10),
          _StateLine(text: preview.finalCandidateSelectionReason),
        ],
        if (preview.topQuantCandidates.isNotEmpty) ...[
          const SizedBox(height: 10),
          _CandidateSection(
              title: 'Top Quant Candidates',
              candidates: preview.topQuantCandidates),
        ],
        if (preview.researchedCandidates.isNotEmpty) ...[
          const SizedBox(height: 10),
          _CandidateSection(
              title: 'Researched Candidates',
              candidates: preview.researchedCandidates),
        ],
        const SizedBox(height: 10),
        _CandidateSection(
            title: 'Final Ranked Candidates',
            candidates: preview.finalRankedCandidates,
            initiallyExpanded: true),
        if (preview.finalRankedCandidates.isEmpty) ...[
          const SizedBox(height: 10),
          const _StateLine(text: 'No KR preview candidates returned.'),
        ],
      ]),
    );
  }
}

class _CandidateSection extends StatelessWidget {
  const _CandidateSection({
    required this.title,
    required this.candidates,
    this.initiallyExpanded = false,
  });

  final String title;
  final List<Candidate> candidates;
  final bool initiallyExpanded;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.03),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
      ),
      child: ExpansionTile(
        initiallyExpanded: initiallyExpanded,
        title: Text(title),
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(10, 0, 10, 10),
            child: Column(children: [
              for (var i = 0; i < candidates.length; i++)
                CandidateCard(index: i, candidate: candidates[i]),
            ]),
          ),
        ],
      ),
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
      constraints: const BoxConstraints(minWidth: 84, maxWidth: 150),
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

String _valueOrNotCalculated(num? value) {
  if (value == null) return 'Not calculated';
  if (value == value.roundToDouble()) return value.toStringAsFixed(0);
  return value.toStringAsFixed(2);
}
