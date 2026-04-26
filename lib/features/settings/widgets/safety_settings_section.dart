import 'package:flutter/material.dart';

import '../../../core/widgets/section_card.dart';
import '../../dashboard/dashboard_controller.dart';

class SafetySettingsSection extends StatelessWidget {
  const SafetySettingsSection({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final s = controller.settings;
    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('Safety Limits', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
        const SizedBox(height: 8),
        Text('Broker Mode: ${s.brokerMode}'),
        Text('Max Daily Trades: ${s.maxDailyTrades}'),
        Text('Max Daily Entries: ${s.maxDailyEntries}'),
        Text('Watchlist Min Entry Score: ${s.minEntryScore}'),
        Text('Watchlist Min Score Gap: ${s.minScoreGap}'),
      ]),
    );
  }
}
