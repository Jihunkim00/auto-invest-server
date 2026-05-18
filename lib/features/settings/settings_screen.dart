import 'package:flutter/material.dart';

import '../../core/widgets/confirm_action_dialog.dart';
import '../../core/widgets/section_card.dart';
import '../dashboard/dashboard_controller.dart';
import '../dashboard/widgets/broker_context_controls.dart';
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
              Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Expanded(
                  child: Text('Settings',
                      style:
                          TextStyle(fontSize: 28, fontWeight: FontWeight.w700)),
                ),
                BrokerContextBadge(controller: controller),
              ]),
              const SizedBox(height: 6),
              Text(
                controller.selectedProvider == SelectedProvider.kis
                    ? 'KIS safety and manual live status.'
                    : 'Alpaca paper and common safety status.',
                style: const TextStyle(color: Colors.white70),
              ),
              const SizedBox(height: 10),
              const _SectionTitle('Safety Mode'),
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
              const _SectionTitle('Trading Permissions'),
              _ReadOnlyPermissionsCard(controller: controller),
              const SizedBox(height: 12),
              const _SectionTitle('Automation Status'),
              OperationToggleCard(
                title: 'Scheduler Enabled',
                subtitle:
                    'Controls scheduled checks through backend scheduler_enabled. Real-order permission is read-only below.',
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
              const SizedBox(height: 12),
              const _SectionTitle('Runtime Status'),
              SafetySettingsSection(controller: controller),
            ],
          ),
        );
      },
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Text(
        text,
        style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800),
      ),
    );
  }
}

class _ReadOnlyPermissionsCard extends StatelessWidget {
  const _ReadOnlyPermissionsCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final settings = controller.settings;
    final safety = controller.kisSafetyStatus;
    final scheduler = controller.schedulerStatus.kr;
    final isKis = controller.selectedProvider == SelectedProvider.kis;
    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.lock_outline, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              isKis
                  ? 'KIS read-only permission flags'
                  : 'Alpaca paper permission flags',
              style: Theme.of(context).textTheme.titleMedium,
            ),
          ),
          const _ReadOnlyBadge(),
        ]),
        const SizedBox(height: 10),
        if (isKis) ...[
          _PermissionLine(
            label: 'KIS real order',
            value:
                safety.kisRealOrderEnabled ? 'Allowed by runtime' : 'Disabled',
            alert: safety.kisRealOrderEnabled,
          ),
          _PermissionLine(
            label: 'KIS live auto buy',
            value: settings.kisLiveAutoBuyEnabled ? 'Enabled' : 'Disabled',
            alert: settings.kisLiveAutoBuyEnabled,
          ),
          _PermissionLine(
            label: 'KIS live auto sell',
            value: settings.kisLiveAutoSellEnabled ? 'Enabled' : 'Disabled',
            alert: settings.kisLiveAutoSellEnabled,
          ),
          _PermissionLine(
            label: 'Scheduler real orders',
            value: scheduler.realOrdersAllowed ||
                    settings.kisSchedulerAllowRealOrders
                ? 'Allowed'
                : 'Disabled',
            alert: scheduler.realOrdersAllowed ||
                settings.kisSchedulerAllowRealOrders,
          ),
          _PermissionLine(
            label: 'Manual confirmation',
            value: settings.kisLiveAutoRequiresManualConfirm
                ? 'Required'
                : 'Not required',
            alert: !settings.kisLiveAutoRequiresManualConfirm,
          ),
        ] else ...[
          _PermissionLine(
            label: 'Alpaca mode',
            value: 'Paper trading',
            alert: false,
          ),
          _PermissionLine(
            label: 'Broker mode',
            value: settings.brokerMode,
            alert: false,
          ),
          _PermissionLine(
            label: 'US scheduler',
            value: controller.schedulerStatus.us.enabledForScheduler
                ? 'Enabled for checks'
                : 'Disabled',
            alert: false,
          ),
        ],
      ]),
    );
  }
}

class _PermissionLine extends StatelessWidget {
  const _PermissionLine({
    required this.label,
    required this.value,
    required this.alert,
  });

  final String label;
  final String value;
  final bool alert;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 7),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SizedBox(
          width: 150,
          child: Text(label, style: const TextStyle(color: Colors.white54)),
        ),
        Expanded(
          child: Text(
            value,
            style: TextStyle(
              color: alert ? Colors.redAccent : Colors.greenAccent,
              fontWeight: FontWeight.w800,
            ),
          ),
        ),
        const SizedBox(width: 8),
        const _ReadOnlyBadge(),
      ]),
    );
  }
}

class _ReadOnlyBadge extends StatelessWidget {
  const _ReadOnlyBadge();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.18)),
      ),
      child: const Text(
        'READ-ONLY',
        style: TextStyle(
          color: Colors.white70,
          fontSize: 10,
          fontWeight: FontWeight.w800,
        ),
      ),
    );
  }
}
