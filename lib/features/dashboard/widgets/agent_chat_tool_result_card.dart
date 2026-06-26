import 'package:flutter/material.dart';

import '../../../models/agent_chat_tool_result.dart';
import 'agent_chat_auto_buy_operations_card.dart';
import 'agent_chat_performance_card.dart';
import 'agent_chat_strategy_risk_card.dart';
import 'agent_chat_dry_run_auto_buy_card.dart';

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
        if (_isPerformanceCard(card.cardType))
          AgentChatPerformanceCard(card: card)
        else if (_isStrategyRiskCard(card.cardType))
          AgentChatStrategyRiskCard(card: card)
        else if (_isDryRunAutoBuyCard(card.cardType))
          AgentChatDryRunAutoBuyCard(card: card)
        else if (_isAutoBuyOperationsCard(card.cardType))
          AgentChatAutoBuyOperationsCard(card: card)
        else
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
                label: Text(
                  suggestion,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
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

bool _isStrategyRiskCard(String cardType) {
  return cardType == 'strategy_risk_state' ||
      cardType == 'strategy_entry_risk' ||
      cardType == 'strategy_order_sizing';
}

bool _isDryRunAutoBuyCard(String cardType) {
  return cardType == 'strategy_dry_run_auto_buy' ||
      cardType == 'strategy_dry_run_auto_buy_recent' ||
      cardType == 'strategy_dry_run_auto_buy_summary';
}

bool _isAutoBuyOperationsCard(String cardType) {
  return cardType == 'strategy_auto_buy_operations_status';
}

bool _isPerformanceCard(String cardType) {
  return cardType == 'strategy_daily_performance' ||
      cardType == 'strategy_monthly_performance' ||
      cardType == 'strategy_trade_performance';
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
                  softWrap: true,
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
                    softWrap: true,
                  ),
                ],
              ],
            ),
          ),
          if (card.primaryValue != null) ...[
            const SizedBox(width: 10),
            Flexible(
              child: Text(
                card.primaryValue!,
                textAlign: TextAlign.right,
                overflow: TextOverflow.ellipsis,
                maxLines: 2,
                style: const TextStyle(
                  color: Colors.lightBlueAccent,
                  fontWeight: FontWeight.w900,
                  fontSize: 16,
                ),
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
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(color: Colors.white60, fontSize: 12),
                  ),
                ),
                const SizedBox(width: 8),
                Flexible(
                  child: Text(
                    row['value']?.toString() ?? '-',
                    textAlign: TextAlign.right,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
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
              for (final badge in card.badges) _ResultBadge(text: badge),
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
    final color = _badgeColor(text);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 4),
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

Color _badgeColor(String text) {
  final normalized = text.toUpperCase();
  if (normalized.contains('BLOCKED') || normalized.contains('AUTH')) {
    return Colors.orangeAccent;
  }
  if (normalized.contains('NO ') ||
      normalized.contains('READ ONLY') ||
      normalized.contains('MANUAL REVIEW')) {
    return Colors.lightBlueAccent;
  }
  if (normalized == 'KIS' || normalized == 'ALPACA') {
    return Colors.greenAccent;
  }
  return Colors.white70;
}
