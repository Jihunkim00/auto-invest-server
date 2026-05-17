import 'package:flutter/material.dart';

import 'dashboard_controller.dart';
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
              const Text(
                'Test Lab',
                style: TextStyle(fontSize: 28, fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 6),
              const Text(
                'Advanced checks, shadow runs, dry-runs, and readiness diagnostics.',
                style: TextStyle(color: Colors.white70),
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
