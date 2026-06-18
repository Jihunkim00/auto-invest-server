import 'package:flutter/material.dart';

import '../../../core/widgets/section_card.dart';
import '../dashboard_controller.dart';

class AgentOperationsSummaryCard extends StatefulWidget {
  const AgentOperationsSummaryCard({super.key, required this.controller});

  final DashboardController controller;

  @override
  State<AgentOperationsSummaryCard> createState() =>
      _AgentOperationsSummaryCardState();
}

class _AgentOperationsSummaryCardState
    extends State<AgentOperationsSummaryCard> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      widget.controller.refreshAgentOperationsSummary();
    });
  }

  @override
  Widget build(BuildContext context) {
    final controller = widget.controller;
    final summary = controller.agentOperationsSnapshot?.summary;
    final safety = controller.agentOperationsSnapshot?.safety;
    return SectionCard(
      padding: const EdgeInsets.all(14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.fact_check_outlined, size: 20),
          const SizedBox(width: 8),
          const Expanded(
            child: Text(
              'Agent Operations',
              style: TextStyle(fontSize: 17, fontWeight: FontWeight.w900),
            ),
          ),
          IconButton(
            key: const ValueKey('agent-operations-refresh'),
            tooltip: 'Refresh Agent Operations',
            onPressed: controller.isLoadingAgentOperations
                ? null
                : controller.refreshAgentOperationsSummary,
            icon: const Icon(Icons.refresh, size: 18),
          ),
        ]),
        const SizedBox(height: 8),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _OpsBadge(text: 'READ ONLY'),
          _OpsBadge(text: 'NO AUTO SUBMIT'),
          _OpsBadge(text: 'SAFE REVIEW QUEUE'),
        ]),
        if (controller.isLoadingAgentOperations) ...[
          const SizedBox(height: 10),
          const Text(
            'Refreshing agent operations...',
            style: TextStyle(color: Colors.lightBlueAccent, fontSize: 12),
          ),
        ],
        if (controller.agentOperationsError != null) ...[
          const SizedBox(height: 10),
          Text(
            controller.agentOperationsError!,
            style: const TextStyle(color: Colors.orangeAccent, fontSize: 12),
          ),
        ],
        const SizedBox(height: 12),
        Wrap(spacing: 10, runSpacing: 10, children: [
          _MetricTile(
            label: 'Active Plans',
            value: '${summary?.activePlans ?? 0}',
          ),
          _MetricTile(
            label: 'Pending Auth',
            value: '${summary?.pendingAuthCount ?? 0}',
          ),
          _MetricTile(
            label: 'Blocked',
            value: '${summary?.blockedCount ?? 0}',
          ),
          _MetricTile(
            label: 'Prefill Ready',
            value: '${summary?.prefillReadyCount ?? 0}',
          ),
          _MetricTile(
            label: 'Safe Runs',
            value: '${summary?.safeRunCompletedCount ?? 0}',
          ),
          _MetricTile(
            label: 'Failed',
            value: '${summary?.failedCount ?? 0}',
          ),
          _MetricTile(
            label: 'Active Chats',
            value: '${summary?.activeConversationCount ?? 0}',
          ),
        ]),
        if (safety != null && !safety.noUnsafeAction) ...[
          const SizedBox(height: 10),
          const Text(
            'Safety flags changed. Review backend operations before acting.',
            style: TextStyle(color: Colors.redAccent, fontSize: 12),
          ),
        ],
      ]),
    );
  }
}

class _MetricTile extends StatelessWidget {
  const _MetricTile({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 118,
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 9),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white12),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(
          value,
          style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w900),
        ),
        const SizedBox(height: 3),
        Text(
          label,
          style: const TextStyle(color: Colors.white70, fontSize: 12),
        ),
      ]),
    );
  }
}

class _OpsBadge extends StatelessWidget {
  const _OpsBadge({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: Colors.greenAccent.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: Colors.greenAccent.withValues(alpha: 0.3)),
      ),
      child: Text(
        text,
        style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w800),
      ),
    );
  }
}
