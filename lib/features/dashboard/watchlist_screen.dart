import 'package:flutter/material.dart';

import 'dashboard_controller.dart';
import 'widgets/broker_context_controls.dart';
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
            onRefresh: controller.refreshWatchlist,
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  const Expanded(
                    child: Text(
                      'Watchlist',
                      style:
                          TextStyle(fontSize: 28, fontWeight: FontWeight.w700),
                    ),
                  ),
                  BrokerContextBadge(controller: controller),
                ]),
                const SizedBox(height: 6),
                Text(
                  controller.selectedProvider == SelectedProvider.kis
                      ? 'KIS preview-only candidate exploration. No live submit from Watchlist.'
                      : 'Alpaca paper candidate exploration and scan summary.',
                  style: const TextStyle(color: Colors.white70),
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
