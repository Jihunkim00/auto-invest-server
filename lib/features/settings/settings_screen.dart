import 'package:flutter/material.dart';

import '../../core/widgets/confirm_action_dialog.dart';
import '../dashboard/dashboard_controller.dart';
import 'widgets/operation_toggle_card.dart';
import 'widgets/safety_settings_section.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final s = controller.settings;
        return SafeArea(
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              const Text('Settings',
                  style: TextStyle(fontSize: 28, fontWeight: FontWeight.w700)),
              const SizedBox(height: 10),
              OperationToggleCard(
                title: 'Scheduler Enabled',
                subtitle:
                    'Controls scheduled executions through backend scheduler_enabled.',
                value: s.schedulerEnabled,
                loading: controller.schedulerLoading,
                onChanged: (v) async {
                  final result = await controller.toggleScheduler(v);
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(result.message),
                    backgroundColor:
                        result.success ? Colors.green : Colors.redAccent,
                  ));
                },
              ),
              OperationToggleCard(
                title: 'Bot Enabled',
                subtitle:
                    'Enables backend bot orchestration. Does not place orders directly from app.',
                value: s.botEnabled,
                loading: controller.botLoading,
                onChanged: (v) async {
                  if (v) {
                    final ok = await showConfirmActionDialog(context,
                        title: 'Turn Bot ON?',
                        description: 'Confirm enabling bot control mode.');
                    if (!ok) return;
                  }
                  final result = await controller.toggleBot(v);
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(result.message),
                    backgroundColor:
                        result.success ? Colors.green : Colors.redAccent,
                  ));
                },
              ),
              OperationToggleCard(
                title: 'Dry Run',
                subtitle:
                    'Safety mode. Keep enabled for paper-only validation.',
                value: s.dryRun,
                loading: controller.dryRunLoading,
                onChanged: (v) async {
                  if (!v) {
                    final ok = await showConfirmActionDialog(context,
                        title: 'Turn Dry Run OFF?',
                        description:
                            'This reduces safety. Confirm only if backend policy allows it.');
                    if (!ok) return;
                  }
                  final result = await controller.setDryRun(v);
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(result.message),
                    backgroundColor:
                        result.success ? Colors.green : Colors.redAccent,
                  ));
                },
              ),
              OperationToggleCard(
                title: 'Kill Switch',
                subtitle:
                    'Emergency block. ON blocks trading actions in backend.',
                value: s.killSwitch,
                loading: controller.killSwitchLoading,
                onChanged: (v) async {
                  if (!v) {
                    final ok = await showConfirmActionDialog(context,
                        title: 'Turn Kill Switch OFF?',
                        description: 'This removes emergency halt protection.');
                    if (!ok) return;
                  }
                  final result = await controller.toggleKillSwitch(v);
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(result.message),
                    backgroundColor:
                        result.success ? Colors.green : Colors.redAccent,
                  ));
                },
              ),
              const SizedBox(height: 12),
              SafetySettingsSection(controller: controller),
            ],
          ),
        );
      },
    );
  }
}
