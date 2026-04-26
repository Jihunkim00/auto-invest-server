import 'package:flutter/material.dart';

import '../dashboard/dashboard_controller.dart';
import 'widgets/log_filter_chips.dart';
import 'widgets/run_log_card.dart';

class LogsScreen extends StatefulWidget {
  const LogsScreen({super.key, required this.controller});

  final DashboardController controller;

  @override
  State<LogsScreen> createState() => _LogsScreenState();
}

class _LogsScreenState extends State<LogsScreen> {
  String filter = 'All';

  @override
  Widget build(BuildContext context) {
    final runs = widget.controller.recentRuns.where((r) {
      if (filter == 'All') return true;
      final f = filter.toLowerCase();
      return r.triggerSource == f || r.action == f || r.result == f;
    }).toList();

    return SafeArea(
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const Text('Recent Runs', style: TextStyle(fontSize: 28, fontWeight: FontWeight.w700)),
          const SizedBox(height: 10),
          LogFilterChips(value: filter, onChanged: (v) => setState(() => filter = v)),
          const SizedBox(height: 10),
          ...runs.map((e) => RunLogCard(run: e)),
        ],
      ),
    );
  }
}
