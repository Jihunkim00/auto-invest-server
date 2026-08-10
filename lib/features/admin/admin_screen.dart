import 'package:flutter/material.dart';

import '../analysis/analysis_screen.dart';
import '../dashboard/dashboard_controller.dart';
import '../dashboard/manual_order_screen.dart';
import '../dashboard/test_lab_screen.dart';
import '../dashboard/watchlist_screen.dart';
import '../logs/logs_screen.dart';
import '../settings/settings_screen.dart';

class AdminScreen extends StatelessWidget {
  const AdminScreen({super.key, required this.controller});

  final DashboardController controller;

  void _open(BuildContext context, Widget screen) {
    Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => screen));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Advanced / Admin')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const Text(
            '운영 도구와 진단 화면입니다. 일반 사용자 화면에는 노출하지 않습니다.',
            style: TextStyle(color: Colors.white70),
          ),
          const SizedBox(height: 14),
          _AdminGroup(
            title: 'Analysis & trading',
            items: [
              _AdminItem(
                key: const ValueKey('admin-open-analysis'),
                icon: Icons.analytics_outlined,
                title: 'Analysis',
                onTap: () => _open(
                  context,
                  AnalysisScreen(
                    controller: controller,
                    onOpenManualOrder: () => _open(
                      context,
                      TradingScreen(controller: controller),
                    ),
                    onOpenDashboard: () => Navigator.of(context).pop(),
                  ),
                ),
              ),
              _AdminItem(
                key: const ValueKey('admin-open-manual-trading'),
                icon: Icons.swap_horiz,
                title: 'Manual Trading',
                onTap: () => _open(
                  context,
                  TradingScreen(controller: controller),
                ),
              ),
            ],
          ),
          _AdminGroup(
            title: 'Operations',
            items: [
              _AdminItem(
                key: const ValueKey('admin-open-test4'),
                icon: Icons.tune,
                title: 'Test tools / KIS Automation',
                subtitle: 'Existing Test4 and scheduler operations surface',
                onTap: () => _open(
                  context,
                  TestLabScreen(controller: controller),
                ),
              ),
              _AdminItem(
                key: const ValueKey('admin-open-watchlist'),
                icon: Icons.manage_search,
                title: 'Watchlist',
                onTap: () => _open(
                  context,
                  WatchlistScreen(
                    controller: controller,
                    onOpenManualOrder: () => _open(
                      context,
                      TradingScreen(controller: controller),
                    ),
                  ),
                ),
              ),
              _AdminItem(
                key: const ValueKey('admin-open-logs'),
                icon: Icons.receipt_long_outlined,
                title: 'Logs & diagnostics',
                onTap: () => _open(
                  context,
                  LogsScreen(controller: controller),
                ),
              ),
              _AdminItem(
                key: const ValueKey('admin-open-settings'),
                icon: Icons.settings_outlined,
                title: 'Settings',
                onTap: () => _open(
                  context,
                  SettingsScreen(controller: controller),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _AdminGroup extends StatelessWidget {
  const _AdminGroup({required this.title, required this.items});

  final String title;
  final List<Widget> items;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 14),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 12, 12, 8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title,
                style: const TextStyle(
                    color: Colors.lightBlueAccent,
                    fontWeight: FontWeight.w800)),
            const SizedBox(height: 6),
            ...items,
          ],
        ),
      ),
    );
  }
}

class _AdminItem extends StatelessWidget {
  const _AdminItem({
    super.key,
    required this.icon,
    required this.title,
    required this.onTap,
    this.subtitle,
  });

  final IconData icon;
  final String title;
  final String? subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      contentPadding: EdgeInsets.zero,
      leading: Icon(icon),
      title: Text(title),
      subtitle: subtitle == null ? null : Text(subtitle!),
      trailing: const Icon(Icons.chevron_right),
      onTap: onTap,
    );
  }
}
