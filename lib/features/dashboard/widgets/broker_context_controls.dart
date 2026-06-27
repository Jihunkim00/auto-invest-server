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
      segments: [
        ButtonSegment(
          value: SelectedProvider.alpaca,
          label: Text(strings.alpacaBroker),
          icon: const Icon(Icons.public, size: 16),
        ),
        ButtonSegment(
          value: SelectedProvider.kis,
          label: Text(strings.kisBroker),
          icon: const Icon(Icons.account_balance, size: 16),
        ),
      ],
      selected: {controller.selectedProvider},
      onSelectionChanged: (selection) =>
          controller.setProvider(selection.first),
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
        style: TextStyle(
          color: color,
          fontSize: 12,
          fontWeight: FontWeight.w800,
        ),
      ),
    );
  }
}
