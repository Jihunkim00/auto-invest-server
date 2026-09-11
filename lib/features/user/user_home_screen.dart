import 'package:flutter/material.dart';

import '../../models/auth_session.dart';
import '../dashboard/dashboard_controller.dart';
import '../home/home_screen.dart';

class UserHomeScreen extends StatelessWidget {
  const UserHomeScreen({
    super.key,
    required this.controller,
    required this.user,
  });

  final DashboardController controller;
  final AuthUser user;

  @override
  Widget build(BuildContext context) {
    return HomeScreen(
      key: const ValueKey('user-home-screen'),
      controller: controller,
      readOnlyUser: true,
    );
  }
}
