import 'package:flutter/material.dart';

import '../../../core/widgets/metric_card.dart';
import '../../../core/widgets/section_card.dart';
import '../../dashboard/dashboard_controller.dart';

class SystemStatusSection extends StatelessWidget {
  const SystemStatusSection({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final s = controller.settings;
    final krScheduler = controller.schedulerStatus.kr;
    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('System Integrity', style: TextStyle(fontSize: 22, fontWeight: FontWeight.w600)),
        const SizedBox(height: 14),
        GridView.count(
          crossAxisCount: 2,
          crossAxisSpacing: 10,
          mainAxisSpacing: 10,
          childAspectRatio: 1.9,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          children: [
            MetricCard(label: 'Bot Status', value: s.botEnabled ? 'ON' : 'OFF', icon: Icons.smart_toy, highlight: s.botEnabled),
            MetricCard(label: 'Scheduler', value: s.schedulerEnabled ? 'ON' : 'OFF', icon: Icons.schedule, highlight: s.schedulerEnabled),
            MetricCard(label: 'Dry Run', value: s.dryRun ? 'ENABLED' : 'OFF', icon: Icons.science, highlight: s.dryRun),
            MetricCard(label: 'Broker Mode', value: 'ALPACA PAPER', icon: Icons.account_balance, highlight: true),
          ],
        ),
        const SizedBox(height: 12),
        _StatusLine(
          icon: Icons.public,
          text: krScheduler.enabledForScheduler
              ? 'KR scheduler enabled'
              : 'KR scheduler disabled',
          color: krScheduler.enabledForScheduler
              ? Colors.greenAccent
              : Colors.amberAccent,
        ),
        const SizedBox(height: 8),
        _StatusLine(
          icon: Icons.lock_outline,
          text: krScheduler.realOrdersAllowed
              ? 'KR real orders allowed'
              : 'Real orders disabled',
          color: krScheduler.realOrdersAllowed
              ? Colors.redAccent
              : Colors.amberAccent,
        ),
        const SizedBox(height: 8),
        _StatusLine(
          icon: Icons.visibility_outlined,
          text: krScheduler.previewOnly ? 'Preview only' : 'Preview unavailable',
          color: Colors.lightBlueAccent,
        ),
      ]),
    );
  }
}

class _StatusLine extends StatelessWidget {
  const _StatusLine({
    required this.icon,
    required this.text,
    required this.color,
  });

  final IconData icon;
  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Row(children: [
      Icon(icon, size: 17, color: color),
      const SizedBox(width: 8),
      Expanded(
        child: Text(
          text,
          style: TextStyle(color: color, fontWeight: FontWeight.w700),
        ),
      ),
    ]);
  }
}
