import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/network/api_client.dart';
import '../../models/auth_session.dart';

class AdminUserManagementPanel extends StatefulWidget {
  const AdminUserManagementPanel({super.key, required this.apiClient});

  final ApiClient apiClient;

  @override
  State<AdminUserManagementPanel> createState() =>
      _AdminUserManagementPanelState();
}

class _AdminUserManagementPanelState
    extends State<AdminUserManagementPanel> {
  List<AuthUser> _users = const [];
  String? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    try {
      final users = await widget.apiClient.fetchAdminUsers();
      if (!mounted) return;
      setState(() {
        _users = users;
        _loading = false;
      });
    } catch (error) {
      if (mounted) {
        setState(() {
          _loading = false;
          _error = error.toString();
        });
      }
    }
  }

  Future<void> _createUser() async {
    final controller = TextEditingController();
    final username = await showDialog<String>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('사용자 추가'),
        content: TextField(
          key: const ValueKey('admin-create-username-field'),
          controller: controller,
          autofocus: true,
          decoration: const InputDecoration(labelText: '사용자 ID'),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: const Text('취소'),
          ),
          FilledButton(
            key: const ValueKey('admin-create-user-submit'),
            onPressed: () => Navigator.of(dialogContext).pop(controller.text),
            child: const Text('생성'),
          ),
        ],
      ),
    );
    controller.dispose();
    if (!mounted || username == null || username.trim().isEmpty) return;
    try {
      final user = await widget.apiClient.createAdminUser(
        username: username.trim(),
      );
      if (mounted) setState(() => _users = [..._users, user]);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  Future<void> _setStatus(AuthUser user, bool enabled) async {
    if (user.id == null) return;
    try {
      final updated = await widget.apiClient.updateAdminUserStatus(
        userId: user.id!,
        enabled: enabled,
      );
      if (!mounted) return;
      setState(() {
        _users = _users
            .map((item) => item.id == updated.id ? updated : item)
            .toList();
      });
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      key: const ValueKey('admin-user-management'),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                const Expanded(
                  child: Text(
                    '사용자 관리',
                    style: TextStyle(
                      color: Colors.lightBlueAccent,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
                IconButton(
                  key: const ValueKey('admin-add-user'),
                  onPressed: _users.length >= 5 ? null : _createUser,
                  icon: const Icon(Icons.person_add_alt_1),
                  tooltip: '사용자 추가',
                ),
              ],
            ),
            const Text(
              '관리자가 사용자 ID를 생성하면 사용자가 등록 코드로 최초 비밀번호를 설정합니다.',
              style: TextStyle(color: Colors.white70),
            ),
            if (_error != null) ...[
              const SizedBox(height: 8),
              Text(
                _error!,
                key: const ValueKey('admin-user-management-error'),
                style: const TextStyle(color: Colors.orangeAccent),
              ),
            ],
            const SizedBox(height: 8),
            if (_loading)
              const Center(child: CircularProgressIndicator())
            else if (_users.isEmpty)
              const Text('등록된 사용자가 없습니다.')
            else
              ..._users.map(
                (user) => ListTile(
                  key: ValueKey('admin-user-${user.id ?? user.username}'),
                  contentPadding: EdgeInsets.zero,
                  leading: Icon(
                    user.role == 'admin'
                        ? Icons.admin_panel_settings_outlined
                        : Icons.person_outline,
                  ),
                  title: Text(user.username),
                  subtitle: Text(
                    user.role == 'admin'
                        ? '관리자'
                        : user.setupCompleted
                            ? '사용자 · 등록 완료'
                            : '사용자 · 등록 대기',
                  ),
                  trailing: user.role == 'admin'
                      ? const Text('활성')
                      : Switch(
                          key: ValueKey('admin-user-status-${user.id}'),
                          value: user.enabled,
                          onChanged: (value) => _setStatus(user, value),
                        ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
