import 'package:flutter/material.dart';

import 'core/network/api_client.dart';
import 'core/theme/app_theme.dart';
import 'features/analysis/analysis_screen.dart';
import 'features/dashboard/dashboard_controller.dart';
import 'features/dashboard/dashboard_screen.dart';
import 'features/dashboard/manual_order_screen.dart';
import 'features/dashboard/portfolio_screen.dart';
import 'features/dashboard/test_lab_screen.dart';
import 'features/dashboard/watchlist_screen.dart';
import 'features/logs/logs_screen.dart';
import 'features/settings/settings_screen.dart';

class AutoInvestApp extends StatefulWidget {
  const AutoInvestApp({super.key});

  @override
  State<AutoInvestApp> createState() => _AutoInvestAppState();
}

class _AutoInvestAppState extends State<AutoInvestApp> {
  final DashboardController _controller = DashboardController(ApiClient());
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
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'AUTO INVEST',
      theme: AppTheme.darkTheme,
      home: Scaffold(
        body: IndexedStack(
          index: _index,
          children: [
            DashboardScreen(controller: _controller),
            PortfolioScreen(
              controller: _controller,
              onOpenManualOrder: () => _selectTab(3),
              onOpenAnalysis: () => _selectTab(4),
            ),
            WatchlistScreen(
              controller: _controller,
              onOpenManualOrder: () => _selectTab(3),
            ),
            ManualOrderScreen(controller: _controller),
            AnalysisScreen(controller: _controller),
            LogsScreen(controller: _controller),
            SettingsScreen(controller: _controller),
            TestLabScreen(controller: _controller),
          ],
        ),
        bottomNavigationBar: NavigationBar(
          selectedIndex: _index,
          onDestinationSelected: _selectTab,
          destinations: const [
            NavigationDestination(
                icon: Icon(Icons.home_outlined),
                selectedIcon: Icon(Icons.home),
                label: 'Home'),
            NavigationDestination(
                icon: Icon(Icons.account_balance_wallet_outlined),
                selectedIcon: Icon(Icons.account_balance_wallet),
                label: 'Portfolio'),
            NavigationDestination(
                icon: Icon(Icons.manage_search_outlined),
                selectedIcon: Icon(Icons.manage_search),
                label: 'Watchlist'),
            NavigationDestination(
                icon: Icon(Icons.request_quote_outlined),
                selectedIcon: Icon(Icons.request_quote),
                label: 'Manual'),
            NavigationDestination(
                icon: Icon(Icons.analytics_outlined),
                selectedIcon: Icon(Icons.analytics),
                label: 'Analysis'),
            NavigationDestination(
                icon: Icon(Icons.receipt_long_outlined),
                selectedIcon: Icon(Icons.receipt_long),
                label: 'Logs'),
            NavigationDestination(
                icon: Icon(Icons.settings_outlined),
                selectedIcon: Icon(Icons.settings),
                label: 'Settings'),
            NavigationDestination(
                icon: Icon(Icons.science_outlined),
                selectedIcon: Icon(Icons.science),
                label: 'Test Lab'),
          ],
        ),
      ),
    );
  }
}
