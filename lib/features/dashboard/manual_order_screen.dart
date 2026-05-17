import 'package:flutter/material.dart';

import 'dashboard_controller.dart';
import 'widgets/order_ticket_section.dart';

class ManualOrderScreen extends StatelessWidget {
  const ManualOrderScreen({super.key, required this.controller});

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
                'Manual Order',
                style: TextStyle(fontSize: 28, fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 6),
              const Text(
                'Validate, confirm, submit, and sync KIS manual orders.',
                style: TextStyle(color: Colors.white70),
              ),
              const SizedBox(height: 12),
              OrderTicketSection(controller: controller),
            ],
          ),
        );
      },
    );
  }
}
