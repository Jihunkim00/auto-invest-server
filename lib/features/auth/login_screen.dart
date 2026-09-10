import 'package:flutter/material.dart';

import '../../core/network/api_client.dart';
import 'admin_password_reset_screen.dart';
import 'auth_screen_frame.dart';
import 'user_registration_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({
    super.key,
    required this.apiClient,
    this.onLoginCompleted,
  });

  final ApiClient apiClient;
  final Future<void> Function()? onLoginCompleted;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _usernameController = TextEditingController(text: 'admin');
  final _passwordController = TextEditingController();
  String? _error;
  bool _loading = false;

  @override
  void dispose() {
    _usernameController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await widget.apiClient.loginAdmin(
        username: _usernameController.text.trim(),
        password: _passwordController.text,
      );
      if (!mounted) return;
      await widget.onLoginCompleted?.call();
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = formatAuthError(error));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _openRegistration() async {
    final registered = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => UserRegistrationScreen(
          apiClient: widget.apiClient,
        ),
      ),
    );
    if (!mounted || registered != true) return;
    _usernameController.clear();
    _passwordController.clear();
    setState(() => _error = null);
    ScaffoldMessenger.maybeOf(context)?.showSnackBar(
      const SnackBar(content: Text('등록이 완료되었습니다. 새 비밀번호로 로그인해 주세요.')),
    );
  }

  Future<void> _openPasswordReset() async {
    final reset = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => AdminPasswordResetScreen(
          apiClient: widget.apiClient,
        ),
      ),
    );
    if (!mounted || reset != true) return;
    _passwordController.clear();
    setState(() => _error = null);
    ScaffoldMessenger.maybeOf(context)?.showSnackBar(
      const SnackBar(
        content: Text('비밀번호가 재설정되었습니다. 새 비밀번호로 로그인해 주세요.'),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return AuthScreenFrame(
      key: const ValueKey('auth-login-screen'),
      title: '로그인',
      subtitle: '관리자 또는 일반 사용자 계정으로 Auto Invest에 접속합니다.',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                TextFormField(
                  key: const ValueKey('auth-username-field'),
                  controller: _usernameController,
                  decoration: const InputDecoration(
                    labelText: 'ID',
                    prefixIcon: Icon(Icons.person_outline),
                  ),
                  textInputAction: TextInputAction.next,
                  validator: (value) => (value == null || value.trim().isEmpty)
                      ? 'ID를 입력하세요.'
                      : null,
                ),
                const SizedBox(height: 14),
                TextFormField(
                  key: const ValueKey('auth-password-field'),
                  controller: _passwordController,
                  obscureText: true,
                  decoration: const InputDecoration(
                    labelText: 'Password',
                    prefixIcon: Icon(Icons.lock_outline),
                  ),
                  onFieldSubmitted: (_) => _submit(),
                  validator: (value) =>
                      (value == null || value.isEmpty) ? '비밀번호를 입력하세요.' : null,
                ),
                if (_error != null) ...[
                  const SizedBox(height: 14),
                  Text(
                    _error!,
                    key: const ValueKey('auth-login-error'),
                    style: const TextStyle(color: Colors.redAccent),
                  ),
                ],
                const SizedBox(height: 20),
                FilledButton.icon(
                  key: const ValueKey('auth-login-button'),
                  onPressed: _loading ? null : _submit,
                  icon: _loading
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.login),
                  label: Text(_loading ? '로그인 중...' : '로그인'),
                ),
              ],
            ),
          ),
          const SizedBox(height: 20),
          OutlinedButton.icon(
            key: const ValueKey('auth-user-registration-link'),
            onPressed: _loading ? null : _openRegistration,
            icon: const Icon(Icons.person_add_alt_1),
            label: const Text('일반 사용자 등록'),
          ),
          const Text(
            '비밀번호를 잊으셨나요?',
            textAlign: TextAlign.center,
          ),
          TextButton(
            key: const ValueKey('auth-password-reset-link'),
            onPressed: _loading ? null : _openPasswordReset,
            child: const Text('비밀번호 재설정'),
          ),
        ],
      ),
    );
  }
}
