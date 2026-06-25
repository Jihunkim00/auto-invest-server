import 'package:flutter/material.dart';

import '../../../models/agent_chat_tool_result.dart';

class AgentChatDryRunAutoBuyCard extends StatelessWidget {
  const AgentChatDryRunAutoBuyCard({super.key, required this.card});

  final AgentChatResultCard card;

  @override
  Widget build(BuildContext context) {
    return Container(
      key: ValueKey('agent-chat-dry-run-auto-buy-card-${card.cardType}'),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.greenAccent.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.greenAccent.withValues(alpha: 0.24)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.science_outlined,
              color: Colors.greenAccent, size: 18),
          const SizedBox(width: 7),
          Expanded(
            child: Text(
              card.title,
              style: const TextStyle(fontWeight: FontWeight.w900),
            ),
          ),
          if (card.primaryValue != null)
            Text(
              card.primaryValue!,
              style: const TextStyle(
                color: Colors.greenAccent,
                fontWeight: FontWeight.w900,
              ),
            ),
        ]),
        if (card.subtitle != null) ...[
          const SizedBox(height: 4),
          Text(card.subtitle!,
              style: const TextStyle(color: Colors.white60, fontSize: 12)),
        ],
        if (card.rows.isNotEmpty) ...[
          const SizedBox(height: 8),
          for (final row in card.rows.take(5))
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
        if (card.badges.isNotEmpty) ...[
          const SizedBox(height: 8),
          Wrap(
            spacing: 5,
            runSpacing: 5,
            children: [
              for (final badge in card.badges)
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 7, vertical: 4),
                  decoration: BoxDecoration(
                    color: Colors.lightBlueAccent.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(999),
                    border: Border.all(
                      color: Colors.lightBlueAccent.withValues(alpha: 0.28),
                    ),
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
            ],
          ),
        ],
      ]),
    );
  }
}
