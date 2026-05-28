import 'dart:convert';

import 'package:flutter/material.dart';

import '../../../core/utils/timestamp_formatter.dart';
import '../../../core/widgets/section_card.dart';
import '../../../models/automation_runtime_monitor.dart';
import '../../dashboard/dashboard_controller.dart';

class AutomationEventTimelineCard extends StatefulWidget {
  const AutomationEventTimelineCard({
    super.key,
    required this.controller,
  });

  final DashboardController controller;

  @override
  State<AutomationEventTimelineCard> createState() =>
      _AutomationEventTimelineCardState();
}

class _AutomationEventTimelineCardState
    extends State<AutomationEventTimelineCard> {
  bool _showOlder = false;

  @override
  Widget build(BuildContext context) {
    final events =
        widget.controller.automationRuntimeMonitor?.events ?? const [];
    final visible = _showOlder ? events : events.take(10).toList();

    return SectionCard(
      key: const Key('automation_event_timeline_card'),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.timeline_outlined, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              'Latest Automation Events',
              style: Theme.of(context).textTheme.titleMedium,
            ),
          ),
          _CountBadge(text: '${events.length} events'),
        ]),
        const SizedBox(height: 10),
        if (events.isEmpty)
          const Text(
            'No automation events loaded yet.',
            style: TextStyle(color: Colors.white60),
          )
        else ...[
          for (final event in visible) ...[
            _AutomationEventRow(event: event),
            if (event != visible.last) const SizedBox(height: 8),
          ],
          if (events.length > 10) ...[
            const SizedBox(height: 10),
            OutlinedButton.icon(
              key: const ValueKey('automation-events-show-older'),
              onPressed: () => setState(() => _showOlder = !_showOlder),
              icon: Icon(
                _showOlder ? Icons.expand_less : Icons.expand_more,
                size: 18,
              ),
              label:
                  Text(_showOlder ? 'Hide older events' : 'Show older events'),
            ),
          ],
        ],
      ]),
    );
  }
}

class _AutomationEventRow extends StatelessWidget {
  const _AutomationEventRow({required this.event});

  final AutomationEvent event;

  @override
  Widget build(BuildContext context) {
    final color = _severityColor(event.severity);
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.28)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Wrap(
            spacing: 8,
            runSpacing: 6,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              _SoftBadge(
                  text: event.providerLabel, color: _providerColor(event)),
              _SoftBadge(text: _categoryLabel(event), color: color),
              if (event.symbol != null)
                _SoftBadge(text: event.symbol!, color: Colors.white70),
              Text(
                formatTimestampWithKst(event.timestamp),
                style: const TextStyle(
                  color: Colors.white60,
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ]),
        const SizedBox(height: 8),
        Text(
          _eventSummary(event),
          style: const TextStyle(fontWeight: FontWeight.w800),
        ),
        const SizedBox(height: 6),
        Wrap(spacing: 12, runSpacing: 6, children: [
          _DataPair(label: 'Action', value: event.action.toUpperCase()),
          _DataPair(label: 'Trigger', value: event.trigger.toUpperCase()),
          _DataPair(
              label: 'Result',
              value: event.result.isEmpty ? 'n/a' : event.result),
          if (event.blockReason != null)
            _DataPair(label: 'Block Reason', value: event.blockReason!),
          if (event.kisOdno != null)
            _DataPair(label: 'ODNO', value: event.kisOdno!),
          if (event.brokerOrderId != null)
            _DataPair(label: 'Broker Order', value: event.brokerOrderId!),
          if (event.orderId != null)
            _DataPair(label: 'Order ID', value: event.orderId!),
        ]),
        const SizedBox(height: 4),
        _DeveloperDetails(event: event),
      ]),
    );
  }
}

class _DeveloperDetails extends StatelessWidget {
  const _DeveloperDetails({required this.event});

  final AutomationEvent event;

  @override
  Widget build(BuildContext context) {
    return ExpansionTile(
      tilePadding: EdgeInsets.zero,
      childrenPadding: EdgeInsets.zero,
      title: const Text(
        'Developer Details',
        style: TextStyle(
          color: Colors.white70,
          fontSize: 12,
          fontWeight: FontWeight.w800,
        ),
      ),
      children: [
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(
            color: Colors.black.withValues(alpha: 0.22),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
          ),
          child: SelectableText(
            const JsonEncoder.withIndent('  ').convert({
              'id': event.id,
              'provider': event.provider,
              'market': event.market,
              'category': event.category,
              'severity': event.severity,
              'mode': event.mode,
              'source': event.source,
              'trigger_source': event.triggerSource,
              'real_order_submitted': event.realOrderSubmitted,
              'broker_submit_called': event.brokerSubmitCalled,
              'manual_submit_called': event.manualSubmitCalled,
              'developer_payload': event.developerPayload,
            }),
            style: const TextStyle(
              color: Colors.white70,
              fontSize: 11,
              fontFamily: 'monospace',
            ),
          ),
        ),
      ],
    );
  }
}

class _DataPair extends StatelessWidget {
  const _DataPair({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return ConstrainedBox(
      constraints: const BoxConstraints(minWidth: 92, maxWidth: 220),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(
          label.toUpperCase(),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(
            color: Colors.white54,
            fontSize: 10,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 3),
        Text(
          value,
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 13,
            fontWeight: FontWeight.w700,
          ),
        ),
      ]),
    );
  }
}

class _SoftBadge extends StatelessWidget {
  const _SoftBadge({required this.text, required this.color});

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
          fontSize: 11,
          fontWeight: FontWeight.w800,
        ),
      ),
    );
  }
}

class _CountBadge extends StatelessWidget {
  const _CountBadge({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 6),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.07),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
      ),
      child: Text(
        text,
        style: const TextStyle(
          color: Colors.white70,
          fontSize: 11,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }
}

String _categoryLabel(AutomationEvent event) {
  switch (event.category) {
    case 'trigger_detected':
      return 'TRIGGER DETECTED';
    case 'blocked':
      return 'BLOCKED';
    case 'order_submitted':
      return 'ORDER SUBMITTED';
    case 'order_filled':
      return 'FILLED';
    case 'order_rejected':
      return 'REJECTED';
    case 'dry_run_simulated':
      return 'DRY RUN';
    case 'settings_changed':
      return 'SETTINGS CHANGED';
    case 'portfolio_check':
      return 'PORTFOLIO CHECK';
    default:
      return 'SCHEDULER RUN';
  }
}

String _eventSummary(AutomationEvent event) {
  final symbol = event.symbol == null ? '' : '${event.symbol} | ';
  if (event.category == 'settings_changed') {
    return 'SYSTEM | ${event.result}: ${event.reason}';
  }
  final trigger = event.trigger == 'none'
      ? ''
      : '${event.trigger.toUpperCase()} trigger detected | ';
  final block =
      event.blockReason == null ? '' : 'blocked: ${event.blockReason} | ';
  final order = event.kisOdno == null ? '' : 'ODNO ${event.kisOdno} | ';
  return '${event.providerLabel} | $symbol$trigger$block$order${event.action.toUpperCase()} ${event.result}';
}

Color _severityColor(String severity) {
  switch (severity) {
    case 'success':
      return Colors.greenAccent;
    case 'warning':
      return Colors.orangeAccent;
    case 'danger':
      return Colors.redAccent;
    default:
      return Colors.white70;
  }
}

Color _providerColor(AutomationEvent event) {
  switch (event.providerLabel) {
    case 'KIS LIVE':
      return Colors.redAccent;
    case 'ALPACA PAPER':
      return Colors.lightBlueAccent;
    default:
      return Colors.white70;
  }
}
