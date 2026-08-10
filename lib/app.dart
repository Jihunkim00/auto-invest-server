import 'package:flutter/material.dart';

import 'core/i18n/app_language.dart';
import 'core/network/api_client.dart';
import 'core/theme/app_theme.dart';
import 'features/admin/admin_screen.dart';
import 'features/ai/ai_screen.dart';
import 'features/assets/assets_screen.dart';
import 'features/dashboard/dashboard_controller.dart';
import 'features/home/home_screen.dart';

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

  void _openAdmin(BuildContext context) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => AdminScreen(controller: _controller),
      ),
    );
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
          home: Builder(
            builder: (appContext) => Scaffold(
              body: IndexedStack(
                index: _index,
                children: [
                  HomeScreen(
                    controller: _controller,
                    onOpenAdmin: () => _openAdmin(appContext),
                  ),
                  AiScreen(
                    controller: _controller,
                    onOpenAdmin: () => _openAdmin(appContext),
                  ),
                  AssetsScreen(controller: _controller),
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
                  const NavigationDestination(
                    icon: Icon(Icons.auto_awesome_outlined),
                    selectedIcon: Icon(Icons.auto_awesome),
                    label: 'AI',
                  ),
                  const NavigationDestination(
                    icon: Icon(Icons.account_balance_wallet_outlined),
                    selectedIcon: Icon(Icons.account_balance_wallet),
                    label: 'Assets',
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}
