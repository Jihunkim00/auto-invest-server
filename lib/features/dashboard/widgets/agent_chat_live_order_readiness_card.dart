import 'package:flutter/material.dart';

import '../../../models/agent_chat_live_order_readiness.dart';
import '../dashboard_controller.dart';

class AgentChatLiveOrderReadinessCard extends StatelessWidget {
  const AgentChatLiveOrderReadinessCard({
    super.key,
    required this.readiness,
    required this.loading,
    required this.error,
    required this.applyingPreset,
    required this.onRefresh,
    required this.onApplyPreset,
    this.compact = false,
  });

  final AgentChatLiveOrderReadiness? readiness;
  final bool loading;
  final String? error;
  final String? applyingPreset;
  final Future<ActionResult> Function() onRefresh;
  final Future<ActionResult> Function(String preset) onApplyPreset;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final value = readiness;
    final statusColor =
        value?.ready == true ? Colors.greenAccent : Colors.orangeAccent;
    return Container(
      key: const ValueKey('agent-chat-live-order-readiness-card'),
      width: double.infinity,
      margin: EdgeInsets.only(top: compact ? 8 : 10),
      padding: EdgeInsets.all(compact ? 10 : 12),
      decoration: BoxDecoration(
        color: statusColor.withValues(alpha: 0.07),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: statusColor.withValues(alpha: 0.28)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Icon(
            value?.ready == true
                ? Icons.verified_outlined
                : Icons.shield_outlined,
            color: statusColor,
            size: 18,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Agent Chat Live Order Readiness',
                  style: TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.w900,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  value?.summary ??
                      'Agent Chat live-order readiness has not been loaded.',
                  style: const TextStyle(color: Colors.white70, fontSize: 12),
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          _ReadinessPill(
            text: value?.ready == true ? 'READY' : 'BLOCKED',
            color: statusColor,
          ),
          IconButton(
            key: const ValueKey('agent-chat-live-order-readiness-refresh'),
            tooltip: 'Refresh readiness',
            onPressed: loading ? null : () => _runRefresh(context),
            icon: loading
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.refresh, size: 18),
          ),
        ]),
        const SizedBox(height: 10),
        _BadgeRow(readiness: value),
        if (error != null) ...[
          const SizedBox(height: 10),
          _WarningLine(message: error!, color: Colors.orangeAccent),
        ],
        if (value != null) ...[
          const SizedBox(height: 10),
          _LimitsRow(readiness: value),
          if (value.blockingChecks.isNotEmpty) ...[
            const SizedBox(height: 10),
            _BlockingReasons(checks: value.blockingChecks.take(4).toList()),
          ],
          const SizedBox(height: 10),
          _CheckWrap(checks: value.checks, compact: compact),
        ],
        const SizedBox(height: 12),
        _PresetButtons(
          applyingPreset: applyingPreset,
          onApplyPreset: (preset) => _confirmAndApply(context, preset),
        ),
      ]),
    );
  }

  Future<void> _runRefresh(BuildContext context) async {
    final result = await onRefresh();
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(result.message)),
    );
  }

  Future<void> _confirmAndApply(BuildContext context, String preset) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => _PresetConfirmDialog(preset: preset),
    );
    if (confirmed != true || !context.mounted) return;
    final result = await onApplyPreset(preset);
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(result.message)),
    );
  }
}

class _BadgeRow extends StatelessWidget {
  const _BadgeRow({required this.readiness});

  final AgentChatLiveOrderReadiness? readiness;

  @override
  Widget build(BuildContext context) {
    final value = readiness;
    final buyEnabled = value?.capabilities.buyEnabled == true;
    final sellEnabled = value?.capabilities.sellEnabled == true;
    return Wrap(spacing: 6, runSpacing: 6, children: [
      const _ReadinessPill(
        text: 'CONFIRM REQUIRED',
        color: Colors.lightBlueAccent,
      ),
      if (buyEnabled)
        const _ReadinessPill(text: 'BUY ENABLED', color: Colors.redAccent),
      if (sellEnabled)
        const _ReadinessPill(text: 'SELL ENABLED', color: Colors.orangeAccent),
      const _ReadinessPill(text: 'READINESS ONLY', color: Colors.greenAccent),
      const _ReadinessPill(
          text: 'NO AUTO SCHEDULER', color: Colors.greenAccent),
      const _ReadinessPill(
        text: 'NO BACKGROUND ORDERS',
        color: Colors.greenAccent,
      ),
    ]);
  }
}

class _LimitsRow extends StatelessWidget {
  const _LimitsRow({required this.readiness});

  final AgentChatLiveOrderReadiness readiness;

  @override
  Widget build(BuildContext context) {
    final limits = readiness.limits;
    return Wrap(spacing: 8, runSpacing: 8, children: [
      _Metric(label: 'Max/day', value: limits.maxOrdersPerDay.toString()),
      _Metric(label: 'Used today', value: limits.ordersUsedToday.toString()),
      _Metric(
        label: 'Remaining',
        value: limits.ordersRemainingToday.toString(),
      ),
      _Metric(
        label: 'Max KRW',
        value: _formatMoney(limits.maxNotionalKrw),
      ),
      _Metric(
        label: 'Max pct',
        value: _formatPct(limits.maxNotionalPct),
      ),
    ]);
  }
}

class _BlockingReasons extends StatelessWidget {
  const _BlockingReasons({required this.checks});

  final List<AgentChatLiveOrderReadinessCheck> checks;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text(
        'Blocking Reasons',
        style: TextStyle(
          color: Colors.orangeAccent,
          fontSize: 12,
          fontWeight: FontWeight.w900,
        ),
      ),
      const SizedBox(height: 5),
      for (final check in checks)
        Padding(
          padding: const EdgeInsets.only(bottom: 3),
          child: Text(
            '${check.label}: ${check.message}',
            style: const TextStyle(color: Colors.white70, fontSize: 12),
          ),
        ),
    ]);
  }
}

