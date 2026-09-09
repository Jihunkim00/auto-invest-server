import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'core/i18n/app_language.dart';
import 'core/network/api_client.dart';
import 'core/theme/app_theme.dart';
import 'features/admin/admin_screen.dart';
import 'features/ai/ai_screen.dart';
import 'features/assets/assets_screen.dart';
import 'features/auth/auth_gate.dart';
import 'features/automation_profile/automation_profile_screen.dart';
import 'features/dashboard/dashboard_controller.dart';
import 'features/home/home_screen.dart';

class AutoInvestApp extends StatefulWidget {
  const AutoInvestApp({
    super.key,
    this.controller,
    this.authenticationEnabled,
  });

  final DashboardController? controller;

  /// Injected controllers are the existing app test seam. Production creates
  /// the controller internally and therefore enables authentication by default.
  final bool? authenticationEnabled;

  @override
  State<AutoInvestApp> createState() => _AutoInvestAppState();
}

class _AutoInvestAppState extends State<AutoInvestApp> {
  bool get _authEnabled =>
      widget.authenticationEnabled ?? widget.controller == null;

  late final ApiClient _apiClient =
      widget.controller?.apiClient ?? ApiClient();
  late final DashboardController _controller = widget.controller ??
      DashboardController(
        _apiClient,
        autoload: !_authEnabled,
        persistProvider: true,
      );

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
          localizationsDelegates: GlobalMaterialLocalizations.delegates,
          supportedLocales: const [
            Locale('ko', 'KR'),
            Locale('en', 'US'),
          ],
          theme: AppTheme.darkTheme,
          home: _authEnabled
              ? AuthGate(
                  apiClient: _apiClient,
                  authenticatedBuilder: (context, onLogout) =>
                      _ExistingAutoInvestHome(
                    controller: _controller,
                    onLogout: onLogout,
                    loadOnMount: true,
                  ),
                )
              : _ExistingAutoInvestHome(
                  controller: _controller,
                  loadOnMount: false,
                ),
        );
      },
    );
  }
}

class _ExistingAutoInvestHome extends StatefulWidget {
  const _ExistingAutoInvestHome({
    required this.controller,
    required this.loadOnMount,
    this.onLogout,
  });

  final DashboardController controller;
  final bool loadOnMount;
  final Future<void> Function(BuildContext originContext)? onLogout;

  @override
  State<_ExistingAutoInvestHome> createState() =>
      _ExistingAutoInvestHomeState();
}

class _ExistingAutoInvestHomeState extends State<_ExistingAutoInvestHome> {
  int _index = 0;

  @override
  void initState() {
    super.initState();
    if (widget.loadOnMount) {
      unawaited(widget.controller.load());
    }
  }

  void _selectTab(int index) {
    setState(() => _index = index);
  }

  void _openAdmin(BuildContext context) {
    final onLogout = widget.onLogout == null
        ? null
        : () => widget.onLogout!(context);
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => AdminScreen(
          controller: widget.controller,
          onLogout: onLogout,
        ),
      ),
    );
  }

  void _openAutomationProfile(BuildContext context) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => AutomationProfileScreen(
          apiClient: widget.controller.apiClient,
          appLanguage: widget.controller.appLanguage,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final controller = widget.controller;
    return Builder(
      builder: (appContext) => Scaffold(
        body: IndexedStack(
          index: _index,
          children: [
            HomeScreen(
              controller: controller,
              onOpenAdmin: () => _openAdmin(appContext),
              onOpenAutomationProfile: () =>
                  _openAutomationProfile(appContext),
            ),
            AiScreen(
              controller: controller,
              onOpenAdmin: () => _openAdmin(appContext),
            ),
            AssetsScreen(
              controller: controller,
              onLogout: widget.onLogout == null
                  ? null
                  : () => widget.onLogout!(appContext),
            ),
          ],
        ),
        bottomNavigationBar: NavigationBar(
          selectedIndex: _index,
          onDestinationSelected: _selectTab,
          destinations: [
            NavigationDestination(
              icon: const Icon(Icons.home_outlined),
              selectedIcon: const Icon(Icons.home),
              label: controller.strings.home,
            ),
            NavigationDestination(
              icon: const Icon(Icons.auto_awesome_outlined),
              selectedIcon: const Icon(Icons.auto_awesome),
              label: controller.strings.aiAssistant,
            ),
            NavigationDestination(
              icon: const Icon(Icons.account_balance_wallet_outlined),
              selectedIcon: const Icon(Icons.account_balance_wallet),
              label: controller.strings.assets,
            ),
          ],
        ),
      ),
    );
  }
}
