import 'package:flutter/material.dart';

import '../../../core/widgets/section_card.dart';
import '../../../models/strategy_risk.dart';
import '../dashboard_controller.dart';

class StrategyRiskStateCard extends StatelessWidget {
  const StrategyRiskStateCard({
    super.key,
    required this.riskState,
    required this.loading,
    required this.error,
    required this.onRefresh,
  });

  final StrategyRiskState? riskState;
  final bool loading;
  final String? error;
  final Future<ActionResult> Function() onRefresh;

  @override
  Widget build(BuildContext context) {
    final value = riskState;
    final color = value?.newEntriesAllowed == false
        ? Colors.orangeAccent
        : Colors.greenAccent;
    return SectionCard(
      key: const ValueKey('strategy-risk-state-card'),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(Icons.shield_outlined, color: color, size: 20),
          const SizedBox(width: 8),
          const Expanded(
            child: Text(
              'Target-Aware Risk State',
              style: TextStyle(fontSize: 17, fontWeight: FontWeight.w900),
            ),
          ),
          IconButton(
            key: const ValueKey('strategy-risk-refresh'),
            tooltip: 'Refresh risk state',
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
          _Badge(
            text: value?.newEntriesAllowed == true
                ? 'ENTRY ALLOWED'
                : 'ENTRY BLOCKED',
            color: color,
          ),
          const _Badge(text: 'PROFILE-AWARE'),
          const _Badge(text: 'READ ONLY'),
          const _Badge(text: 'NO ORDER SUBMIT'),
          if (value?.targetHit == true)
            const _Badge(text: 'TARGET HIT', color: Colors.greenAccent),
          if (value?.lossLimitHit == true)
            const _Badge(text: 'LOSS LIMIT HIT', color: Colors.orangeAccent),
          if (value?.sizeReduced == true)
            const _Badge(text: 'SIZE REDUCED', color: Colors.amberAccent),
        ]),
        if (error != null) ...[
          const SizedBox(height: 10),
          Text(error!, style: const TextStyle(color: Colors.orangeAccent)),
        ],
        if (value == null) ...[
          const SizedBox(height: 12),
          const Text(
            'Risk state has not been loaded.',
            style: TextStyle(color: Colors.white60),
          ),
        ] else ...[
          const SizedBox(height: 12),
          Text(
            'Active profile: ${value.activeProfile.toUpperCase()}',
            style: const TextStyle(fontWeight: FontWeight.w800),
          ),
          if (value.primaryBlockReason != null) ...[
            const SizedBox(height: 4),
            Text(
              'Primary block: ${value.primaryBlockReason}',
              style: const TextStyle(color: Colors.orangeAccent),
            ),
          ],
          const SizedBox(height: 10),
          Wrap(spacing: 10, runSpacing: 8, children: [
            _Metric(
              label: 'Target progress',
              value: '${value.targetProgressPct.toStringAsFixed(1)}%',
            ),
            _Metric(
              label: 'Monthly return / limit',
              value:
                  '${_signedPct(value.currentMonthReturnPct)} / ${_pct(value.monthlyMaxLossPct)}',
            ),
            _Metric(
              label: 'Loss budget used',
              value: '${value.lossBudgetUsedPct.toStringAsFixed(1)}%',
            ),
            _Metric(
              label: 'Daily return / limit',
              value:
                  '${_signedPct(value.currentDailyReturnPct)} / ${_pct(value.dailyMaxLossPct)}',
            ),
            _Metric(
              label: 'Trades today',
              value: '${value.tradesUsedToday}/${value.maxTradesPerDay}',
            ),
            _Metric(
              label: 'Positions',
              value: '${value.currentPositionsCount}/${value.maxPositions}',
            ),
            _Metric(
              label: 'Recommended size',
              value:
                  '${_pct(value.recommendedOrderNotionalPct)} / ${_money(value.recommendedOrderNotionalKrw)}',
            ),
          ]),
          if (value.riskFlags.isNotEmpty) ...[
            const SizedBox(height: 10),
            Text(
              'Risk flags: ${value.riskFlags.join(', ')}',
              style: const TextStyle(color: Colors.amberAccent, fontSize: 12),
            ),
          ],
          if (value.gatingNotes.isNotEmpty) ...[
            const SizedBox(height: 8),
            for (final note in value.gatingNotes.take(3))
              Padding(
                padding: const EdgeInsets.only(top: 3),
                child: Text(
                  '• $note',
                  style: const TextStyle(color: Colors.white70, fontSize: 12),
                ),
              ),
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

class _Metric extends StatelessWidget {
  const _Metric({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 160,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label,
            style: const TextStyle(color: Colors.white54, fontSize: 11)),
        const SizedBox(height: 2),
        Text(value, style: const TextStyle(fontWeight: FontWeight.w800)),
      ]),
    );
  }
}

class _Badge extends StatelessWidget {
  const _Badge({required this.text, this.color = Colors.lightBlueAccent});

  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.32)),
      ),
      child: Text(
        text,
        style: TextStyle(
          color: color,
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

String _money(double value) => '₩${value.toStringAsFixed(0)}';
