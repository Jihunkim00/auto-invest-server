import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/network/api_client.dart';
import '../../models/auth_session.dart';
import 'admin_setup_screen.dart';
import 'login_screen.dart';

typedef AuthenticatedAppBuilder = Widget Function(
  BuildContext context,
  Future<void> Function(BuildContext originContext) onLogout,
);

class AuthGate extends StatefulWidget {
  const AuthGate({
    super.key,
    required this.apiClient,
    required this.authenticatedBuilder,
  });

  final ApiClient apiClient;
  final AuthenticatedAppBuilder authenticatedBuilder;

  @override
  State<AuthGate> createState() => _AuthGateState();
}

class _AuthGateState extends State<AuthGate> {
  AuthSessionState? _authState;
  String? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    unawaited(_refresh());
  }

  Future<void> _refresh() async {
    if (mounted) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }
    try {
      final state = await widget.apiClient.fetchAuthMe();
      if (!mounted) return;
      setState(() {
        _authState = state;
        _loading = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = error.toString();
      });
    }
  }

  Future<void> _logout(BuildContext originContext) async {
    try {
      await widget.apiClient.logout();
    } catch (_) {
      return;
    }
    if (originContext.mounted) {
      Navigator.of(originContext).popUntil((route) => route.isFirst);
    }
    await _refresh();
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const _AuthLoadingView();
    }
    if (_error != null) {
      return _AuthErrorView(error: _error!, onRetry: _refresh);
    }

    final state = _authState;
    if (state == null || state.setupRequired) {
      return AdminSetupScreen(
        apiClient: widget.apiClient,
        onSetupCompleted: _refresh,
      );
    }
    if (!state.authenticated) {
      return LoginScreen(
        apiClient: widget.apiClient,
        onLoginCompleted: _refresh,
      );
    }
    return widget.authenticatedBuilder(context, _logout);
  }
}

class _AuthLoadingView extends StatelessWidget {
  const _AuthLoadingView();

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircularProgressIndicator(),
            SizedBox(height: 16),
            Text('Auto Invest 인증 상태를 확인하는 중...'),
          ],
        ),
      ),
    );
  }
}

class _AuthErrorView extends StatelessWidget {
  const _AuthErrorView({required this.error, required this.onRetry});

  final String error;
  final Future<void> Function() onRetry;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.cloud_off, size: 40),
              const SizedBox(height: 12),
              const Text('Backend에 연결할 수 없습니다.'),
              const SizedBox(height: 8),
              Text(
                error,
                textAlign: TextAlign.center,
                style: const TextStyle(color: Colors.white70),
              ),
              const SizedBox(height: 16),
              FilledButton.icon(
                key: const ValueKey('auth-retry-button'),
                onPressed: () => onRetry(),
                icon: const Icon(Icons.refresh),
                label: const Text('다시 시도'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
