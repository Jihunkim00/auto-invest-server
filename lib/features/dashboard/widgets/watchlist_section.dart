import 'package:flutter/material.dart';

import '../../../core/widgets/section_card.dart';
import '../../../models/kis_watchlist_preview.dart';
import '../../../models/market_watchlist.dart';
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
          Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
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
            const _StateLine(
                text:
                    'Quant-first | GPT advisory only | No real order submitted'),
            if (controller.krWatchlistPreviewError != null) ...[
              const SizedBox(height: 10),
              _StateLine(
                  text: controller.krWatchlistPreviewError!,
                  color: Colors.redAccent),
            ],
            if (controller.krWatchlistPreview != null) ...[
              const SizedBox(height: 10),
              _PreviewResult(preview: controller.krWatchlistPreview!),
            ],
          ])
        else
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
                ? 'Running watchlist...'
                : 'Run US Watchlist Once'),
          ),
      ]),
    );
  }
}

class _PreviewResult extends StatelessWidget {
  const _PreviewResult({required this.preview});

  final KisWatchlistPreview preview;

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
        Wrap(spacing: 8, runSpacing: 8, children: [
          const _SoftBadge(text: 'PREVIEW ONLY', color: Colors.lightBlueAccent),
          const _SoftBadge(text: 'TRADING DISABLED', color: Colors.amberAccent),
          const _SoftBadge(
              text: 'NO REAL ORDER SUBMITTED', color: Colors.orangeAccent),
          _SoftBadge(
              text: preview.gptAnalysisIncluded
                  ? 'GPT ADVISORY'
                  : 'PRICE-ONLY PREVIEW',
              color: preview.gptAnalysisIncluded
                  ? Colors.greenAccent
                  : Colors.white70),
        ]),
        const SizedBox(height: 12),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _DataPair(label: 'Market', value: '${preview.market} / KIS'),
          _DataPair(label: 'Result', value: preview.result),
          _DataPair(label: 'Action', value: preview.action.toUpperCase()),
          _DataPair(
              label: 'Should Trade',
              value: preview.shouldTrade ? 'YES' : 'NO'),
          _DataPair(label: 'Analyzed', value: '${preview.analyzedSymbolCount}'),
        ]),
        if (preview.warnings.isNotEmpty) ...[
          const SizedBox(height: 10),
          _StateLine(text: 'Warnings: ${preview.warnings.join(', ')}'),
        ],
        const SizedBox(height: 10),
        for (final item in preview.items) ...[
          _PreviewItemRow(item: item),
          if (item != preview.items.last) const SizedBox(height: 8),
        ],
      ]),
    );
  }
}

class _PreviewItemRow extends StatelessWidget {
  const _PreviewItemRow({required this.item});

  final KisWatchlistPreviewItem item;

