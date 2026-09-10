import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/network/api_client.dart';
import '../../models/auth_session.dart';
import '../../models/user_watchlist_item.dart';

class UserSettingsScreen extends StatefulWidget {
  const UserSettingsScreen({
    super.key,
    required this.apiClient,
    required this.user,
    required this.onLogout,
  });

  final ApiClient apiClient;
  final AuthUser user;
  final Future<void> Function() onLogout;

  @override
  State<UserSettingsScreen> createState() => _UserSettingsScreenState();
}

class _UserPasswordDialog extends StatefulWidget {
  const _UserPasswordDialog({required this.apiClient});

  final ApiClient apiClient;

  @override
  State<_UserPasswordDialog> createState() => _UserPasswordDialogState();
}

class _UserPasswordDialogState extends State<_UserPasswordDialog> {
  final _currentController = TextEditingController();
  final _newController = TextEditingController();
  final _confirmController = TextEditingController();
  String? _error;
  bool _loading = false;

  @override
  void dispose() {
    _currentController.dispose();
    _newController.dispose();
    _confirmController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_newController.text.isEmpty ||
        _newController.text != _confirmController.text) {
      setState(() => _error = '새 비밀번호를 확인해 주세요.');
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await widget.apiClient.changePassword(
        currentPassword: _currentController.text,
        newPassword: _newController.text,
        confirmPassword: _confirmController.text,
      );
      if (mounted) Navigator.of(context).pop(true);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      key: const ValueKey('user-password-dialog'),
      title: const Text('비밀번호 변경'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            key: const ValueKey('user-current-password-field'),
            controller: _currentController,
            obscureText: true,
            decoration: const InputDecoration(labelText: '현재 비밀번호'),
          ),
          TextField(
            key: const ValueKey('user-new-password-field'),
            controller: _newController,
            obscureText: true,
            decoration: const InputDecoration(labelText: '새 비밀번호'),
          ),
          TextField(
            key: const ValueKey('user-confirm-password-field'),
            controller: _confirmController,
            obscureText: true,
            decoration: const InputDecoration(labelText: '새 비밀번호 확인'),
          ),
          if (_error != null)
            Text(_error!, style: const TextStyle(color: Colors.redAccent)),
        ],
      ),
      actions: [
        TextButton(
          onPressed: _loading ? null : () => Navigator.of(context).pop(),
          child: const Text('취소'),
        ),
        FilledButton(
          key: const ValueKey('user-password-submit'),
          onPressed: _loading ? null : _submit,
          child: const Text('변경'),
        ),
      ],
    );
  }
}

