import 'package:flutter/material.dart';

import '../../../core/widgets/section_card.dart';
import '../../../models/market_watchlist.dart';
import '../../dashboard/dashboard_controller.dart';

class WatchlistSection extends StatelessWidget {
  const WatchlistSection({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final isKr = controller.selectedProvider == SelectedProvider.kis;
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
        const SizedBox(height: 10),
        Wrap(spacing: 8, runSpacing: 8, children: [
          Text(title,
              style: const TextStyle(
                  color: Colors.white70, fontWeight: FontWeight.w800)),
          if (isKr) ...[
            const _SoftBadge(text: 'PREVIEW ONLY', color: Colors.lightBlueAccent),
            const _SoftBadge(text: 'TRADING DISABLED', color: Colors.amberAccent),
            const _SoftBadge(text: 'NO AUTO ORDER', color: Colors.orangeAccent),
          ],
        ]),
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
              : Icon(isKr ? Icons.preview_outlined : Icons.play_arrow),
          label: Text(controller.runOnceLoading
              ? (isKr ? 'Running KIS preview...' : 'Running Alpaca watchlist...')
              : (isKr ? 'Run KIS Preview' : 'Run Alpaca Watchlist')),
        ),
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
