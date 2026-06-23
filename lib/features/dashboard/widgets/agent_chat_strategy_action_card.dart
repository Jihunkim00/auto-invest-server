import 'package:flutter/material.dart';

import '../../../models/agent_chat_strategy_action.dart';
import '../../../models/strategy_profile.dart';

class AgentChatStrategyActionCard extends StatelessWidget {
  const AgentChatStrategyActionCard({
    super.key,
    required this.action,
    required this.busy,
    required this.onConfirm,
    required this.onCancel,
    this.compact = false,
  });

  final AgentChatStrategyAction action;
  final bool busy;
  final Future<void> Function(AgentChatStrategyAction action) onConfirm;
  final Future<void> Function(AgentChatStrategyAction action) onCancel;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final canAct = action.isPending && !busy;
    final color = action.isAggressive ? Colors.orangeAccent : Colors.greenAccent;
    return Container(
      key: const ValueKey('agent-chat-strategy-action-card'),
      width: double.infinity,
      margin: const EdgeInsets.only(top: 10),
      padding: EdgeInsets.all(compact ? 10 : 12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.34)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Icon(
            action.isPending
                ? Icons.rule_folder_outlined
                : Icons.check_circle_outline,
            color: color,
            size: 18,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              action.isPending
                  ? 'Strategy Profile Confirmation Required'
                  : 'Strategy Profile ${_statusLabel(action.status)}',
              style: const TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.w900,
              ),
            ),
          ),
        ]),
        SizedBox(height: compact ? 8 : 10),
        _BadgeRow(action: action),
        SizedBox(height: compact ? 8 : 10),
        _StrategyRows(action: action, compact: compact),
        SizedBox(height: compact ? 8 : 10),
        Text(
          action.isAggressive
              ? '고수익형은 월 5% 이상을 목표로 하지만 손실 변동성이 커질 수 있습니다. 월 손실 -6% 또는 일일 손실 -1.5% 도달 시 거래가 제한됩니다. 이 설정은 주문을 즉시 실행하지 않습니다. 적용할까요?'
              : action.isPending
                  ? 'This applies only the strategy risk profile after confirmation. It does not place an order.'
                  : 'This profile action is no longer pending. Buttons are disabled for terminal states.',
          style: TextStyle(color: color, height: 1.25),
        ),
        const SizedBox(height: 10),
        Wrap(spacing: 8, runSpacing: 8, children: [
          FilledButton.icon(
            key: const ValueKey('agent-chat-strategy-action-confirm'),
            onPressed: canAct ? () => onConfirm(action) : null,
            icon: busy
                ? const SizedBox(
                    width: 14,
                    height: 14,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.check_circle_outline, size: 16),
            label: const Text('Apply Profile'),
          ),
          OutlinedButton.icon(
            key: const ValueKey('agent-chat-strategy-action-cancel'),
            onPressed: canAct ? () => onCancel(action) : null,
            icon: const Icon(Icons.cancel_outlined, size: 16),
            label: const Text('Cancel'),
          ),
        ]),
      ]),
    );
  }
}

class _BadgeRow extends StatelessWidget {
  const _BadgeRow({required this.action});

  final AgentChatStrategyAction action;

  @override
  Widget build(BuildContext context) {
    return Wrap(spacing: 6, runSpacing: 6, children: [
      const _ActionBadge(text: 'PROFILE ONLY'),
      const _ActionBadge(text: 'NO ORDER SUBMIT'),
      const _ActionBadge(text: 'CONFIRM REQUIRED'),
      const _ActionBadge(text: 'STRATEGY TARGET'),
      _ActionBadge(text: action.requestedProfile.toUpperCase()),
    ]);
  }
}

class _StrategyRows extends StatelessWidget {
  const _StrategyRows({required this.action, required this.compact});

  final AgentChatStrategyAction action;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final profile = action.requestedProfilePayload ?? action.activeProfile;
    final rows = [
      ('Profile', action.displayName),
      (
        'Target',
        profile == null
            ? strategyProfileLabel(action.requestedProfile)
            : _pctRange(profile),
      ),
      if (profile != null) ('Monthly loss cap', _pct(profile.monthlyMaxLossPct)),
      if (profile != null) ('Daily loss cap', _pct(profile.dailyMaxLossPct)),
      if (profile != null) ('Order limit', _money(profile.maxOrderNotionalKrw)),
      if (profile != null) ('Buy score', _score(profile.buyScoreThreshold)),
      ('Status', _statusLabel(action.status)),
      if (action.expiresAt != null) ('Expires', action.expiresAt!),
    ];
    return Wrap(
      spacing: compact ? 10 : 14,
      runSpacing: compact ? 6 : 8,
      children: [
        for (final row in rows)
          SizedBox(
            width: compact ? 150 : 190,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  row.$1,
                  style: const TextStyle(color: Colors.white54, fontSize: 11),
                ),
                const SizedBox(height: 2),
                Text(
                  row.$2,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.w800,
                    height: 1.2,
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }
}

class _ActionBadge extends StatelessWidget {
  const _ActionBadge({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: Colors.lightBlueAccent.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: Colors.lightBlueAccent.withValues(alpha: 0.34)),
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

String _statusLabel(String status) {
  final normalized = status.trim().replaceAll('_', ' ');
  if (normalized.isEmpty) return 'Unknown';
  return normalized
      .split(' ')
      .where((part) => part.isNotEmpty)
      .map((part) => '${part[0].toUpperCase()}${part.substring(1)}')
      .join(' ');
}

String _pctRange(StrategyProfile profile) {
  return '${_pct(profile.monthlyTargetMinPct)}-${_pct(profile.monthlyTargetMaxPct)}';
}

String _pct(double value) {
  final pct = value * 100;
  final text = pct.abs() >= 10 ? pct.toStringAsFixed(0) : pct.toStringAsFixed(1);
  return '$text%';
}

String _score(double value) {
  if (value == value.roundToDouble()) return value.toStringAsFixed(0);
  return value.toStringAsFixed(1);
}

String _money(double value) {
  return 'KRW ${_groupDigits(value.round().toString())}';
}

String _groupDigits(String value) {
  final buffer = StringBuffer();
  for (var i = 0; i < value.length; i += 1) {
    final fromEnd = value.length - i;
    buffer.write(value[i]);
    if (fromEnd > 1 && fromEnd % 3 == 1) buffer.write(',');
  }
  return buffer.toString();
}