  @override
  Widget build(BuildContext context) {
    final title =
        item.name.isEmpty ? item.symbol : '${item.symbol} · ${item.name}';
    final subtitle = item.market.isEmpty ? '' : ' · ${item.market}';
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Text('$title$subtitle',
                style: const TextStyle(
                    color: Colors.white, fontWeight: FontWeight.w800)),
          ),
          _SoftBadge(
              text: _indicatorStatusLabel(item.indicatorStatus),
              color: _indicatorStatusColor(item.indicatorStatus)),
          const SizedBox(width: 8),
          _SoftBadge(
              text: item.actionHint.toUpperCase(),
              color: item.actionHint == 'avoid'
                  ? Colors.redAccent
                  : item.actionHint == 'candidate'
                      ? Colors.greenAccent
                      : Colors.lightBlueAccent),
        ]),
        const SizedBox(height: 8),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _DataPair(
              label: 'Current',
              value:
                  item.currentPrice == null ? 'n/a' : _krw(item.currentPrice!)),
          _DataPair(
              label: 'Entry Ready', value: item.entryReady ? 'YES' : 'NO'),
          _DataPair(
              label: 'Trade Allowed', value: item.tradeAllowed ? 'YES' : 'NO'),
          _DataPair(
              label: 'Block Reason',
              value: item.blockReason.isEmpty ? 'none' : item.blockReason),
        ]),
        const SizedBox(height: 10),
        const _SubsectionTitle(text: 'Score Breakdown'),
        if (item.hasScores)
          Wrap(spacing: 14, runSpacing: 8, children: [
            if (item.quantBuyScore != null)
              _DataPair(label: 'Quant Buy', value: _score(item.quantBuyScore)),
            if (item.quantSellScore != null)
              _DataPair(label: 'Quant Sell', value: _score(item.quantSellScore)),
            if (item.aiBuyScore != null)
              _DataPair(label: 'AI Buy', value: _score(item.aiBuyScore)),
            if (item.aiSellScore != null)
              _DataPair(label: 'AI Sell', value: _score(item.aiSellScore)),
            if (item.finalBuyScore != null)
              _DataPair(label: 'Final Buy', value: _score(item.finalBuyScore)),
            if (item.finalSellScore != null)
              _DataPair(label: 'Final Sell', value: _score(item.finalSellScore)),
            if (item.confidence != null)
              _DataPair(label: 'Confidence', value: _score(item.confidence)),
          ])
        else
          const _StateLine(
              text:
                  'Technical score not calculated. Reason: insufficient indicator data.'),
        const SizedBox(height: 10),
        const _SubsectionTitle(text: 'Quant Indicators'),
        if (item.hasIndicatorValues)
          _IndicatorPayload(payload: item.indicatorPayload)
        else
          const _StateLine(text: 'KIS OHLCV indicators not available yet'),
        const SizedBox(height: 10),
        const _SubsectionTitle(text: 'GPT advisory context'),
        if (item.reason.isNotEmpty) ...[
          Text(item.reason, style: const TextStyle(color: Colors.white70)),
        ],
        if (item.gptReason.isNotEmpty) ...[
          const SizedBox(height: 4),
          Text(item.gptReason, style: const TextStyle(color: Colors.white60)),
        ],
        if (item.blockReasons.isNotEmpty) ...[
          const SizedBox(height: 6),
          Text('Blocks: ${item.blockReasons.join(', ')}',
              style: const TextStyle(color: Colors.white54, fontSize: 12)),
        ],
        if (item.error != null) ...[
          const SizedBox(height: 6),
          Text('Error: ${item.error}',
              style: const TextStyle(color: Colors.redAccent, fontSize: 12)),
        ],
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

class _SubsectionTitle extends StatelessWidget {
  const _SubsectionTitle({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Text(text.toUpperCase(),
          style: const TextStyle(
              color: Colors.white54,
              fontSize: 10,
              fontWeight: FontWeight.w800)),
    );
  }
}

class _IndicatorPayload extends StatelessWidget {
  const _IndicatorPayload({required this.payload});

  final Map<String, dynamic> payload;

  @override
  Widget build(BuildContext context) {
    final entries =
        payload.entries.where((entry) => entry.value != null).toList();
    return Wrap(spacing: 14, runSpacing: 8, children: [
      for (final entry in entries)
        _DataPair(label: entry.key, value: entry.value.toString()),
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
        ? '${item.symbol} · ${item.name} · ${item.market}'
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

String _score(double? value) {
  if (value == null) return 'n/a';
  if (value == value.roundToDouble()) return value.toStringAsFixed(0);
  return value.toStringAsFixed(2);
}

String _indicatorStatusLabel(String value) {
  switch (value) {
    case 'ok':
      return 'OK';
    case 'price_only':
      return 'PRICE ONLY';
    default:
      return 'INSUFFICIENT DATA';
  }
}

Color _indicatorStatusColor(String value) {
  switch (value) {
    case 'ok':
      return Colors.greenAccent;
    case 'price_only':
      return Colors.lightBlueAccent;
    default:
      return Colors.orangeAccent;
  }
}

String _krw(double value) {
  final sign = value < 0 ? '-' : '';
  return '$sign₩${_groupedNumber(value.abs().round())}';
}

String _groupedNumber(int value) {
  final text = value.toString();
  final buffer = StringBuffer();
  for (var i = 0; i < text.length; i += 1) {
    final remaining = text.length - i;
    buffer.write(text[i]);
    if (remaining > 1 && remaining % 3 == 1) {
      buffer.write(',');
    }
  }
  return buffer.toString();
}
