import 'package:flutter/material.dart';

import '../../../core/utils/timestamp_formatter.dart';
import '../../../core/widgets/section_card.dart';
import '../../../models/strategy_performance.dart';

class StrategyTradePerformanceListCard extends StatelessWidget {
  const StrategyTradePerformanceListCard({
    super.key,
    required this.performance,
    required this.loading,
  });

  final StrategyTradePerformanceList? performance;
  final bool loading;

  @override
  Widget build(BuildContext context) {
    final value = performance;
    final items = value?.items ?? const <StrategyTradePerformanceItem>[];
    final quality = value?.dataQuality;
    return SectionCard(
      key: const ValueKey('strategy-trade-performance-list-card'),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.receipt_long_outlined, size: 20),
          const SizedBox(width: 8),
          const Expanded(
            child: Text(
              'Recent Trade Performance',
              style: TextStyle(fontSize: 17, fontWeight: FontWeight.w900),
            ),
          ),
          if (loading)
            const SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
        ]),
        const SizedBox(height: 8),
        const Text(
          'FIFO best-effort | read-only | estimated fees',
          style: TextStyle(color: Colors.white60, fontSize: 12),
        ),
        const SizedBox(height: 10),
        if (items.isEmpty)
          const Text(
            'No matched trade performance is available.',
            style: TextStyle(color: Colors.white60),
          )
        else
          for (final item in items.take(5))
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child:
                  Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        item.symbolName ?? item.symbol,
                        style: const TextStyle(fontWeight: FontWeight.w800),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        '${item.side.toUpperCase()} | qty ${item.quantity} | ${item.status}',
                        style: const TextStyle(
                          color: Colors.white54,
                          fontSize: 11,
                        ),
                      ),
                      if (_metadata(item).isNotEmpty) ...[
                        const SizedBox(height: 2),
                        Text(
                          _metadata(item),
                          style: const TextStyle(
                            color: Colors.white38,
                            fontSize: 11,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                const SizedBox(width: 8),
                Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                  Text(
                    _money(item.displayPnl),
                    style: TextStyle(
                      color: (item.displayPnl ?? 0) < 0
                          ? Colors.orangeAccent
                          : Colors.greenAccent,
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                  Text(
                    item.pnlPct == null ? '-' : _signedPct(item.pnlPct!),
                    style: const TextStyle(color: Colors.white54, fontSize: 11),
                  ),
                ]),
              ]),
            ),
        if (quality?.hasWarnings == true) ...[
          const SizedBox(height: 2),
          Text(
            'Data quality: ${quality!.notes.isEmpty ? 'best-effort estimate' : quality.notes.join(', ')}',
            style: const TextStyle(
              color: Colors.orangeAccent,
              fontSize: 12,
            ),
          ),
        ],
      ]),
    );
  }
}

String _metadata(StrategyTradePerformanceItem item) {
  final values = <String>[
    if (item.decisionSource?.trim().isNotEmpty == true)
      item.decisionSource!.trim(),
    if (item.createdAt?.trim().isNotEmpty == true)
      formatTimestampWithKst(item.createdAt),
  ];
  return values.join(' | ');
}

String _money(double? value) {
  if (value == null) return 'insufficient data';
  return '${value >= 0 ? '+' : ''}KRW ${value.toStringAsFixed(0)}';
}

String _signedPct(double value) {
  final pct = value * 100;
  return '${pct >= 0 ? '+' : ''}${pct.toStringAsFixed(2)}%';
}
