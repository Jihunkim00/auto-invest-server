import 'package:flutter/material.dart';

import '../../core/network/api_client.dart';
import 'auth_screen_frame.dart';

class AdminSetupScreen extends StatefulWidget {
  const AdminSetupScreen({
    super.key,
    required this.apiClient,
    this.onSetupCompleted,
  });

  final ApiClient apiClient;
  final Future<void> Function()? onSetupCompleted;

  @override
  State<AdminSetupScreen> createState() => _AdminSetupScreenState();
}

class _AdminSetupScreenState extends State<AdminSetupScreen> {
  final _formKey = GlobalKey<FormState>();
  final _setupCodeController = TextEditingController();
  final _passwordController = TextEditingController();
  final _confirmPasswordController = TextEditingController();
  String? _error;
  bool _loading = false;

  @override
  void dispose() {
    _setupCodeController.dispose();
    _passwordController.dispose();
    _confirmPasswordController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await widget.apiClient.setupAdmin(
        username: 'admin',
        setupCode: _setupCodeController.text,
        newPassword: _passwordController.text,
        confirmPassword: _confirmPasswordController.text,
      );
      if (!mounted) return;
      await widget.onSetupCompleted?.call();
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = formatAuthError(error));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AuthScreenFrame(
      key: const ValueKey('auth-admin-setup-screen'),
      title: 'Admin 최초 설정',
      subtitle: '처음 한 번만 등록 코드를 사용해 비밀번호를 설정합니다.',
      child: Form(
        key: _formKey,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TextFormField(
              key: ValueKey('auth-setup-username-field'),
              initialValue: 'admin',
              readOnly: true,
              decoration: InputDecoration(
                labelText: 'ID',
                prefixIcon: Icon(Icons.person_outline),
              ),
            ),
            const SizedBox(height: 14),
            TextFormField(
              key: const ValueKey('auth-setup-code-field'),
              controller: _setupCodeController,
              decoration: const InputDecoration(
                labelText: '등록 코드',
                prefixIcon: Icon(Icons.key_outlined),
              ),
              validator: (value) => (value == null || value.isEmpty)
                  ? '등록 코드를 입력하세요.'
                  : null,
            ),
            const SizedBox(height: 14),
            TextFormField(
              key: const ValueKey('auth-setup-password-field'),
              controller: _passwordController,
              obscureText: true,
              decoration: const InputDecoration(
                labelText: '새 비밀번호',
                prefixIcon: Icon(Icons.lock_outline),
              ),
              validator: (value) => (value == null || value.isEmpty)
                  ? '새 비밀번호를 입력하세요.'
                  : null,
            ),
            const SizedBox(height: 14),
            TextFormField(
              key: const ValueKey('auth-setup-confirm-password-field'),
              controller: _confirmPasswordController,
              obscureText: true,
              decoration: const InputDecoration(
                labelText: '비밀번호 확인',
                prefixIcon: Icon(Icons.lock_reset_outlined),
              ),
              validator: (value) => value != _passwordController.text
                  ? '비밀번호가 일치하지 않습니다.'
                  : null,
            ),
            if (_error != null) ...[
              const SizedBox(height: 14),
              Text(
                _error!,
                key: const ValueKey('auth-setup-error'),
                style: const TextStyle(color: Colors.redAccent),
              ),
            ],
            const SizedBox(height: 20),
            FilledButton.icon(
              key: const ValueKey('auth-setup-button'),
              onPressed: _loading ? null : _submit,
              icon: _loading
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.check_circle_outline),
              label: Text(_loading ? '설정 중...' : '설정 완료'),
            ),
          ],
        ),
      ),
    );
  }
}
