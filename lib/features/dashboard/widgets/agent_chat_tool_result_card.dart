import 'package:flutter/material.dart';

import '../../../models/agent_chat_tool_result.dart';

class AgentChatToolResultCardList extends StatelessWidget {
  const AgentChatToolResultCardList({
    super.key,
    required this.cards,
    required this.followUpSuggestions,
    this.onSuggestionSelected,
  });

  final List<AgentChatResultCard> cards;
  final List<String> followUpSuggestions;
  final ValueChanged<String>? onSuggestionSelected;

  @override
  Widget build(BuildContext context) {
    if (cards.isEmpty && followUpSuggestions.isEmpty) {
      return const SizedBox.shrink();
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      for (final card in cards) ...[
        AgentChatToolResultCard(card: card),
        const SizedBox(height: 8),
      ],
      if (followUpSuggestions.isNotEmpty)
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: [
            for (final suggestion in followUpSuggestions)
              ActionChip(
                key: ValueKey('agent-chat-follow-up-$suggestion'),
                label: Text(suggestion),
                onPressed: onSuggestionSelected == null
                    ? null
                    : () => onSuggestionSelected!(suggestion),
                visualDensity: VisualDensity.compact,
              ),
          ],
        ),
    ]);
  }
}

class AgentChatToolResultCard extends StatelessWidget {
  const AgentChatToolResultCard({super.key, required this.card});

  final AgentChatResultCard card;

  @override
  Widget build(BuildContext context) {
    return Container(
      key: ValueKey('agent-chat-result-card-${card.cardType}'),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.22),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  card.title,
                  style: const TextStyle(
                    fontWeight: FontWeight.w900,
                    height: 1.2,
                  ),
                ),
                if (card.subtitle != null) ...[
                  const SizedBox(height: 3),
                  Text(
                    card.subtitle!,
                    style: const TextStyle(
                      color: Colors.white60,
                      fontSize: 12,
                      height: 1.2,
                    ),
                  ),
                ],
              ],
            ),
          ),
          if (card.primaryValue != null) ...[
            const SizedBox(width: 10),
            Text(
              card.primaryValue!,
              style: const TextStyle(
                color: Colors.lightBlueAccent,
                fontWeight: FontWeight.w900,
                fontSize: 16,
              ),
            ),
          ],
        ]),
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
                Text(
                  row['value']?.toString() ?? '-',
                  style: const TextStyle(fontSize: 12),
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
                _ResultBadge(text: badge),
            ],
          ),
        ],
      ]),
    );
  }
}

class _ResultBadge extends StatelessWidget {
  const _ResultBadge({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 4),
      decoration: BoxDecoration(
        color: Colors.lightBlueAccent.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: Colors.lightBlueAccent.withValues(alpha: 0.28)),
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
