import 'package:flutter/material.dart';

import '../../../core/widgets/section_card.dart';
import '../../../models/strategy_dry_run_auto_buy.dart';
import '../dashboard_controller.dart';

class StrategyDryRunAutoBuyCard extends StatelessWidget {
  const StrategyDryRunAutoBuyCard({
    super.key,
    required this.result,
    required this.loading,
    required this.error,
    required this.onRun,
    required this.onRefresh,
  });

  final StrategyDryRunAutoBuyResult? result;
  final bool loading;
  final String? error;
  final Future<ActionResult> Function() onRun;
  final Future<ActionResult> Function() onRefresh;

  @override
  Widget build(BuildContext context) {
    final value = result;
    final action = (value?.action ?? 'hold').toUpperCase();
    final color = value?.wouldBuy == true
        ? Colors.greenAccent
        : value?.blocked == true
            ? Colors.orangeAccent
            : Colors.lightBlueAccent;
    return SectionCard(
      key: const ValueKey('strategy-dry-run-auto-buy-card'),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(Icons.science_outlined, color: color, size: 20),
          const SizedBox(width: 8),
          const Expanded(
            child: Text(
              'Profile-Aware Dry-Run Auto Buy',
              style: TextStyle(fontSize: 17, fontWeight: FontWeight.w900),
            ),
          ),
        ]),
        const SizedBox(height: 8),
        Wrap(spacing: 6, runSpacing: 6, children: [
          const _Badge(text: 'DRY RUN ONLY'),
          const _Badge(text: 'NO ORDER SUBMIT'),
          const _Badge(text: 'NO VALIDATION'),
          const _Badge(text: 'PROFILE AWARE'),
          const _Badge(text: 'TARGET AWARE'),
          _Badge(text: action, color: color),
        ]),
        const SizedBox(height: 10),
        Wrap(spacing: 8, runSpacing: 8, children: [
          FilledButton.icon(
            key: const ValueKey('strategy-dry-run-run-once'),
            onPressed: loading ? null : () => _run(context),
            icon: loading
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.play_arrow),
            label: const Text('Run Dry-Run Auto Buy Once'),
          ),
          OutlinedButton.icon(
            key: const ValueKey('strategy-dry-run-refresh'),
            onPressed: loading ? null : () => _refresh(context),
            icon: const Icon(Icons.refresh),
            label: const Text('Refresh Recent Dry-Runs'),
          ),
        ]),
        if (error != null) ...[
          const SizedBox(height: 10),
          Text(error!, style: const TextStyle(color: Colors.orangeAccent)),
          const SizedBox(height: 6),
          TextButton(
            key: const ValueKey('strategy-dry-run-retry'),
            onPressed: loading ? null : () => _refresh(context),
            child: const Text('Retry'),
          ),
        ],
        if (value == null) ...[
          const SizedBox(height: 12),
          const Text(
            'No profile-aware dry-run result yet.',
            style: TextStyle(color: Colors.white60),
          ),
        ] else ...[
          const SizedBox(height: 12),
          Wrap(spacing: 10, runSpacing: 8, children: [
            _Metric(label: 'Active profile', value: value.activeProfile),
            _Metric(
              label: 'Selected symbol',
              value: [
                value.selectedSymbolName,
                value.selectedSymbol,
              ].whereType<String>().join(' / ').isEmpty
                  ? '-'
                  : [
                      value.selectedSymbolName,
                      value.selectedSymbol,
                    ].whereType<String>().join(' / '),
            ),
            _Metric(label: 'Buy score', value: _score(value.buyScore)),
            _Metric(label: 'Final score', value: _score(value.finalScore)),
            _Metric(
              label: 'Recommended notional',
              value: _money(value.recommendedNotionalKrw),
            ),
            _Metric(
              label: 'Simulated quantity',
              value: '${value.simulatedQuantity}',
            ),
            _Metric(
              label: 'Target risk approved',
              value: value.targetRiskApproved ? 'YES' : 'NO',
            ),
            _Metric(label: 'Reason', value: value.reason),
            _Metric(label: 'Signal / Run', value: '${value.signalId ?? '-'} / ${value.tradeRunId ?? '-'}'),
            _Metric(
              label: 'Last run',
              value: value.createdAt?.toLocal().toString() ?? '-',
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

  Future<void> _run(BuildContext context) async {
    final action = await onRun();
    if (!context.mounted) return;
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(action.message)));
  }

  Future<void> _refresh(BuildContext context) async {
    final action = await onRefresh();
    if (!context.mounted) return;
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(action.message)));
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

String _score(double? value) =>
    value == null ? '-' : value.toStringAsFixed(1);
String _money(double value) => '₩${value.toStringAsFixed(0)}';
