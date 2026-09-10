class AuthUser {
  const AuthUser({
    this.id,
    required this.username,
    required this.role,
    required this.enabled,
    required this.setupCompleted,
  });

  final int? id;
  final String username;
  final String role;
  final bool enabled;
  final bool setupCompleted;

  factory AuthUser.fromJson(Map<String, dynamic> json) {
    return AuthUser(
      id: json['id'] is num
          ? (json['id'] as num).toInt()
          : int.tryParse(json['id']?.toString() ?? ''),
      username: json['username']?.toString() ?? '',
      role: json['role']?.toString() ?? '',
      enabled: json['enabled'] == true,
      setupCompleted: json['setup_completed'] == true,
    );
  }
}

class AuthSessionState {
  const AuthSessionState({
    required this.authenticated,
    required this.setupRequired,
    this.user,
  });

  final bool authenticated;
  final bool setupRequired;
  final AuthUser? user;

  bool get isAuthenticated => authenticated;

  factory AuthSessionState.fromJson(Map<String, dynamic> json) {
    final rawUser = json['user'];
    final user = rawUser is Map
        ? AuthUser.fromJson(Map<String, dynamic>.from(rawUser))
        : null;
    final authenticated = json['authenticated'] == true;
    return AuthSessionState(
      authenticated: authenticated,
      setupRequired: json['setup_required'] == true ||
          (!authenticated && user != null && !user.setupCompleted),
      user: user,
    );
  }
}
