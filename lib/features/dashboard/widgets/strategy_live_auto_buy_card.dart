import 'package:flutter/material.dart';

import '../../../core/widgets/section_card.dart';
import '../../../models/strategy_live_auto_buy.dart';
import '../dashboard_controller.dart';

class StrategyLiveAutoBuyCard extends StatelessWidget {
  const StrategyLiveAutoBuyCard({
    super.key,
    required this.readiness,
    required this.latest,
    required this.recent,
    required this.loading,
    required this.error,
    required this.onRun,
    required this.onRefresh,
  });

  final StrategyLiveAutoBuyReadiness? readiness;
  final StrategyLiveAutoBuyRunResult? latest;
  final List<StrategyLiveAutoBuyRunResult> recent;
  final bool loading;
  final String? error;
  final Future<ActionResult> Function() onRun;
  final Future<ActionResult> Function() onRefresh;

  @override
  Widget build(BuildContext context) {
    final ready = readiness?.ready == true;
    final color = ready
        ? Colors.greenAccent
        : latest?.submitted == true
            ? Colors.lightBlueAccent
            : Colors.orangeAccent;
    final runEnabled = ready && !loading;

    return SectionCard(
      key: const ValueKey('strategy-live-auto-buy-card'),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(Icons.verified_user_outlined, color: color, size: 20),
          const SizedBox(width: 8),
          const Expanded(
            child: Text(
              'Profile-Aware Guarded Live Auto Buy',
              style: TextStyle(fontSize: 17, fontWeight: FontWeight.w900),
            ),
          ),
        ]),
        const SizedBox(height: 8),
        Wrap(spacing: 6, runSpacing: 6, children: [
          const _Badge(text: 'LIVE AUTO BUY'),
          const _Badge(text: 'DISABLED BY DEFAULT'),
          const _Badge(text: 'REQUIRES RECENT DRY RUN'),
          const _Badge(text: 'TARGET RISK GATED'),
          const _Badge(text: 'KIS VALIDATION REQUIRED'),
          const _Badge(text: 'ONE SHOT ONLY'),
          const _Badge(text: 'NO SCHEDULER'),
          const _Badge(text: 'NO AUTO RETRY'),
          _Badge(
            text: ready ? 'READY' : 'BLOCKED',
            color: ready ? Colors.greenAccent : Colors.orangeAccent,
          ),
        ]),
        const SizedBox(height: 10),
        Wrap(spacing: 8, runSpacing: 8, children: [
          FilledButton.icon(
            key: const ValueKey('strategy-live-auto-buy-run-once'),
            onPressed: runEnabled ? () => _confirmAndRun(context) : null,
            icon: loading
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.play_arrow),
            label: const Text('Run Guarded Live Buy Once'),
          ),
          OutlinedButton.icon(
            key: const ValueKey('strategy-live-auto-buy-refresh'),
            onPressed: loading ? null : () => _refresh(context),
            icon: const Icon(Icons.refresh),
            label: const Text('Refresh Live Buy Status'),
          ),
        ]),
        if (error != null) ...[
          const SizedBox(height: 10),
          Text(error!, style: const TextStyle(color: Colors.orangeAccent)),
        ],
        const SizedBox(height: 12),
        Wrap(spacing: 10, runSpacing: 8, children: [
          _Metric(
            label: 'Active profile',
            value: readiness?.activeProfile ?? latest?.activeProfile ?? '-',
          ),
          _Metric(
            label: 'Selected symbol',
            value: readiness?.selectedSymbol ?? latest?.symbol ?? '-',
          ),
          _Metric(
            label: 'Readiness',
            value: ready
                ? 'ready'
                : readiness?.primaryBlockReason ??
                    latest?.blockReason ??
                    'not_ready',
          ),
          _Metric(
            label: 'Dry-run age',
            value: readiness?.recentDryRunAgeMinutes == null
                ? '-'
                : '${readiness!.recentDryRunAgeMinutes!.toStringAsFixed(1)}m',
          ),
          _Metric(
            label: 'Orders today',
            value:
                '${readiness?.ordersUsedToday ?? 0}/${readiness?.maxOrdersPerDay ?? 0}',
          ),
          _Metric(
            label: 'Max notional',
            value: _money(readiness?.maxNotionalKrw),
          ),
          _Metric(
            label: 'Latest status',
            value: latest?.status ?? '-',
          ),
          _Metric(
            label: 'Latest attempt',
            value: '${latest?.attemptId ?? '-'}',
          ),
        ]),
        if (latest != null) ...[
          const SizedBox(height: 10),
          Text(
            latest!.submitted
                ? 'Submitted ${latest!.quantity ?? 0} shares, broker ${latest!.brokerOrderId ?? '-'}.'
                : 'Last result: ${latest!.blockReason ?? latest!.status}.',
            style: const TextStyle(color: Colors.white70, fontSize: 12),
          ),
        ],
        if (readiness?.gatingNotes.isNotEmpty == true) ...[
          const SizedBox(height: 8),
          for (final note in readiness!.gatingNotes.take(3))
            Padding(
              padding: const EdgeInsets.only(top: 3),
              child: Text(
                note,
                style: const TextStyle(color: Colors.white70, fontSize: 12),
              ),
            ),
        ],
        if (recent.isNotEmpty) ...[
          const SizedBox(height: 10),
          Text(
            'Recent guarded attempts: ${recent.length}',
            style: const TextStyle(color: Colors.white60, fontSize: 12),
          ),
        ],
      ]),
    );
  }

  Future<void> _confirmAndRun(BuildContext context) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Run Guarded Live Buy Once'),
        content: const Text(
          '이 작업은 실제 KIS 매수 주문을 제출할 수 있습니다. 최근 dry-run would_buy 결과, target-aware risk, KIS validation을 모두 다시 확인한 뒤 통과할 때만 주문합니다. 계속할까요?',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            key: const ValueKey('strategy-live-auto-buy-confirm-run'),
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Run Once'),
          ),
        ],
      ),
    );
    if (confirmed != true || !context.mounted) return;
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
        Text(
          label,
          style: const TextStyle(color: Colors.white54, fontSize: 11),
        ),
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

String _money(double? value) =>
    value == null ? '-' : 'KRW ${value.toStringAsFixed(0)}';
