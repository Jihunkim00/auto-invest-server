import 'package:flutter/material.dart';

import 'dashboard_controller.dart';
import 'widgets/portfolio_snapshot_section.dart';

class PortfolioScreen extends StatelessWidget {
  const PortfolioScreen({
    super.key,
    required this.controller,
    this.onOpenManualOrder,
    this.onOpenAnalysis,
  });

  final DashboardController controller;
  final VoidCallback? onOpenManualOrder;
  final VoidCallback? onOpenAnalysis;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        return SafeArea(
          child: RefreshIndicator(
            onRefresh: controller.load,
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                const Text(
                  'Portfolio',
                  style: TextStyle(fontSize: 28, fontWeight: FontWeight.w700),
                ),
                const SizedBox(height: 6),
                const Text(
                  'Holdings, sell reviews, and manual ticket preparation.',
                  style: TextStyle(color: Colors.white70),
                ),
                const SizedBox(height: 12),
                PortfolioSnapshotSection(
                  controller: controller,
                  managementMode: true,
                  onOpenManualOrder: onOpenManualOrder,
                  onReviewPosition: onOpenAnalysis,
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}
