import 'package:flutter/material.dart';

import 'core/i18n/app_language.dart';
import 'core/network/api_client.dart';
import 'core/theme/app_theme.dart';
import 'features/analysis/analysis_screen.dart';
import 'features/dashboard/dashboard_controller.dart';
import 'features/dashboard/dashboard_screen.dart';
import 'features/dashboard/manual_order_screen.dart';
import 'features/dashboard/test_lab_screen.dart';
import 'features/dashboard/watchlist_screen.dart';
import 'features/logs/logs_screen.dart';
import 'features/settings/settings_screen.dart';

class AutoInvestApp extends StatefulWidget {
  const AutoInvestApp({
    super.key,
    this.controller,
  });

  final DashboardController? controller;

  @override
  State<AutoInvestApp> createState() => _AutoInvestAppState();
}

class _AutoInvestAppState extends State<AutoInvestApp> {
  late final DashboardController _controller =
      widget.controller ?? DashboardController(ApiClient());
  int _index = 0;

  void _selectTab(int index) {
    setState(() => _index = index);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        final strings = _controller.strings;
        return MaterialApp(
          debugShowCheckedModeBanner: false,
          title: strings.appTitle,
          locale: Locale(_controller.appLanguage.languageCode),
          theme: AppTheme.darkTheme,
          home: Scaffold(
            body: IndexedStack(
              index: _index,
              children: [
                DashboardScreen(
                  controller: _controller,
                  onOpenManualOrder: () => _selectTab(3),
                  onReviewPosition: () => _selectTab(2),
                  onOpenLogs: () => _selectTab(4),
                  onOpenSettings: () => _selectTab(5),
                ),
                WatchlistScreen(
                  controller: _controller,
                  onOpenManualOrder: () => _selectTab(3),
                ),
                AnalysisScreen(
                  controller: _controller,
                  onOpenManualOrder: () => _selectTab(3),
                  onOpenDashboard: () => _selectTab(0),
                ),
                TradingScreen(controller: _controller),
                LogsScreen(controller: _controller),
                SettingsScreen(controller: _controller),
                KisAutomationScreen(controller: _controller),
              ],
            ),
            bottomNavigationBar: NavigationBar(
              selectedIndex: _index,
              onDestinationSelected: _selectTab,
              destinations: [
                NavigationDestination(
                  icon: const Icon(Icons.home_outlined),
                  selectedIcon: const Icon(Icons.home),
                  label: strings.home,
                ),
                NavigationDestination(
                  icon: const Icon(Icons.manage_search_outlined),
                  selectedIcon: const Icon(Icons.manage_search),
                  label: strings.watchlist,
                ),
                NavigationDestination(
                  icon: const Icon(Icons.analytics_outlined),
                  selectedIcon: const Icon(Icons.analytics),
                  label: strings.analysis,
                ),
                NavigationDestination(
                  icon: const Icon(Icons.swap_horiz_outlined),
                  selectedIcon: const Icon(Icons.swap_horiz),
                  label: strings.trading,
                ),
                NavigationDestination(
                  icon: const Icon(Icons.receipt_long_outlined),
                  selectedIcon: const Icon(Icons.receipt_long),
                  label: strings.logs,
                ),
                NavigationDestination(
                  icon: const Icon(Icons.settings_outlined),
                  selectedIcon: const Icon(Icons.settings),
                  label: strings.settings,
                ),
                NavigationDestination(
                  icon: const Icon(Icons.tune_outlined),
                  selectedIcon: const Icon(Icons.tune),
                  label: strings.kisAutomation,
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}
