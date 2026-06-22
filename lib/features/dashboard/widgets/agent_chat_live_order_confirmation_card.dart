import 'package:flutter/material.dart';

import '../../../models/agent_chat_live_order_action.dart';

class AgentChatLiveOrderConfirmationCard extends StatelessWidget {
  const AgentChatLiveOrderConfirmationCard({
    super.key,
    required this.action,
    required this.busy,
    required this.onConfirm,
    required this.onCancel,
    this.compact = false,
  });

  final AgentChatLiveOrderAction action;
  final bool busy;
  final Future<void> Function(AgentChatLiveOrderAction action) onConfirm;
  final Future<void> Function(AgentChatLiveOrderAction action) onCancel;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final canAct = action.isPending && !busy;
    return Container(
      key: const ValueKey('agent-chat-live-order-card'),
      width: double.infinity,
      margin: const EdgeInsets.only(top: 10),
      padding: EdgeInsets.all(compact ? 10 : 12),
      decoration: BoxDecoration(
        color: Colors.redAccent.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.redAccent.withValues(alpha: 0.35)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Icon(Icons.warning_amber_rounded,
              color: Colors.orangeAccent, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              action.isPending
                  ? 'Live Order Confirmation Required'
                  : 'Live Order ${_statusLabel(action.status)}',
              style: const TextStyle(
                fontWeight: FontWeight.w900,
                color: Colors.white,
              ),
            ),
          ),
        ]),
        SizedBox(height: compact ? 8 : 10),
        _LiveOrderRows(action: action, compact: compact),
        if (action.safetyControls.isNotEmpty) ...[
          SizedBox(height: compact ? 8 : 10),
          _SafetyControls(action: action),
        ],
        SizedBox(height: compact ? 8 : 10),
        Text(
          action.isPending
              ? 'Confirming sends this action to the backend, where runtime settings, validation, duplicate checks, and risk limits run again before any KIS submit.'
              : 'This action is no longer pending. Buttons are disabled for terminal states.',
          style: const TextStyle(color: Colors.orangeAccent, height: 1.25),
        ),
        const SizedBox(height: 10),
        Wrap(spacing: 8, runSpacing: 8, children: [
          FilledButton.icon(
            key: const ValueKey('agent-chat-live-order-confirm'),
            onPressed: canAct ? () => _confirmWithDialog(context) : null,
            icon: busy
                ? const SizedBox(
                    width: 14,
                    height: 14,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.check_circle_outline, size: 16),
            label: const Text('Confirm Live Order'),
          ),
          OutlinedButton.icon(
            key: const ValueKey('agent-chat-live-order-cancel'),
            onPressed: canAct ? () => onCancel(action) : null,
            icon: const Icon(Icons.cancel_outlined, size: 16),
            label: const Text('Cancel'),
          ),
        ]),
      ]),
    );
  }

  Future<void> _confirmWithDialog(BuildContext context) async {
    final approved = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Confirm Live Order'),
        content: const Text(
          'This will submit a real KIS order if backend validation and risk gates pass. Continue?',
        ),
        actions: [
          TextButton(
            key: const ValueKey('agent-chat-live-order-dialog-cancel'),
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            key: const ValueKey('agent-chat-live-order-dialog-confirm'),
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Continue'),
          ),
        ],
      ),
    );
    if (approved == true) {
      await onConfirm(action);
    }
  }
}

class _SafetyControls extends StatelessWidget {
  const _SafetyControls({required this.action});

  final AgentChatLiveOrderAction action;

  @override
  Widget build(BuildContext context) {
    final controls = action.safetyControls;
    final rows = [
      ('dry_run', controls['dry_run']),
      ('kill_switch', controls['kill_switch']),
      ('kis_enabled', controls['kis_enabled']),
      ('kis_real_order_enabled', controls['kis_real_order_enabled']),
      ('chat_live_order', controls['agent_chat_live_order_enabled']),
      ('market_open', controls['market_open']),
      ('entry_allowed_now', controls['entry_allowed_now']),
      ('daily_limit_remaining', controls['daily_limit_remaining']),
      ('max_notional_limit', controls['max_notional_limit']),
    ];
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text(
        'Safety Controls',
        style: TextStyle(
          color: Colors.orangeAccent,
          fontWeight: FontWeight.w900,
          fontSize: 12,
        ),
      ),
      const SizedBox(height: 6),
      Wrap(spacing: 6, runSpacing: 6, children: [
        for (final row in rows)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
            decoration: BoxDecoration(
              color: Colors.orangeAccent.withValues(alpha: 0.10),
              borderRadius: BorderRadius.circular(999),
              border: Border.all(
                color: Colors.orangeAccent.withValues(alpha: 0.35),
              ),
            ),
            child: Text(
              '${row.$1}: ${_controlValue(row.$2)}',
              style: const TextStyle(
                color: Colors.orangeAccent,
                fontSize: 10,
                fontWeight: FontWeight.w900,
              ),
            ),
          ),
      ]),
    ]);
  }
}

class _LiveOrderRows extends StatelessWidget {
  const _LiveOrderRows({required this.action, required this.compact});

  final AgentChatLiveOrderAction action;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final rows = [
      ('Symbol', action.displayName),
      ('Side', action.side.toUpperCase()),
      ('Quantity', _formatQuantity(action.quantity)),
      ('Order Type', action.orderType.toUpperCase()),
      ('Estimated Price', _formatMoney(action.estimatedPrice, action.currency)),
      (
        'Estimated Notional',
        _formatMoney(action.estimatedNotional, action.currency)
      ),
      ('Provider', '${action.provider.toUpperCase()} / ${action.market}'),
      if (action.expiresAt != null) ('Expires', action.expiresAt!),
      ('Status', _statusLabel(action.status)),
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

String _statusLabel(String status) {
  final normalized = status.trim().replaceAll('_', ' ');
  if (normalized.isEmpty) return 'Unknown';
  return normalized
      .split(' ')
      .where((part) => part.isNotEmpty)
      .map((part) => '${part[0].toUpperCase()}${part.substring(1)}')
      .join(' ');
}

String _formatQuantity(double? value) {
  if (value == null) return '-';
  if (value == value.roundToDouble()) return value.toStringAsFixed(0);
  return value.toStringAsFixed(4).replaceFirst(RegExp(r'0+$'), '');
}

String _formatMoney(double? value, String currency) {
  if (value == null) return '-';
  final amount = value.round().toString();
  return '$currency ${_groupDigits(amount)}';
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

String _controlValue(Object? value) {
  if (value == null) return '-';
  if (value is bool) return value ? 'ON' : 'OFF';
  return value.toString();
}
