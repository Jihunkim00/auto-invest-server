import 'package:flutter/material.dart';

import '../../../core/widgets/section_card.dart';
import '../../../models/strategy_live_auto_buy.dart';
import '../dashboard_controller.dart';

class AgentChatLiveAutoBuyStatusCard extends StatelessWidget {
  const AgentChatLiveAutoBuyStatusCard({
    super.key,
    required this.readiness,
    required this.recent,
    required this.loading,
    required this.error,
    required this.onRefresh,
  });

  final StrategyLiveAutoBuyReadiness? readiness;
  final List<StrategyLiveAutoBuyRunResult> recent;
  final bool loading;
  final String? error;
  final Future<ActionResult> Function() onRefresh;

  @override
  Widget build(BuildContext context) {
    final ready = readiness?.ready == true;
    return SectionCard(
      key: const ValueKey('agent-chat-live-auto-buy-status-card'),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(
            Icons.chat_bubble_outline,
            color: ready ? Colors.greenAccent : Colors.lightBlueAccent,
            size: 20,
          ),
          const SizedBox(width: 8),
          const Expanded(
            child: Text(
              'Agent Chat Live Auto Buy Status',
              style: TextStyle(fontSize: 17, fontWeight: FontWeight.w900),
            ),
          ),
          OutlinedButton.icon(
            key: const ValueKey('agent-chat-live-auto-buy-refresh'),
            onPressed: loading ? null : () => _refresh(context),
            icon: const Icon(Icons.refresh, size: 18),
            label: const Text('Refresh'),
          ),
        ]),
        const SizedBox(height: 8),
        Wrap(spacing: 6, runSpacing: 6, children: [
          const _Badge(text: 'READ ONLY'),
          const _Badge(text: 'LIVE AUTO BUY'),
          const _Badge(text: 'NO CHAT EXECUTION'),
          const _Badge(text: 'NO VALIDATION'),
          const _Badge(text: 'NO BROKER SUBMIT'),
          _Badge(
            text: ready ? 'READY' : 'BLOCKED',
            color: ready ? Colors.greenAccent : Colors.orangeAccent,
          ),
        ]),
        if (error != null) ...[
          const SizedBox(height: 10),
          Text(error!, style: const TextStyle(color: Colors.orangeAccent)),
        ],
        const SizedBox(height: 10),
        Wrap(spacing: 10, runSpacing: 8, children: [
          _Metric(
            label: 'Readiness',
            value: ready
                ? 'ready'
                : readiness?.primaryBlockReason ?? 'not_ready',
          ),
          _Metric(
            label: 'Active profile',
            value: readiness?.activeProfile ?? '-',
          ),
          _Metric(
            label: 'Recent dry-run',
            value: readiness?.recentDryRunFound == true ? 'found' : 'missing',
          ),
          _Metric(
            label: 'Recent attempts',
            value: '${recent.length}',
          ),
        ]),
      ]),
    );
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
      width: 140,
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
