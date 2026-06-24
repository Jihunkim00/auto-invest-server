import 'package:flutter/material.dart';

import '../../../core/widgets/section_card.dart';
import '../../../models/strategy_performance.dart';

class StrategyDailyPnlCard extends StatelessWidget {
  const StrategyDailyPnlCard({
    super.key,
    required this.performance,
    required this.loading,
    required this.error,
  });

  final StrategyDailyPerformance? performance;
  final bool loading;
  final String? error;

  @override
  Widget build(BuildContext context) {
    final value = performance;
    final color = (value?.netPnlEstimated ?? 0) < 0
        ? Colors.orangeAccent
        : Colors.greenAccent;
    return SectionCard(
      key: const ValueKey('strategy-daily-pnl-card'),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(Icons.query_stats_outlined, color: color, size: 20),
          const SizedBox(width: 8),
          const Expanded(
            child: Text(
              'Today P&L',
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
        const Wrap(spacing: 6, runSpacing: 6, children: [
          _PnlBadge(text: 'READ ONLY'),
          _PnlBadge(text: 'ESTIMATED'),
          _PnlBadge(text: 'NO ORDER'),
        ]),
        if (error != null) ...[
          const SizedBox(height: 10),
          Text(error!, style: const TextStyle(color: Colors.orangeAccent)),
        ],
        if (value == null) ...[
          const SizedBox(height: 12),
          const Text(
            'Daily P&L has not been loaded.',
            style: TextStyle(color: Colors.white60),
          ),
        ] else ...[
          const SizedBox(height: 12),
          Wrap(spacing: 10, runSpacing: 8, children: [
            _PnlMetric(
              label: 'Realized P&L',
              value: _money(value.realizedPnl),
            ),
            _PnlMetric(
              label: 'Unrealized P&L',
              value: _money(value.unrealizedPnl),
            ),
            _PnlMetric(
              label: 'Estimated net P&L',
              value: _money(value.netPnlEstimated),
            ),
            _PnlMetric(
              label: 'Estimated return',
              value: _signedPct(value.pnlPct),
            ),
            _PnlMetric(
              label: 'Filled orders',
              value: '${value.filledOrdersCount}',
            ),
            _PnlMetric(
              label: 'Rejected orders',
              value: '${value.rejectedOrdersCount}',
            ),
          ]),
          if (value.dataQuality.hasWarnings) ...[
            const SizedBox(height: 10),
            Text(
              'Data quality: ${value.dataQuality.notes.isEmpty ? 'best-effort estimate' : value.dataQuality.notes.join(', ')}',
              style: const TextStyle(color: Colors.orangeAccent, fontSize: 12),
            ),
          ],
        ],
      ]),
    );
  }
}

class _PnlMetric extends StatelessWidget {
  const _PnlMetric({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 145,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label,
            style: const TextStyle(color: Colors.white54, fontSize: 11)),
        const SizedBox(height: 2),
        Text(value, style: const TextStyle(fontWeight: FontWeight.w800)),
      ]),
    );
  }
}

class _PnlBadge extends StatelessWidget {
  const _PnlBadge({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: Colors.lightBlueAccent.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
        border:
            Border.all(color: Colors.lightBlueAccent.withValues(alpha: 0.32)),
      ),
      child: Text(
        text,
        style: const TextStyle(
          color: Colors.lightBlueAccent,
          fontSize: 10,
          fontWeight: FontWeight.w900,
        ),
      ),
    );
  }
}

String _money(double value) {
  final sign = value > 0 ? '+' : '';
  return '$sign${value.toStringAsFixed(0)} KRW';
}

String _signedPct(double value) {
  final pct = value * 100;
  return '${pct >= 0 ? '+' : ''}${pct.toStringAsFixed(2)}%';
}
