import 'package:flutter/material.dart';

import '../dashboard_controller.dart';

class GlobalBrokerSelector extends StatelessWidget {
  const GlobalBrokerSelector({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final strings = controller.strings;
    return SegmentedButton<SelectedProvider>(
      key: const ValueKey('global-broker-selector'),
      showSelectedIcon: false,
      style: const ButtonStyle(
        visualDensity: VisualDensity.compact,
        tapTargetSize: MaterialTapTargetSize.padded,
        padding: WidgetStatePropertyAll(
          EdgeInsets.symmetric(horizontal: 8, vertical: 7),
        ),
        minimumSize: WidgetStatePropertyAll(Size(76, 40)),
      ),
      segments: [
        ButtonSegment(
          value: SelectedProvider.alpaca,
          tooltip: strings.brokerFullDisplayName('alpaca'),
          label: _BrokerOptionLabel(
            key: const ValueKey('broker-option-alpaca'),
            labelKey: const ValueKey('broker-option-alpaca-label'),
            text: strings.brokerCompactDisplayName('alpaca'),
          ),
          icon: const Icon(Icons.public, size: 16),
        ),
        ButtonSegment(
          value: SelectedProvider.kis,
          tooltip: strings.brokerFullDisplayName('kis'),
          label: _BrokerOptionLabel(
            key: const ValueKey('broker-option-kis'),
            labelKey: const ValueKey('broker-option-kis-label'),
            text: strings.brokerCompactDisplayName('kis'),
          ),
          icon: const Icon(Icons.account_balance, size: 16),
        ),
      ],
      selected: {controller.selectedProvider},
      onSelectionChanged: (selection) =>
          controller.setProvider(selection.first),
    );
  }
}

class _BrokerOptionLabel extends StatelessWidget {
  const _BrokerOptionLabel({
    super.key,
    required this.labelKey,
    required this.text,
  });

  final Key labelKey;
  final String text;

  @override
  Widget build(BuildContext context) {
    return ConstrainedBox(
      constraints: const BoxConstraints(minWidth: 44, maxWidth: 72),
      child: Text(
        text,
        key: labelKey,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        softWrap: false,
        textAlign: TextAlign.center,
        style: const TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w800,
          letterSpacing: 0,
          height: 1.1,
        ),
      ),
    );
  }
}

class BrokerContextBadge extends StatelessWidget {
  const BrokerContextBadge({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final isKis = controller.selectedProvider == SelectedProvider.kis;
    final strings = controller.strings;
    final color = isKis ? Colors.redAccent : Colors.lightBlueAccent;
    return Container(
      key: const ValueKey('selected-broker-context-badge'),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.38)),
      ),
      child: Text(
        isKis ? strings.kisBrokerMarket : strings.alpacaBrokerMarket,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        softWrap: false,
        style: TextStyle(
          color: color,
          fontSize: 12,
          fontWeight: FontWeight.w800,
        ),
      ),
    );
  }
}
