import 'package:flutter/material.dart';

import '../../core/widgets/section_card.dart';
import '../dashboard/dashboard_controller.dart';

/// Stage 106 user-facing AI entry point. This shell keeps the navigation
/// surface useful without exposing operational controls or submitting orders.
class AiScreen extends StatelessWidget {
  const AiScreen({super.key, required this.controller, this.onOpenAdmin});

  final DashboardController controller;
  final VoidCallback? onOpenAdmin;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 14, 16, 4),
            child: Row(
              children: [
                const Icon(Icons.auto_awesome, color: Colors.lightBlueAccent),
                const SizedBox(width: 10),
                const Expanded(
                  child: Text(
                    'AI Assistant',
                    style: TextStyle(fontSize: 24, fontWeight: FontWeight.w900),
                  ),
                ),
                IconButton(
                  key: const ValueKey('ai-open-admin'),
                  tooltip: 'Advanced / Admin',
                  onPressed: onOpenAdmin,
                  icon: const Icon(Icons.admin_panel_settings_outlined),
                ),
              ],
            ),
          ),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 10),
            child: Row(
              children: [
                for (final label in const [
                  'Analyze a symbol',
                  'Show portfolio',
                  'Recent decision',
                ])
                  Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: ActionChip(
                      key: ValueKey('ai-shell-quick-$label'),
                      label: Text(label),
                      onPressed: () {},
                    ),
                  ),
              ],
            ),
          ),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.fromLTRB(16, 4, 16, 16),
              children: [
                SectionCard(
                  key: const ValueKey('ai-shell-welcome-card'),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'Ask about your market and portfolio.',
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        'AI answers and order preparation remain read-only in this user surface.',
                        style: const TextStyle(color: Colors.white70),
                      ),
                      const SizedBox(height: 12),
                      Text(
                        'Broker: ${controller.selectedBrokerLabel}',
                        style: const TextStyle(color: Colors.white54),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 12),
                const SectionCard(
                  child: TextField(
                    enabled: false,
                    decoration: InputDecoration(
                      hintText: 'What would you like to know?',
                      prefixIcon: Icon(Icons.chat_bubble_outline),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
