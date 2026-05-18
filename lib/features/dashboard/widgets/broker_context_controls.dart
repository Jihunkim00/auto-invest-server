import 'package:flutter/material.dart';

import '../dashboard_controller.dart';

class GlobalBrokerSelector extends StatelessWidget {
  const GlobalBrokerSelector({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return SegmentedButton<SelectedProvider>(
      key: const ValueKey('global-broker-selector'),
      showSelectedIcon: false,
      segments: const [
        ButtonSegment(
          value: SelectedProvider.alpaca,
          label: Text('Alpaca'),
          icon: Icon(Icons.public, size: 16),
        ),
        ButtonSegment(
          value: SelectedProvider.kis,
          label: Text('KIS'),
          icon: Icon(Icons.account_balance, size: 16),
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
        isKis ? 'KIS / KR' : 'Alpaca / US',
        style: TextStyle(
          color: color,
          fontSize: 12,
          fontWeight: FontWeight.w800,
        ),
      ),
    );
  }
}
