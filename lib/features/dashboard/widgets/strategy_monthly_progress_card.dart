import 'package:flutter/material.dart';

import '../../../core/widgets/section_card.dart';
import '../../../models/strategy_performance.dart';
import '../dashboard_controller.dart';

class StrategyMonthlyProgressCard extends StatelessWidget {
  const StrategyMonthlyProgressCard({
    super.key,
    required this.performance,
    required this.loading,
    required this.error,
    required this.onRefresh,
  });

  final StrategyMonthlyPerformance? performance;
  final bool loading;
  final String? error;
  final Future<ActionResult> Function() onRefresh;

  @override
  Widget build(BuildContext context) {
    final value = performance;
    final color = value?.lossLimitHit == true
        ? Colors.orangeAccent
        : value?.targetHit == true
            ? Colors.greenAccent
            : Colors.lightBlueAccent;
    return SectionCard(
      key: const ValueKey('strategy-monthly-progress-card'),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(Icons.track_changes_outlined, color: color, size: 20),
          const SizedBox(width: 8),
          const Expanded(
            child: Text(
              'Strategy Monthly Progress',
              style: TextStyle(fontSize: 17, fontWeight: FontWeight.w900),
            ),
          ),
          IconButton(
            key: const ValueKey('strategy-performance-refresh'),
            tooltip: 'Refresh performance',
            onPressed: loading ? null : () => _refresh(context),
            icon: loading
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.refresh, size: 18),
          ),
        ]),
        const SizedBox(height: 8),
        Wrap(spacing: 6, runSpacing: 6, children: [
          const _Badge(text: 'READ ONLY'),
          const _Badge(text: 'ESTIMATED'),
          const _Badge(text: 'NO ORDER'),
          if (value != null)
            _Badge(text: value.activeProfile.profileName.toUpperCase()),
        ]),
        if (error != null) ...[
          const SizedBox(height: 10),
          Text(error!, style: const TextStyle(color: Colors.orangeAccent)),
        ],
        if (value == null) ...[
          const SizedBox(height: 12),
          const Text(
            'Monthly performance has not been loaded.',
            style: TextStyle(color: Colors.white60),
          ),
        ] else ...[
          const SizedBox(height: 12),
          Text(
            '${value.activeProfile.displayName} | ${_pct(value.monthlyTargetMinPct)}-${_pct(value.monthlyTargetMaxPct)} target',
            style: const TextStyle(color: Colors.white70),
          ),
          const SizedBox(height: 10),
          LinearProgressIndicator(
            key: const ValueKey('strategy-monthly-target-progress'),
            value: (value.targetProgressPct / 100).clamp(0.0, 1.0),
            minHeight: 8,
            color: color,
            backgroundColor: Colors.white12,
          ),
          const SizedBox(height: 10),
          Wrap(spacing: 10, runSpacing: 8, children: [
            _Metric(
              label: 'Current return',
              value: _signedPct(value.currentMonthReturnPct),
            ),
            _Metric(
              label: 'Target progress',
              value: '${value.targetProgressPct.toStringAsFixed(1)}%',
            ),
            _Metric(
              label: 'Monthly loss limit',
              value: _pct(value.monthlyMaxLossPct),
            ),
            _Metric(
              label: 'Loss budget used',
              value: '${value.lossBudgetUsedPct.toStringAsFixed(1)}%',
            ),
            _Metric(
              label: 'Target hit',
              value: value.targetHit ? 'YES' : 'NO',
            ),
            _Metric(
              label: 'Loss limit hit',
              value: value.lossLimitHit ? 'YES' : 'NO',
            ),
            _Metric(
              label: 'New entries',
              value: value.newEntriesAllowedByTarget ? 'ALLOWED' : 'BLOCKED',
            ),
          ]),
          if (value.dataQuality.hasWarnings) ...[
            const SizedBox(height: 10),
            _DataQualityWarning(quality: value.dataQuality),
          ],
        ],
      ]),
    );
  }

  Future<void> _refresh(BuildContext context) async {
    final result = await onRefresh();
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(result.message)),
    );
  }
}

class _DataQualityWarning extends StatelessWidget {
  const _DataQualityWarning({required this.quality});

  final StrategyDataQuality quality;

  @override
  Widget build(BuildContext context) {
    return Text(
      'Data quality: ${quality.notes.isEmpty ? 'best-effort estimate' : quality.notes.join(', ')}',
      style: const TextStyle(color: Colors.orangeAccent, fontSize: 12),
    );
  }
}

class _Metric extends StatelessWidget {
  const _Metric({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 132,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label,
            style: const TextStyle(color: Colors.white54, fontSize: 11)),
        const SizedBox(height: 2),
        Text(
          value,
          style: const TextStyle(fontWeight: FontWeight.w800),
        ),
      ]),
    );
  }
}

class _Badge extends StatelessWidget {
  const _Badge({required this.text});

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

String _pct(double value) => '${(value * 100).toStringAsFixed(1)}%';
String _signedPct(double value) {
  final pct = value * 100;
  return '${pct >= 0 ? '+' : ''}${pct.toStringAsFixed(2)}%';
}
