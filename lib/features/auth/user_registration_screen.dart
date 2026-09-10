import 'package:flutter/material.dart';

import '../../core/network/api_client.dart';
import 'auth_screen_frame.dart';

class UserRegistrationScreen extends StatefulWidget {
  const UserRegistrationScreen({
    super.key,
    required this.apiClient,
  });

  final ApiClient apiClient;

  @override
  State<UserRegistrationScreen> createState() => _UserRegistrationScreenState();
}


class _UserRegistrationScreenState extends State<UserRegistrationScreen> {
  final _formKey = GlobalKey<FormState>();
  final _usernameController = TextEditingController();
  final _codeController = TextEditingController();
  final _passwordController = TextEditingController();
  final _confirmController = TextEditingController();
  String? _error;
  bool _loading = false;

  @override
  void dispose() {
    _usernameController.dispose();
    _codeController.dispose();
    _passwordController.dispose();
    _confirmController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await widget.apiClient.registerUser(
        username: _usernameController.text.trim(),
        setupCode: _codeController.text,
        newPassword: _passwordController.text,
        confirmPassword: _confirmController.text,
      );
      if (mounted) Navigator.of(context).pop(true);
    } catch (error) {
      if (mounted) setState(() => _error = formatAuthError(error));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  String? _required(String? value, String label) {
    if (value == null || value.trim().isEmpty) return '$label을(를) 입력해 주세요.';
    return null;
  }

  @override
  Widget build(BuildContext context) {
    return AuthScreenFrame(
      key: const ValueKey('auth-user-registration-screen'),
      title: '사용자 등록',
      subtitle: '관리자가 만든 사용자 ID로 최초 등록을 완료합니다.',
      child: Form(
        key: _formKey,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TextFormField(
              key: const ValueKey('auth-register-username-field'),
              controller: _usernameController,
              decoration: const InputDecoration(
                labelText: '사용자 ID',
                prefixIcon: Icon(Icons.person_outline),
              ),
              validator: (value) => _required(value, '사용자 ID'),
              textInputAction: TextInputAction.next,
            ),
            const SizedBox(height: 12),
            TextFormField(
              key: const ValueKey('auth-register-code-field'),
              controller: _codeController,
              decoration: const InputDecoration(
                labelText: '등록 코드',
                prefixIcon: Icon(Icons.key_outlined),
              ),
              validator: (value) => _required(value, '등록 코드'),
              textInputAction: TextInputAction.next,
            ),
            const SizedBox(height: 12),
            TextFormField(
              key: const ValueKey('auth-register-password-field'),
              controller: _passwordController,
              obscureText: true,
              decoration: const InputDecoration(
                labelText: '새 비밀번호',
                prefixIcon: Icon(Icons.lock_outline),
              ),
              validator: (value) => _required(value, '새 비밀번호'),
              textInputAction: TextInputAction.next,
            ),
            const SizedBox(height: 12),
            TextFormField(
              key: const ValueKey('auth-register-confirm-password-field'),
              controller: _confirmController,
              obscureText: true,
              decoration: const InputDecoration(
                labelText: '새 비밀번호 확인',
                prefixIcon: Icon(Icons.lock_reset_outlined),
              ),
              validator: (value) {
                final required = _required(value, '새 비밀번호 확인');
                if (required != null) return required;
                if (value != _passwordController.text) {
                  return '비밀번호가 일치하지 않습니다.';
                }
                return null;
              },
            ),
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(
                _error!,
                key: const ValueKey('auth-register-error'),
                style: const TextStyle(color: Colors.redAccent),
              ),
            ],
            const SizedBox(height: 20),
            FilledButton.icon(
              key: const ValueKey('auth-register-button'),
              onPressed: _loading ? null : _submit,
              icon: _loading
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.person_add_alt_1),
              label: Text(_loading ? '등록 중...' : '등록 완료'),
            ),
            TextButton(
              key: const ValueKey('auth-register-back-button'),
              onPressed: _loading ? null : () => Navigator.of(context).pop(),
              child: const Text('로그인으로 돌아가기'),
            ),
          ],
        ),
      ),
    );
  }
}
