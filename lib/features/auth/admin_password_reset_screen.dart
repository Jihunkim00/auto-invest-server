import 'package:flutter/material.dart';

import '../../core/network/api_client.dart';
import 'auth_screen_frame.dart';

class AdminPasswordResetScreen extends StatefulWidget {
  const AdminPasswordResetScreen({
    super.key,
    required this.apiClient,
  });

  final ApiClient apiClient;

  @override
  State<AdminPasswordResetScreen> createState() =>
      _AdminPasswordResetScreenState();
}

class _AdminPasswordResetScreenState extends State<AdminPasswordResetScreen> {
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
      await widget.apiClient.resetAdminPassword(
        username: 'admin',
        setupCode: _setupCodeController.text,
        newPassword: _passwordController.text,
        confirmPassword: _confirmPasswordController.text,
      );
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = _formatResetError(error));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  String _formatResetError(Object error) {
    if (error is ApiRequestException) {
      if (error.statusCode == 409) {
        return '관리자 초기 설정이 필요합니다.';
      }
      if (error.statusCode == 422) {
        return '입력 내용을 확인해 주세요.';
      }
      if (error.statusCode == 400) {
        return '등록 코드 또는 입력 내용을 확인해 주세요.';
      }
    }
    return '비밀번호 재설정에 실패했습니다. 잠시 후 다시 시도해 주세요.';
  }

  @override
  Widget build(BuildContext context) {
    return AuthScreenFrame(
      key: const ValueKey('auth-password-reset-screen'),
      title: 'Admin 비밀번호 재설정',
      subtitle: '등록 코드로 admin 비밀번호를 재설정합니다.',
      child: Form(
        key: _formKey,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TextFormField(
              key: ValueKey('auth-password-reset-username-field'),
              initialValue: 'admin',
              readOnly: true,
              decoration: InputDecoration(
                labelText: 'ID',
                prefixIcon: Icon(Icons.person_outline),
              ),
            ),
            const SizedBox(height: 14),
            TextFormField(
              key: const ValueKey('auth-password-reset-code-field'),
              controller: _setupCodeController,
              obscureText: true,
              decoration: const InputDecoration(
                labelText: '등록 코드',
                prefixIcon: Icon(Icons.key_outlined),
              ),
              validator: (value) =>
                  (value == null || value.isEmpty) ? '등록 코드를 입력하세요.' : null,
            ),
            const SizedBox(height: 14),
            TextFormField(
              key: const ValueKey('auth-password-reset-password-field'),
              controller: _passwordController,
              obscureText: true,
              decoration: const InputDecoration(
                labelText: '새 비밀번호',
                prefixIcon: Icon(Icons.lock_outline),
              ),
              validator: (value) =>
                  (value == null || value.isEmpty) ? '새 비밀번호를 입력하세요.' : null,
            ),
            const SizedBox(height: 14),
            TextFormField(
              key: const ValueKey('auth-password-reset-confirm-password-field'),
              controller: _confirmPasswordController,
              obscureText: true,
              decoration: const InputDecoration(
                labelText: '새 비밀번호 확인',
                prefixIcon: Icon(Icons.lock_reset_outlined),
              ),
              validator: (value) =>
                  value != _passwordController.text ? '비밀번호가 일치하지 않습니다.' : null,
            ),
            if (_error != null) ...[
              const SizedBox(height: 14),
              Text(
                _error!,
                key: const ValueKey('auth-password-reset-error'),
                style: const TextStyle(color: Colors.redAccent),
              ),
            ],
            const SizedBox(height: 20),
            FilledButton.icon(
              key: const ValueKey('auth-password-reset-button'),
              onPressed: _loading ? null : _submit,
              icon: _loading
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.lock_reset_outlined),
              label: Text(_loading ? '재설정 중...' : '비밀번호 재설정'),
            ),
            const SizedBox(height: 8),
            TextButton(
              key: const ValueKey('auth-password-reset-back-button'),
              onPressed: _loading ? null : () => Navigator.of(context).pop(),
              child: const Text('로그인으로 돌아가기'),
            ),
          ],
        ),
      ),
    );
  }
}
