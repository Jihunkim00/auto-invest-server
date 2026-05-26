import 'package:flutter/material.dart';

import 'dashboard_controller.dart';
import 'widgets/broker_context_controls.dart';
import 'widgets/watchlist_section.dart';

class KisAutomationScreen extends StatelessWidget {
  const KisAutomationScreen({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        return SafeArea(
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Expanded(
                  child: Text(
                    'KIS Automation',
                    style: TextStyle(fontSize: 28, fontWeight: FontWeight.w700),
                  ),
                ),
                BrokerContextBadge(controller: controller),
              ]),
              const SizedBox(height: 6),
              Text(
                controller.selectedProvider == SelectedProvider.kis
                    ? 'Primary KIS operations surface for readiness, buy review, position management, and scheduled management.'
                    : 'Switch to KIS to use broker automation operations.',
                style: const TextStyle(color: Colors.white70),
              ),
              const SizedBox(height: 12),
              KisAutomationSection(controller: controller),
            ],
          ),
        );
      },
    );
  }
}

class TestLabScreen extends StatelessWidget {
  const TestLabScreen({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return KisAutomationScreen(controller: controller);
  }
}
