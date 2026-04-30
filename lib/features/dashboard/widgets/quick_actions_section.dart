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
            onPressed: controller.killSwitchLoading
                ? null
                : () async {
                    final result = await controller.toggleKillSwitch(!controller.settings.killSwitch);
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                      content: Text(result.message),
                      backgroundColor: result.success ? Colors.green : Colors.redAccent,
                    ));
                  },
            icon: controller.killSwitchLoading ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2.0, color: Colors.white)) : const Icon(Icons.power_settings_new),
            label: Text(controller.settings.killSwitch ? 'TURN OFF KILL SWITCH' : 'HALT ALL TRADING'),
          )
        ]),
      ),
      const SizedBox(height: 12),
      SectionCard(
        child: Column(children: [
          FilledButton.tonalIcon(
            onPressed: controller.runOnceLoading
                ? null
                : () async {
                    final result = await controller.runOnce();
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                      content: Text(result.message),
                      backgroundColor: result.success ? Colors.green : Colors.redAccent,
                    ));
                  },
            icon: controller.runOnceLoading ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2.0)) : const Icon(Icons.play_arrow),
            label: Text(controller.runOnceLoading ? 'Running watchlist analysis...' : 'Run Watchlist Once'),
          ),
          const SizedBox(height: 8),
          Row(children: [
            Expanded(
              child: OutlinedButton(
                onPressed: controller.schedulerLoading
                    ? null
                    : () async {
                        final result = await controller.toggleScheduler(!controller.settings.schedulerEnabled);
                        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                          content: Text(result.message),
                          backgroundColor: result.success ? Colors.green : Colors.redAccent,
                        ));
                      },
                child: controller.schedulerLoading
                    ? const SizedBox(height: 18, child: Center(child: CircularProgressIndicator(strokeWidth: 2.0)))
                    : Text(controller.settings.schedulerEnabled ? 'Scheduler OFF' : 'Scheduler ON'),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: OutlinedButton(
                onPressed: controller.botLoading
                    ? null
                    : () async {
                        final result = await controller.toggleBot(!controller.settings.botEnabled);
                        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                          content: Text(result.message),
                          backgroundColor: result.success ? Colors.green : Colors.redAccent,
                        ));
                      },
                child: controller.botLoading
                    ? const SizedBox(height: 18, child: Center(child: CircularProgressIndicator(strokeWidth: 2.0)))
                    : Text(controller.settings.botEnabled ? 'Bot OFF' : 'Bot ON'),
              ),
            ),
          ])
        ]),
      )
    ]);
  }
}
