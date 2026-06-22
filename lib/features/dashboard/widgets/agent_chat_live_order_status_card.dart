import 'package:flutter/material.dart';

import '../../../models/agent_chat_live_order_action.dart';

class AgentChatLiveOrderStatusCard extends StatelessWidget {
  const AgentChatLiveOrderStatusCard({
    super.key,
    required this.action,
    required this.busy,
    required this.onRefresh,
    required this.onCancel,
    this.compact = false,
  });

  final AgentChatLiveOrderAction action;
  final bool busy;
  final Future<void> Function(AgentChatLiveOrderAction action) onRefresh;
  final Future<void> Function(AgentChatLiveOrderAction action) onCancel;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final canRefresh = action.isRefreshable && !busy;
    final canCancel = action.isPending && !busy;
    return Container(
      key: const ValueKey('agent-chat-live-order-status-card'),
      width: double.infinity,
      margin: const EdgeInsets.only(top: 10),
      padding: EdgeInsets.all(compact ? 10 : 12),
      decoration: BoxDecoration(
        color: _statusColor(action.status).withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: _statusColor(action.status).withValues(alpha: 0.35),
        ),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Icon(_statusIcon(action.status),
              color: _statusColor(action.status), size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              'Live Order Status: ${_statusLabel(action.status)}',
              style: const TextStyle(
                fontWeight: FontWeight.w900,
                color: Colors.white,
              ),
            ),
          ),
        ]),
        SizedBox(height: compact ? 8 : 10),
        _StatusRows(action: action, compact: compact),
        if (action.safetyControls.isNotEmpty) ...[
          SizedBox(height: compact ? 8 : 10),
          _SafetyControls(action: action, compact: compact),
        ],
        const SizedBox(height: 10),
        Wrap(spacing: 8, runSpacing: 8, children: [
          OutlinedButton.icon(
            key: const ValueKey('agent-chat-live-order-refresh-status'),
            onPressed: canRefresh ? () => onRefresh(action) : null,
            icon: busy
                ? const SizedBox(
                    width: 14,
                    height: 14,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.sync, size: 16),
            label: const Text('Refresh Status'),
          ),
          if (action.isPending)
            OutlinedButton.icon(
              key: const ValueKey('agent-chat-live-order-status-cancel'),
              onPressed: canCancel ? () => onCancel(action) : null,
              icon: const Icon(Icons.cancel_outlined, size: 16),
              label: const Text('Cancel Pending Action'),
            ),
        ]),
      ]),
    );
  }
}

class _StatusRows extends StatelessWidget {
  const _StatusRows({required this.action, required this.compact});

  final AgentChatLiveOrderAction action;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final rows = [
      ('Symbol', action.displayName),
      ('Side', action.side.toUpperCase()),
      ('Quantity', _formatQuantity(action.quantity)),
      ('Estimated Notional', _formatMoney(action.estimatedNotional, action.currency)),
      ('Broker Order', action.brokerOrderId ?? '-'),
      ('Broker Status', action.brokerStatus ?? action.internalStatus ?? '-'),
      ('Last Sync', action.lastSyncAt ?? '-'),
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

class _SafetyControls extends StatelessWidget {
  const _SafetyControls({required this.action, required this.compact});

  final AgentChatLiveOrderAction action;
  final bool compact;

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
      Wrap(
        spacing: 6,
        runSpacing: 6,
        children: [
          for (final row in rows)
            _ControlChip(
              label: row.$1,
              value: _controlValue(row.$2),
              warning: _isWarningControl(row.$1, row.$2),
            ),
        ],
      ),
    ]);
  }
}

class _ControlChip extends StatelessWidget {
  const _ControlChip({
    required this.label,
    required this.value,
    required this.warning,
  });

  final String label;
  final String value;
  final bool warning;

  @override
  Widget build(BuildContext context) {
    final color = warning ? Colors.orangeAccent : Colors.lightBlueAccent;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.35)),
      ),
      child: Text(
        '$label: $value',
        style: TextStyle(
          color: color,
          fontSize: 10,
          fontWeight: FontWeight.w900,
        ),
      ),
    );
  }
}

bool _isWarningControl(String key, Object? value) {
  if (key == 'dry_run' || key == 'kill_switch') return value == true;
  if (key == 'kis_enabled' ||
      key == 'kis_real_order_enabled' ||
      key == 'chat_live_order' ||
      key == 'market_open' ||
      key == 'entry_allowed_now') {
    return value == false;
  }
  return false;
}

Color _statusColor(String status) {
  switch (status) {
    case 'filled':
      return Colors.greenAccent;
    case 'submitted':
    case 'partially_filled':
      return Colors.lightBlueAccent;
    case 'blocked':
    case 'failed':
    case 'rejected':
    case 'sync_required':
      return Colors.orangeAccent;
    case 'cancelled':
    case 'expired':
      return Colors.white54;
    default:
      return Colors.redAccent;
  }
}

IconData _statusIcon(String status) {
  switch (status) {
    case 'filled':
      return Icons.check_circle_outline;
    case 'submitted':
    case 'partially_filled':
      return Icons.cloud_done_outlined;
    case 'blocked':
    case 'failed':
    case 'rejected':
    case 'sync_required':
      return Icons.report_problem_outlined;
    case 'cancelled':
    case 'expired':
      return Icons.cancel_outlined;
    default:
      return Icons.pending_actions_outlined;
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
