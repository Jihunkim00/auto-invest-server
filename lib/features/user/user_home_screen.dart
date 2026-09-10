import 'package:flutter/material.dart';

import '../../models/auth_session.dart';

class UserHomeScreen extends StatelessWidget {
  const UserHomeScreen({super.key, required this.user});

  final AuthUser user;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      key: const ValueKey('user-home-screen'),
      appBar: AppBar(title: const Text('Home')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            key: const ValueKey('user-home-account-status'),
            child: ListTile(
              leading: const Icon(Icons.verified_user_outlined),
              title: Text('${user.username} 계정'),
              subtitle: const Text('계정이 활성화되어 있습니다.'),
            ),
          ),
          const SizedBox(height: 12),
          Card(
            key: const ValueKey('user-home-safe-status'),
            child: const ListTile(
              leading: Icon(Icons.shield_outlined, color: Colors.greenAccent),
              title: Text('안전한 읽기 전용 상태'),
              subtitle: Text('주문·브로커 연결·자동매매 운영 기능은 관리자 화면에서만 제공됩니다.'),
            ),
          ),
          const SizedBox(height: 12),
          const Card(
            child: ListTile(
              leading: Icon(Icons.info_outline),
              title: Text('내 계정'),
              subtitle: Text('Settings에서 개인 설정과 관심종목을 관리할 수 있습니다.'),
            ),
          ),
        ],
      ),
    );
  }
}
