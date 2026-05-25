import 'package:flutter/material.dart';

import 'core/i18n/app_strings.dart';
import 'core/network/api_client.dart';
import 'core/theme/app_theme.dart';
import 'features/analysis/analysis_screen.dart';
import 'features/dashboard/dashboard_controller.dart';
import 'features/dashboard/dashboard_screen.dart';
import 'features/dashboard/manual_order_screen.dart';
import 'features/dashboard/test_lab_screen.dart';
import 'features/logs/logs_screen.dart';
import 'features/settings/settings_screen.dart';

class AutoInvestApp extends StatefulWidget {
  const AutoInvestApp({super.key, this.controller});
  final DashboardController? controller;
  @override
  State<AutoInvestApp> createState() => _AutoInvestAppState();
}

class _AutoInvestAppState extends State<AutoInvestApp> {
  late final DashboardController _controller = widget.controller ?? DashboardController(ApiClient());
  int _index = 0;
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
        final l = _controller.uiLanguage;
        return MaterialApp(
          debugShowCheckedModeBanner: false,
          title: 'AUTO INVEST',
          theme: AppTheme.lightTheme,
          home: Scaffold(
            body: IndexedStack(index: _index, children: [
              DashboardScreen(controller: _controller, onOpenManualOrder: () => setState(() => _index = 2), onReviewPosition: () => setState(() => _index = 1)),
              AnalysisScreen(controller: _controller),
              TradingScreen(controller: _controller),
              LogsScreen(controller: _controller),
              SettingsScreen(controller: _controller),
              TestLabScreen(controller: _controller),
            ]),
            bottomNavigationBar: NavigationBar(
              selectedIndex: _index,
              onDestinationSelected: (v) => setState(() => _index = v),
              destinations: [
                NavigationDestination(icon: const Icon(Icons.home_outlined), selectedIcon: const Icon(Icons.home), label: AppStrings.t(AppTextKey.home, l)),
                NavigationDestination(icon: const Icon(Icons.analytics_outlined), selectedIcon: const Icon(Icons.analytics), label: AppStrings.t(AppTextKey.analysis, l)),
                NavigationDestination(icon: const Icon(Icons.swap_horiz_outlined), selectedIcon: const Icon(Icons.swap_horiz), label: AppStrings.t(AppTextKey.trading, l)),
                NavigationDestination(icon: const Icon(Icons.receipt_long_outlined), selectedIcon: const Icon(Icons.receipt_long), label: AppStrings.t(AppTextKey.logs, l)),
              ],
            ),
          ),
        );
      },
    );
  }
}
