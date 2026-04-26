import 'package:flutter/material.dart';

import '../../../core/widgets/section_card.dart';
import '../../dashboard/dashboard_controller.dart';

class QuickActionsSection extends StatelessWidget {
  const QuickActionsSection({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return Column(children: [
      SectionCard(
        child: Column(children: [
          const Text('EMERGENCY PROTOCOL', style: TextStyle(color: Colors.redAccent, fontWeight: FontWeight.w700, fontSize: 11)),
          const SizedBox(height: 8),
          const Text('KILL SWITCH', style: TextStyle(fontSize: 26, fontWeight: FontWeight.w700)),
          const SizedBox(height: 12),
          FilledButton.icon(
            style: FilledButton.styleFrom(backgroundColor: Colors.red.shade800, minimumSize: const Size.fromHeight(46)),
            onPressed: () => controller.toggleKillSwitch(!controller.settings.killSwitch),
            icon: const Icon(Icons.power_settings_new),
            label: Text(controller.settings.killSwitch ? 'TURN OFF KILL SWITCH' : 'HALT ALL TRADING'),
          )
        ]),
      ),
      const SizedBox(height: 12),
      SectionCard(
        child: Column(children: [
          FilledButton.tonalIcon(
            onPressed: controller.runOnce,
            icon: const Icon(Icons.play_arrow),
            label: const Text('Run Watchlist Once'),
          ),
          const SizedBox(height: 8),
          Row(children: [
            Expanded(child: OutlinedButton(onPressed: () => controller.toggleScheduler(!controller.settings.schedulerEnabled), child: Text(controller.settings.schedulerEnabled ? 'Scheduler OFF' : 'Scheduler ON'))),
            const SizedBox(width: 8),
            Expanded(child: OutlinedButton(onPressed: () => controller.toggleBot(!controller.settings.botEnabled), child: Text(controller.settings.botEnabled ? 'Bot OFF' : 'Bot ON'))),
          ])
        ]),
      )
    ]);
  }
}
