import 'package:flutter/material.dart';

import 'dashboard_controller.dart';
import 'widgets/broker_context_controls.dart';
import 'widgets/watchlist_section.dart';

class TestLabScreen extends StatelessWidget {
  const TestLabScreen({super.key, required this.controller});

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
                    'Test Lab',
                    style: TextStyle(fontSize: 28, fontWeight: FontWeight.w700),
                  ),
                ),
                BrokerContextBadge(controller: controller),
              ]),
              const SizedBox(height: 6),
              Text(
                controller.selectedProvider == SelectedProvider.kis
                    ? 'KIS shadow, dry-run, preview, and readiness diagnostics.'
                    : 'Alpaca paper and watchlist diagnostics remain non-live here.',
                style: const TextStyle(color: Colors.white70),
              ),
              const SizedBox(height: 12),
              TestLabSection(controller: controller),
            ],
          ),
        );
      },
    );
  }
}
