import 'package:flutter/material.dart';

import '../../core/config/app_config.dart';
import '../../core/widgets/status_badge.dart';
import 'dashboard_controller.dart';
import 'widgets/last_run_summary_card.dart';
import 'widgets/quick_actions_section.dart';
import 'widgets/system_status_section.dart';

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({super.key, required this.controller});

  final DashboardController controller;

  void _toast(BuildContext context, String msg) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
  }

  String _connectionLabel(BackendConnectionStatus s) {
    switch (s) {
      case BackendConnectionStatus.connected:
        return 'Connected';
      case BackendConnectionStatus.offline:
        return 'Offline';
      case BackendConnectionStatus.error:
        return 'Error';
    }
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: RefreshIndicator(
        onRefresh: controller.refreshSettings,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Text('Auto Invest Command Center', style: Theme.of(context).textTheme.headlineMedium),
            const SizedBox(height: 4),
            const Text('Paper trading dashboard. Monitoring 50 watchlist symbols.', style: TextStyle(color: Colors.white70)),
            const SizedBox(height: 10),
            Row(children: [
              StatusBadge(text: 'Paper Mode', active: true),
              const SizedBox(width: 8),
              StatusBadge(text: _connectionLabel(controller.connectionStatus), active: controller.connectionStatus == BackendConnectionStatus.connected, alert: controller.connectionStatus != BackendConnectionStatus.connected),
            ]),
            const SizedBox(height: 6),
            Text('Backend: ${AppConfig.resolvedApiBaseUrl}', style: const TextStyle(color: Colors.white60, fontSize: 12)),
            Text('Last settings sync: ${controller.lastSettingsSyncAt?.toIso8601String() ?? 'N/A'}', style: const TextStyle(color: Colors.white60, fontSize: 12)),
            if (controller.lastActionMessage != null)
              Text(controller.lastActionMessage!, style: const TextStyle(color: Colors.greenAccent, fontSize: 12)),
            if (controller.bannerWarning != null)
              Container(
                margin: const EdgeInsets.only(top: 8),
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(color: Colors.orange.withOpacity(0.16), borderRadius: BorderRadius.circular(12), border: Border.all(color: Colors.orangeAccent.withOpacity(0.5))),
                child: Text(controller.bannerWarning!, style: const TextStyle(color: Colors.orangeAccent)),
              ),
            const SizedBox(height: 16),
            LayoutBuilder(
              builder: (context, c) {
                final vertical = c.maxWidth < 900;
                final quick = QuickActionsSection(
                  controller: controller,
                  onRunOnce: () async => _toast(context, await controller.runWatchlistOnce()),
                  onToggleScheduler: () async => _toast(context, await controller.toggleScheduler(!controller.settings.schedulerEnabled)),
                  onToggleBot: () async => _toast(context, await controller.toggleBot(!controller.settings.botEnabled)),
                  onToggleKillSwitch: () async => _toast(context, await controller.toggleKillSwitch(!controller.settings.killSwitch)),
                );
                if (vertical) {
                  return Column(children: [
                    SystemStatusSection(controller: controller),
                    const SizedBox(height: 12),
                    LastRunSummaryCard(controller: controller),
                    const SizedBox(height: 12),
                    quick,
                  ]);
                }
                return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Expanded(
                    flex: 8,
                    child: Column(children: [SystemStatusSection(controller: controller), const SizedBox(height: 12), LastRunSummaryCard(controller: controller)]),
                  ),
                  const SizedBox(width: 12),
                  Expanded(flex: 4, child: quick),
                ]);
              },
            ),
          ],
        ),
      ),
    );
  }
}