class _UserSettingsScreenState extends State<UserSettingsScreen> {
  final _displayNameController = TextEditingController();
  final _symbolController = TextEditingController();
  Map<String, dynamic> _settings = <String, dynamic>{};
  List<UserWatchlistItem> _watchlist = const [];
  String? _error;
  bool _loading = true;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _displayNameController.dispose();
    _symbolController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final values = await widget.apiClient.fetchUserSettings();
      final items = await widget.apiClient.fetchUserWatchlist();
      if (!mounted) return;
      setState(() {
        _settings = values;
        _watchlist = items;
        _loading = false;
      });
      _displayNameController.text = values['display_name']?.toString() ?? '';
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = error.toString();
      });
    }
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      final values = <String, dynamic>{
        ..._settings,
        'display_name': _displayNameController.text.trim(),
      };
      final saved = await widget.apiClient.updateUserSettings(values);
      if (!mounted) return;
      setState(() {
        _settings = saved;
        _saving = false;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('설정이 저장되었습니다.')),
      );
    } catch (error) {
      if (mounted) setState(() => _saving = false);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(error.toString())),
        );
      }
    }
  }

  Future<void> _addSymbol() async {
    final symbol = _symbolController.text.trim();
    if (symbol.isEmpty) return;
    try {
      final item = await widget.apiClient.addUserWatchlist(symbol: symbol);
      if (!mounted) return;
      setState(() {
        _watchlist = [..._watchlist, item];
        _symbolController.clear();
      });
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(error.toString())),
        );
      }
    }
  }

  Future<void> _removeSymbol(String symbol) async {
    try {
      await widget.apiClient.removeUserWatchlist(symbol);
      if (mounted) {
        setState(() {
          _watchlist = _watchlist.where((item) => item.symbol != symbol).toList();
        });
      }
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(error.toString())),
        );
      }
    }
  }

  Future<void> _changePassword() async {
    final changed = await showDialog<bool>(
      context: context,
      builder: (_) => _UserPasswordDialog(apiClient: widget.apiClient),
    );
    if (changed == true && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('비밀번호가 변경되었습니다.')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      key: const ValueKey('user-settings-screen'),
      appBar: AppBar(title: const Text('Settings')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Card(
                  key: const ValueKey('user-account-card'),
                  child: ListTile(
                    leading: const Icon(Icons.account_circle_outlined),
                    title: Text(widget.user.username),
                    subtitle: const Text('일반 사용자 · 운영 기능은 관리자만 사용할 수 있습니다.'),
                  ),
                ),
                if (_error != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 10),
                    child: Text(
                      _error!,
                      key: const ValueKey('user-settings-error'),
                      style: const TextStyle(color: Colors.orangeAccent),
                    ),
                  ),
                const SizedBox(height: 12),
                Card(
                  key: const ValueKey('user-settings-card'),
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const Text(
                          '내 설정',
                          style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800),
                        ),
                        const SizedBox(height: 12),
                        TextField(
                          key: const ValueKey('user-settings-display-name-field'),
                          controller: _displayNameController,
                          decoration: const InputDecoration(
                            labelText: '표시 이름',
                            prefixIcon: Icon(Icons.badge_outlined),
                          ),
                        ),
                        const SizedBox(height: 12),
                        FilledButton.icon(
                          key: const ValueKey('user-settings-save-button'),
                          onPressed: _saving ? null : _save,
                          icon: const Icon(Icons.save_outlined),
                          label: Text(_saving ? '저장 중...' : '설정 저장'),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                Card(
                  key: const ValueKey('user-watchlist-card'),
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const Text(
                          '내 관심종목',
                          style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800),
                        ),
                        const SizedBox(height: 10),
                        Row(
                          children: [
                            Expanded(
                              child: TextField(
                                key: const ValueKey('user-watchlist-symbol-field'),
                                controller: _symbolController,
                                decoration: const InputDecoration(
                                  labelText: '종목 코드',
                                  hintText: '예: 005930',
                                ),
                                onSubmitted: (_) => _addSymbol(),
                              ),
                            ),
                            const SizedBox(width: 8),
                            IconButton(
                              key: const ValueKey('user-watchlist-add-button'),
                              onPressed: _addSymbol,
                              icon: const Icon(Icons.add_circle_outline),
                            ),
                          ],
                        ),
                        ..._watchlist.map(
                          (item) => ListTile(
                            key: ValueKey('user-watchlist-item-${item.symbol}'),
                            contentPadding: EdgeInsets.zero,
                            title: Text(item.symbol),
                            subtitle: Text('${item.provider} · ${item.market}'),
                            trailing: IconButton(
                              key: ValueKey('user-watchlist-remove-${item.symbol}'),
                              onPressed: () => _removeSymbol(item.symbol),
                              icon: const Icon(Icons.remove_circle_outline),
                            ),
                          ),
                        ),
                        if (_watchlist.isEmpty)
                          const Text(
                            '등록된 관심종목이 없습니다.',
                            style: TextStyle(color: Colors.white70),
                          ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                Card(
                  key: const ValueKey('user-account-actions-card'),
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Wrap(
                      spacing: 10,
                      runSpacing: 10,
                      children: [
                        OutlinedButton.icon(
                          key: const ValueKey('user-change-password-button'),
                          onPressed: _changePassword,
                          icon: const Icon(Icons.lock_reset_outlined),
                          label: const Text('비밀번호 변경'),
                        ),
                        FilledButton.icon(
                          key: const ValueKey('user-logout-button'),
                          onPressed: widget.onLogout,
                          icon: const Icon(Icons.logout),
                          label: const Text('로그아웃'),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
    );
  }
}
