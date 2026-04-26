import 'package:flutter/material.dart';

import '../../../core/widgets/section_card.dart';
import '../../dashboard/dashboard_controller.dart';

class QuickActionsSection extends StatelessWidget {
  const QuickActionsSection({
    super.key,
    required this.controller,
    required this.onRunOnce,
    required this.onToggleScheduler,
    required this.onToggleBot,
    required this.onToggleKillSwitch,
  });

  final DashboardController controller;
  final Future<void> Function() onRunOnce;
  final Future<void> Function() onToggleScheduler;
  final Future<void> Function() onToggleBot;
  final Future<void> Function() onToggleKillSwitch;

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
            onPressed: controller.isPending(SettingKey.killSwitch) ? null : onToggleKillSwitch,
            icon: controller.isPending(SettingKey.killSwitch)
                ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.power_settings_new),
            label: Text(controller.settings.killSwitch ? 'TURN OFF KILL SWITCH' : 'HALT ALL TRADING'),
          )
        ]),
      ),
      const SizedBox(height: 12),
      SectionCard(
        child: Column(children: [
          FilledButton.tonalIcon(
            onPressed: controller.runInProgress ? null : onRunOnce,
            icon: controller.runInProgress
                ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.play_arrow),
            label: Text(controller.runInProgress ? 'Running watchlist analysis...' : 'Run Watchlist Once'),
          ),
          if (controller.runInProgress) const Padding(
            padding: EdgeInsets.only(top: 8),
            child: LinearProgressIndicator(minHeight: 2),
          ),
          const SizedBox(height: 8),
          Row(children: [
            Expanded(
              child: OutlinedButton(
                onPressed: controller.isPending(SettingKey.scheduler) ? null : onToggleScheduler,
                child: controller.isPending(SettingKey.scheduler)
                    ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2))
                    : Text(controller.settings.schedulerEnabled ? 'Scheduler OFF' : 'Scheduler ON'),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: OutlinedButton(
                onPressed: controller.isPending(SettingKey.bot) ? null : onToggleBot,
                child: controller.isPending(SettingKey.bot)
                    ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2))
                    : Text(controller.settings.botEnabled ? 'Bot OFF' : 'Bot ON'),
              ),
            ),
          ])
        ]),
      )
    ]);
  }
}
