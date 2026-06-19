import 'package:flutter/material.dart';

import '../../../core/widgets/section_card.dart';
import '../dashboard_controller.dart';
import 'agent_review_queue_item_card.dart';

const _agentQueueFilters = <String, String>{
  'all': 'All',
  'auth_required': 'Auth Required',
  'blocked': 'Blocked',
  'prefill_ready': 'Prefill Ready',
  'safe_run_completed': 'Safe Runs',
  'failed': 'Failed',
};

class AgentReviewQueuePanel extends StatefulWidget {
  const AgentReviewQueuePanel({super.key, required this.controller});

  final DashboardController controller;

  @override
  State<AgentReviewQueuePanel> createState() => _AgentReviewQueuePanelState();
}

class _AgentReviewQueuePanelState extends State<AgentReviewQueuePanel> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      widget.controller.refreshAgentReviewQueue();
    });
  }

  @override
  Widget build(BuildContext context) {
    final controller = widget.controller;
    final busy = controller.isLoadingAgentReviewQueue ||
        controller.isAgentRunning ||
        controller.isAgentPreparingTicket;
    return SectionCard(
      padding: const EdgeInsets.all(14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.rule_folder_outlined, size: 20),
          const SizedBox(width: 8),
          const Expanded(
            child: Text(
              'Agent Review Queue',
              style: TextStyle(fontSize: 17, fontWeight: FontWeight.w900),
            ),
          ),
          IconButton(
            key: const ValueKey('agent-review-queue-refresh'),
            tooltip: 'Refresh Agent Review Queue',
            onPressed: busy ? null : controller.refreshAgentReviewQueue,
            icon: const Icon(Icons.refresh, size: 18),
          ),
        ]),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final entry in _agentQueueFilters.entries)
              ChoiceChip(
                key: ValueKey('agent-review-filter-${entry.key}'),
                label: Text(entry.value),
                selected: controller.selectedAgentQueueFilter == entry.key,
                onSelected: busy
                    ? null
                    : (_) =>
                        controller.refreshAgentReviewQueue(filter: entry.key),
              ),
          ],
        ),
        if (controller.isLoadingAgentReviewQueue) ...[
          const SizedBox(height: 10),
          const Text(
            'Refreshing review queue...',
            style: TextStyle(color: Colors.lightBlueAccent, fontSize: 12),
          ),
        ],
        const SizedBox(height: 12),
        if (controller.agentReviewQueue.items.isEmpty)
          const Text(
            'No open Agent review queue items.',
            style: TextStyle(color: Colors.white70),
          )
        else
          for (final item in controller.agentReviewQueue.items)
            AgentReviewQueueItemCard(
              item: item,
              busy: busy,
              onOpenChat: item.canOpenChat
                  ? () => _runAction(
                        context,
                        controller.openAgentConversationFromQueue(
                          item.conversationKey,
                        ),
                      )
                  : null,
              onRunSafeAction: item.canRunSafeAction
                  ? () => _runAction(
                        context,
                        controller.runSafeActionFromQueue(item.planId),
                      )
                  : null,
              onPrepareTicket: item.canPrepareTicket
                  ? () => _runAction(
                        context,
                        controller.prepareTicketFromQueue(item.planId),
                      )
                  : null,
              onMarkReviewed: () => _runAction(
                context,
                controller.markAgentQueueItemReviewed(item.queueKey),
              ),
              onDismiss: () => _runAction(
                context,
                controller.dismissAgentQueueItem(item.queueKey),
              ),
            ),
      ]),
    );
  }

  Future<void> _runAction(
    BuildContext context,
    Future<ActionResult> future,
  ) async {
    final result = await future;
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(result.message)),
    );
  }
}
