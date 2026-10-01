import 'dart:async';

import 'package:flutter/material.dart';

import '../../models/auth_session.dart';
import '../dashboard/dashboard_controller.dart';
import '../home/home_screen.dart';

class UserHomeScreen extends StatefulWidget {
  const UserHomeScreen({
    super.key,
    required this.controller,
    required this.user,
    this.onOpenSettings,
    this.onOpenAutomationProfile,
  });

  final DashboardController controller;
  final AuthUser user;
  final VoidCallback? onOpenSettings;
  final VoidCallback? onOpenAutomationProfile;

  @override
  State<UserHomeScreen> createState() => _UserHomeScreenState();
}

class _UserHomeScreenState extends State<UserHomeScreen> {
  String _mode = 'paper';
  bool _modeLoading = false;

  @override
  void initState() {
    super.initState();
    unawaited(_loadTradingMode());
    unawaited(widget.controller.loadUserHomeRecentActivity());
  }

  Future<bool> _loadTradingMode({bool forceFetch = false}) async {
    try {
      late final Map<String, dynamic> settings;
      if (!forceFetch && widget.controller.regularUserHomeBootstrapStarted) {
        await widget.controller.waitForRegularUserHomeContext();
        if (!widget.controller.userTradingSettingsLoaded) return false;
        settings = widget.controller.userTradingSettings;
      } else {
        settings = await widget.controller.apiClient.fetchUserTradingSettings();
      }
      if (!mounted) return false;
      setState(() => _mode =
          settings['trading_mode']?.toString() == 'live' ? 'live' : 'paper');
      return true;
    } catch (_) {
      // Home remains usable when the optional mode indicator is unavailable.
      return false;
    }
  }

  Future<void> _changeTradingMode(String mode) async {
    if (mode == _mode) return;
    if (mounted) setState(() => _modeLoading = true);
    try {
      await widget.controller.apiClient.updateUserTradingSettings(
        tradingMode: mode,
      );
      final reloaded = await _loadTradingMode(forceFetch: true);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              reloaded ? '거래 모드가 저장되었습니다.' : '거래 모드 상태를 다시 불러오지 못했습니다.',
            ),
          ),
        );
      }
    } catch (_) {
      await _loadTradingMode(forceFetch: true);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('거래 모드를 저장하지 못했습니다.')),
        );
      }
    } finally {
      if (mounted) setState(() => _modeLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return HomeScreen(
      key: const ValueKey('user-home-screen'),
      controller: widget.controller,
      onOpenSettings: widget.onOpenSettings,
      onOpenAutomationProfile: widget.onOpenAutomationProfile,
      readOnlyUser: true,
      userTradingMode: _mode,
      userTradingModeLoading: _modeLoading,
      onUserModeChanged: _changeTradingMode,
    );
  }
}
