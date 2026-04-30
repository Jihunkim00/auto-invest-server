import 'package:flutter/material.dart';

import '../../core/widgets/status_badge.dart';
import 'dashboard_controller.dart';
import 'widgets/last_run_summary_card.dart';
import 'widgets/manual_trading_run_section.dart';
import 'widgets/quick_actions_section.dart';
import 'widgets/system_status_section.dart';

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final runAction =
            controller.hasLatestRunResult || controller.showingOfflineFallback
                ? controller.runResult.action
                : 'No run yet';
        return SafeArea(
          child: RefreshIndicator(
            onRefresh: controller.load,
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Text('Auto Invest Command Center',
                    style: Theme.of(context).textTheme.headlineMedium),
                const SizedBox(height: 4),
                const Text(
                    'Paper trading dashboard. Monitoring 50 watchlist symbols.',
                    style: TextStyle(color: Colors.white70)),
                const SizedBox(height: 10),
                Row(children: [
                  StatusBadge(text: 'Paper Mode', active: true),
                  const SizedBox(width: 8),
                  StatusBadge(
                      text: runAction.isEmpty ? 'No run yet' : runAction,
                      active: false,
                      alert: runAction == 'hold'),
                ]),
                const SizedBox(height: 16),
                LayoutBuilder(
                  builder: (context, c) {
                    final vertical = c.maxWidth < 900;
                    if (vertical) {
                      return Column(children: [
                        SystemStatusSection(controller: controller),
                        const SizedBox(height: 12),
                        LastRunSummaryCard(controller: controller),
                        const SizedBox(height: 12),
                        ManualTradingRunSection(controller: controller),
                        const SizedBox(height: 12),
                        QuickActionsSection(controller: controller),
                      ]);
                    }
                    return Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(
                              flex: 8,
                              child: Column(children: [
                                SystemStatusSection(controller: controller),
                                const SizedBox(height: 12),
                                LastRunSummaryCard(controller: controller),
                                const SizedBox(height: 12),
                                ManualTradingRunSection(controller: controller),
                              ])),
                          const SizedBox(width: 12),
                          Expanded(
                              flex: 4,
                              child:
                                  QuickActionsSection(controller: controller)),
                        ]);
                  },
                ),
                if (controller.error != null) ...[
                  const SizedBox(height: 12),
                  Text(controller.error!,
                      style: const TextStyle(color: Colors.orangeAccent)),
                ]
              ],
            ),
          ),
        );
      },
    );
  }
}
