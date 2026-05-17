import 'package:flutter/material.dart';

import 'dashboard_controller.dart';
import 'widgets/watchlist_section.dart';

class WatchlistScreen extends StatelessWidget {
  const WatchlistScreen({
    super.key,
    required this.controller,
    this.onOpenManualOrder,
  });

  final DashboardController controller;
  final VoidCallback? onOpenManualOrder;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        return SafeArea(
          child: RefreshIndicator(
            onRefresh: controller.loadMarketWatchlists,
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                const Text(
                  'Watchlist',
                  style: TextStyle(fontSize: 28, fontWeight: FontWeight.w700),
                ),
                const SizedBox(height: 6),
                const Text(
                  'Find the next new-buy candidate. Manual order review happens elsewhere.',
                  style: TextStyle(color: Colors.white70),
                ),
                const SizedBox(height: 12),
                WatchlistSection(
                  controller: controller,
                  onOpenManualOrder: onOpenManualOrder,
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}
