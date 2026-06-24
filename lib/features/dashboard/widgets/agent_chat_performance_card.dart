import 'package:flutter/material.dart';

import '../../../models/agent_chat_tool_result.dart';

class AgentChatPerformanceCard extends StatelessWidget {
  const AgentChatPerformanceCard({super.key, required this.card});

  final AgentChatResultCard card;

  @override
  Widget build(BuildContext context) {
    return Container(
      key: ValueKey('agent-chat-performance-card-${card.cardType}'),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.lightBlueAccent.withValues(alpha: 0.07),
        borderRadius: BorderRadius.circular(8),
        border:
            Border.all(color: Colors.lightBlueAccent.withValues(alpha: 0.25)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(
          card.title,
          style: const TextStyle(fontWeight: FontWeight.w900),
        ),
        if (card.subtitle != null) ...[
          const SizedBox(height: 3),
          Text(card.subtitle!,
              style: const TextStyle(color: Colors.white60, fontSize: 12)),
        ],
        if (card.primaryValue != null) ...[
          const SizedBox(height: 8),
          Text(
            card.primaryValue!,
            style: const TextStyle(
              color: Colors.lightBlueAccent,
              fontSize: 17,
              fontWeight: FontWeight.w900,
            ),
          ),
        ],
        if (card.rows.isNotEmpty) ...[
          const SizedBox(height: 8),
          for (final row in card.rows.take(6))
            Padding(
              padding: const EdgeInsets.only(top: 3),
              child: Row(children: [
                Expanded(
                  child: Text(
                    row['label']?.toString() ?? '',
                    style: const TextStyle(color: Colors.white60, fontSize: 12),
                  ),
                ),
                const SizedBox(width: 8),
                Flexible(
                  child: Text(
                    row['value']?.toString() ?? '-',
                    textAlign: TextAlign.right,
                    style: const TextStyle(fontSize: 12),
                  ),
                ),
              ]),
            ),
        ],
        const SizedBox(height: 8),
        Wrap(spacing: 5, runSpacing: 5, children: [
          for (final badge in card.badges)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 4),
              decoration: BoxDecoration(
                color: Colors.lightBlueAccent.withValues(alpha: 0.10),
                borderRadius: BorderRadius.circular(999),
              ),
              child: Text(
                badge,
                style: const TextStyle(
                  color: Colors.lightBlueAccent,
                  fontSize: 10,
                  fontWeight: FontWeight.w900,
                ),
              ),
            ),
        ]),
      ]),
    );
  }
}
