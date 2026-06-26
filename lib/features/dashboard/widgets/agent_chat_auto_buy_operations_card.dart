import 'package:flutter/material.dart';

import '../../../models/agent_chat_tool_result.dart';

class AgentChatAutoBuyOperationsCard extends StatelessWidget {
  const AgentChatAutoBuyOperationsCard({super.key, required this.card});

  final AgentChatResultCard card;

  @override
  Widget build(BuildContext context) {
    return Container(
      key: const ValueKey('agent-chat-auto-buy-operations-card'),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.lightBlueAccent.withValues(alpha: 0.07),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: Colors.lightBlueAccent.withValues(alpha: 0.24),
        ),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.tune_outlined,
              color: Colors.lightBlueAccent, size: 18),
          const SizedBox(width: 7),
          Expanded(
            child: Text(
              card.title,
              style: const TextStyle(fontWeight: FontWeight.w900),
            ),
          ),
          if (card.primaryValue != null)
            Flexible(
              child: Text(
                card.primaryValue!,
                textAlign: TextAlign.right,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  color: Colors.lightBlueAccent,
                  fontWeight: FontWeight.w900,
                ),
              ),
            ),
        ]),
        if (card.subtitle != null) ...[
          const SizedBox(height: 4),
          Text(
            card.subtitle!,
            style: const TextStyle(color: Colors.white60, fontSize: 12),
          ),
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
              for (final badge in card.badges) _Badge(text: badge),
            ],
          ),
        ],
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
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 4),
      decoration: BoxDecoration(
        color: Colors.lightBlueAccent.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(
          color: Colors.lightBlueAccent.withValues(alpha: 0.28),
        ),
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
