import 'package:flutter/material.dart';

import '../../../models/agent_review_queue.dart';

class AgentReviewQueueItemCard extends StatelessWidget {
  const AgentReviewQueueItemCard({
    super.key,
    required this.item,
    required this.busy,
    required this.onOpenChat,
    required this.onRunSafeAction,
    required this.onPrepareTicket,
    required this.onMarkReviewed,
    required this.onDismiss,
  });

  final AgentReviewQueueItem item;
  final bool busy;
  final VoidCallback? onOpenChat;
  final VoidCallback? onRunSafeAction;
  final VoidCallback? onPrepareTicket;
  final VoidCallback onMarkReviewed;
  final VoidCallback onDismiss;

  @override
  Widget build(BuildContext context) {
    final details = [
      if (item.symbol != null) item.symbol!,
      if (item.side != null && item.side != 'none') item.side!.toUpperCase(),
      if (item.status != null) item.status!,
      if (item.riskLevel != null) item.riskLevel!,
    ].join(' · ');
    return Container(
      key: ValueKey('agent-review-queue-item-${item.queueKey}'),
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white12),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Expanded(
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(
                item.commandType ?? item.title,
                style:
                    const TextStyle(fontSize: 14, fontWeight: FontWeight.w900),
              ),
              const SizedBox(height: 4),
              Text(
                item.title,
                style: const TextStyle(color: Colors.white70, height: 1.25),
              ),
              if (details.isNotEmpty) ...[
                const SizedBox(height: 5),
                Text(
                  details,
                  style: const TextStyle(color: Colors.white54, fontSize: 12),
                ),
              ],
            ]),
          ),
          _PriorityBadge(priority: item.priority, queueType: item.queueType),
        ]),
        if (item.summary.isNotEmpty) ...[
          const SizedBox(height: 8),
          Text(
            item.summary,
            maxLines: 3,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(color: Colors.white70, height: 1.3),
          ),
        ],
        if (item.blockedReason != null) ...[
          const SizedBox(height: 8),
          Text(
            item.blockedReason!,
            style: const TextStyle(color: Colors.orangeAccent, fontSize: 12),
          ),
        ],
        const SizedBox(height: 8),
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: [
            for (final badge in item.safetyBadges) _SafetyBadge(text: badge),
            if (item.conversationKey != null)
              _SafetyBadge(text: _shortConversation(item.conversationKey!)),
          ],
        ),
        const SizedBox(height: 10),
        Wrap(spacing: 8, runSpacing: 8, children: [
          OutlinedButton.icon(
            key: ValueKey('agent-review-open-chat-${item.queueKey}'),
            onPressed: busy ? null : onOpenChat,
            icon: const Icon(Icons.chat_bubble_outline, size: 16),
            label: const Text('Open Chat'),
          ),
          if (item.canRunSafeAction)
            FilledButton.icon(
              key: ValueKey('agent-review-run-safe-${item.queueKey}'),
              onPressed: busy ? null : onRunSafeAction,
              icon: const Icon(Icons.play_arrow, size: 16),
              label: const Text('Run Safe Action'),
            ),
          if (item.canPrepareTicket)
            FilledButton.icon(
              key: ValueKey('agent-review-prepare-ticket-${item.queueKey}'),
              onPressed: busy ? null : onPrepareTicket,
              icon: const Icon(Icons.edit_note, size: 16),
              label: const Text('Prepare Ticket'),
            ),
          OutlinedButton.icon(
            key: ValueKey('agent-review-mark-reviewed-${item.queueKey}'),
            onPressed: busy ? null : onMarkReviewed,
            icon: const Icon(Icons.done, size: 16),
            label: const Text('Mark Reviewed'),
          ),
          OutlinedButton.icon(
            key: ValueKey('agent-review-dismiss-${item.queueKey}'),
            onPressed: busy ? null : onDismiss,
            icon: const Icon(Icons.archive_outlined, size: 16),
            label: const Text('Dismiss'),
          ),
        ]),
      ]),
    );
  }
}

class _PriorityBadge extends StatelessWidget {
  const _PriorityBadge({required this.priority, required this.queueType});

  final String priority;
  final String queueType;

  @override
  Widget build(BuildContext context) {
    final color = priority == 'high'
        ? Colors.redAccent
        : priority == 'medium'
            ? Colors.orangeAccent
            : Colors.lightBlueAccent;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: color.withValues(alpha: 0.35)),
      ),
      child: Text(
        '$queueType · $priority',
        style: TextStyle(color: color, fontSize: 11, fontWeight: FontWeight.w800),
      ),
    );
  }
}

class _SafetyBadge extends StatelessWidget {
  const _SafetyBadge({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 4),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: Colors.white12),
      ),
      child: Text(
        text,
        style: const TextStyle(fontSize: 10, fontWeight: FontWeight.w800),
      ),
    );
  }
}

String _shortConversation(String value) {
  if (value.length <= 14) return value;
  return '${value.substring(0, 10)}...';
}
