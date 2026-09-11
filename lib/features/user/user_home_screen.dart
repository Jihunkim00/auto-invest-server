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
  });

  final DashboardController controller;
  final AuthUser user;
  final VoidCallback? onOpenSettings;

  @override
  State<UserHomeScreen> createState() => _UserHomeScreenState();
}

class _UserHomeScreenState extends State<UserHomeScreen> {
  String _mode = 'paper';

  @override
  void initState() {
    super.initState();
    unawaited(_loadTradingMode());
  }

  Future<void> _loadTradingMode() async {
    try {
      final settings = await widget.controller.apiClient.fetchUserTradingSettings();
      if (!mounted) return;
      setState(() => _mode = settings['trading_mode']?.toString() == 'live' ? 'live' : 'paper');
    } catch (_) {
      // Home remains usable when the optional mode indicator is unavailable.
    }
  }

  @override
  Widget build(BuildContext context) {
    return HomeScreen(
      key: const ValueKey('user-home-screen'),
      controller: widget.controller,
      onOpenSettings: widget.onOpenSettings,
      readOnlyUser: true,
      userTradingMode: _mode,
    );
  }
}