class _CheckWrap extends StatelessWidget {
  const _CheckWrap({required this.checks, required this.compact});

  final List<AgentChatLiveOrderReadinessCheck> checks;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final visible = checks.where((check) {
      return check.severity == 'blocking' ||
          check.key == 'dry_run' ||
          check.key == 'kill_switch' ||
          check.key == 'kis_enabled' ||
          check.key == 'kis_real_order_enabled' ||
          check.key == 'agent_chat_live_order_enabled' ||
          check.key == 'agent_chat_live_order_kis_enabled' ||
          check.key == 'agent_chat_live_order_buy_enabled' ||
          check.key == 'agent_chat_live_order_sell_enabled' ||
          check.key == 'scheduler_real_orders_disabled';
    }).toList(growable: false);
    return Wrap(
      spacing: 6,
      runSpacing: 6,
      children: [
        for (final check in visible.take(compact ? 10 : 16))
          _CheckChip(check: check),
      ],
    );
  }
}

class _PresetButtons extends StatelessWidget {
  const _PresetButtons({
    required this.applyingPreset,
    required this.onApplyPreset,
  });

  final String? applyingPreset;
  final ValueChanged<String> onApplyPreset;

  @override
  Widget build(BuildContext context) {
    const presets = [
      ('safe_off', 'Safe Off'),
      ('chat_confirmed_test', 'Chat Confirmed Test'),
      ('chat_confirmed_buy_only', 'Buy Only Guarded'),
      ('chat_confirmed_sell_only', 'Sell Only Guarded'),
      ('chat_confirmed_full_guarded', 'Full Guarded'),
    ];
    return Wrap(spacing: 8, runSpacing: 8, children: [
      for (final item in presets)
        OutlinedButton(
          key: ValueKey('agent-chat-live-order-preset-${item.$1}'),
          onPressed:
              applyingPreset == null ? () => onApplyPreset(item.$1) : null,
          child: applyingPreset == item.$1
              ? const SizedBox(
                  width: 14,
                  height: 14,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : Text(item.$2),
        ),
    ]);
  }
}

class _PresetConfirmDialog extends StatelessWidget {
  const _PresetConfirmDialog({required this.preset});

  final String preset;

  @override
  Widget build(BuildContext context) {
    final isFull = preset == 'chat_confirmed_full_guarded';
    return AlertDialog(
      key: const ValueKey('agent-chat-live-order-preset-confirm-dialog'),
      title: Text('Apply ${_presetLabel(preset)}?'),
      content: Text(
        isFull
            ? 'This sets both buy and sell chat-confirmed orders to enabled. Actual orders still require explicit chat confirmation plus backend validation and risk gates. No order is submitted by this preset.'
            : 'This preset changes only Agent Chat live-order settings. No order is submitted, no validation runs, and scheduler real orders are not enabled.',
      ),
      actions: [
        TextButton(
          key: const ValueKey('agent-chat-live-order-preset-cancel'),
          onPressed: () => Navigator.of(context).pop(false),
          child: const Text('Cancel'),
        ),
        FilledButton(
          key: const ValueKey('agent-chat-live-order-preset-apply'),
          onPressed: () => Navigator.of(context).pop(true),
          child: const Text('Apply Preset'),
        ),
      ],
    );
  }
}

class _Metric extends StatelessWidget {
  const _Metric({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 105,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(
          label,
          style: const TextStyle(color: Colors.white54, fontSize: 11),
        ),
        const SizedBox(height: 2),
        Text(
          value,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 12,
            fontWeight: FontWeight.w800,
          ),
        ),
      ]),
    );
  }
}

class _CheckChip extends StatelessWidget {
  const _CheckChip({required this.check});

  final AgentChatLiveOrderReadinessCheck check;

  @override
  Widget build(BuildContext context) {
    final color = _severityColor(check);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.34)),
      ),
      child: Text(
        '${check.label}: ${_displayValue(check.value)}',
        style: TextStyle(
          color: color,
          fontSize: 10,
          fontWeight: FontWeight.w900,
        ),
      ),
    );
  }
}

class _ReadinessPill extends StatelessWidget {
  const _ReadinessPill({required this.text, required this.color});

  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.34)),
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

class _WarningLine extends StatelessWidget {
  const _WarningLine({required this.message, required this.color});

  final String message;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Text(
      message,
      style: TextStyle(color: color, fontSize: 12, height: 1.25),
    );
  }
}

Color _severityColor(AgentChatLiveOrderReadinessCheck check) {
  if (check.ok) return Colors.greenAccent;
  switch (check.severity) {
    case 'blocking':
      return Colors.orangeAccent;
    case 'warning':
      return Colors.amberAccent;
    default:
      return Colors.white70;
  }
}

String _displayValue(Object? value) {
  if (value == null) return '-';
  if (value is bool) return value ? 'ON' : 'OFF';
  return value.toString();
}

String _formatMoney(double? value) {
  if (value == null) return '-';
  return 'KRW ${value.round()}';
}

String _formatPct(double? value) {
  if (value == null) return '-';
  return '${(value * 100).toStringAsFixed(1)}%';
}

String _presetLabel(String preset) {
  switch (preset) {
    case 'safe_off':
      return 'Safe Off';
    case 'chat_confirmed_test':
      return 'Chat Confirmed Test';
    case 'chat_confirmed_buy_only':
      return 'Buy Only Guarded';
    case 'chat_confirmed_sell_only':
      return 'Sell Only Guarded';
    case 'chat_confirmed_full_guarded':
      return 'Full Guarded';
  }
  return preset;
}
