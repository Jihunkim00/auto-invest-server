import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/auth/admin_setup_screen.dart';
import 'package:auto_invest_dashboard/features/auth/auth_gate.dart';
import 'package:auto_invest_dashboard/features/auth/login_screen.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/settings/settings_screen.dart';
import 'package:auto_invest_dashboard/models/auth_session.dart';

void main() {
  testWidgets('AdminSetupScreen submits setup fields', (tester) async {
    final api = _FakeAuthApiClient();
    var completed = false;

    await tester.pumpWidget(
      MaterialApp(
        home: AdminSetupScreen(
          apiClient: api,
          onSetupCompleted: () async => completed = true,
        ),
      ),
    );

    await tester.enterText(
      find.byKey(const ValueKey('auth-setup-code-field')),
      'autoinvest테스터',
    );
    await tester.enterText(
      find.byKey(const ValueKey('auth-setup-password-field')),
      'new-password',
    );
    await tester.enterText(
      find.byKey(const ValueKey('auth-setup-confirm-password-field')),
      'new-password',
    );
    await tester.tap(find.byKey(const ValueKey('auth-setup-button')));
    await tester.pumpAndSettle();

    expect(completed, isTrue);
    expect(api.setupCalls, 1);
  });

  testWidgets('LoginScreen reports failure and supports success',
      (tester) async {
    final api = _FakeAuthApiClient()..loginError = true;
    var completed = false;

    await tester.pumpWidget(
      MaterialApp(
        home: LoginScreen(
          apiClient: api,
          onLoginCompleted: () async => completed = true,
        ),
      ),
    );

    await tester.enterText(
      find.byKey(const ValueKey('auth-password-field')),
      'wrong-password',
    );
    await tester.tap(find.byKey(const ValueKey('auth-login-button')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('auth-login-error')), findsOneWidget);
    expect(completed, isFalse);

    api.loginError = false;
    await tester.tap(find.byKey(const ValueKey('auth-login-button')));
    await tester.pumpAndSettle();
    expect(completed, isTrue);
  });

  testWidgets('LoginScreen opens password reset and returns after success',
      (tester) async {
    final api = _FakeAuthApiClient();

    await tester.pumpWidget(
      MaterialApp(
        home: LoginScreen(apiClient: api),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('비밀번호를 잊으셨나요?'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('auth-password-reset-link')),
      findsOneWidget,
    );
    await tester.tap(find.byKey(const ValueKey('auth-password-reset-link')));
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey('auth-password-reset-screen')),
      findsOneWidget,
    );
    await tester.enterText(
      find.byKey(const ValueKey('auth-password-reset-code-field')),
      'autoinvest테스터',
    );
    await tester.enterText(
      find.byKey(const ValueKey('auth-password-reset-password-field')),
      'reset-password',
    );
    await tester.enterText(
      find.byKey(const ValueKey('auth-password-reset-confirm-password-field')),
      'reset-password',
    );
    await tester.tap(
      find.byKey(const ValueKey('auth-password-reset-button')),
    );
    await tester.pumpAndSettle();

    expect(api.passwordResetCalls, 1);
    expect(find.byKey(const ValueKey('auth-login-screen')), findsOneWidget);
    expect(
      find.text('비밀번호가 재설정되었습니다. 새 비밀번호로 로그인해 주세요.'),
      findsOneWidget,
    );
  });

  testWidgets('Password reset shows a friendly error', (tester) async {
    final api = _FakeAuthApiClient()..passwordResetError = true;

    await tester.pumpWidget(
      MaterialApp(
        home: LoginScreen(apiClient: api),
      ),
    );
    await tester.tap(find.byKey(const ValueKey('auth-password-reset-link')));
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const ValueKey('auth-password-reset-code-field')),
      'wrong-code',
    );
    await tester.enterText(
      find.byKey(const ValueKey('auth-password-reset-password-field')),
      'reset-password',
    );
    await tester.enterText(
      find.byKey(const ValueKey('auth-password-reset-confirm-password-field')),
      'reset-password',
    );
    await tester.tap(
      find.byKey(const ValueKey('auth-password-reset-button')),
    );
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey('auth-password-reset-error')),
      findsOneWidget,
    );
    expect(
      find.text('등록 코드 또는 입력 내용을 확인해 주세요.'),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('auth-password-reset-screen')),
      findsOneWidget,
    );
  });

  testWidgets('AuthGate renders authenticated existing app and logs out',
      (tester) async {
    final api = _FakeAuthApiClient(
      state: const AuthSessionState(
        authenticated: true,
        setupRequired: false,
        user: AuthUser(
          username: 'admin',
          role: 'admin',
          enabled: true,
          setupCompleted: true,
        ),
      ),
    );

    await tester.pumpWidget(
      MaterialApp(
        home: AuthGate(
          apiClient: api,
          authenticatedBuilder: (context, onLogout) => Center(
            child: FilledButton(
              key: const ValueKey('existing-app-logout'),
              onPressed: () => onLogout(context),
              child: const Text('Existing Auto Invest App'),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Existing Auto Invest App'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('existing-app-logout')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('auth-login-screen')), findsOneWidget);
    expect(api.logoutCalls, 1);
  });

  testWidgets('Settings shows account and password change success snackbar',
      (tester) async {
    final api = _FakeAuthApiClient();
    final controller = DashboardController(api, autoload: false);
    addTearDown(controller.dispose);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SettingsScreen(
            controller: controller,
            onLogout: () async {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.byKey(const ValueKey('settings-account-card')),
      500,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('settings-account-card')), findsOneWidget);
    expect(find.byKey(const ValueKey('settings-admin-id')), findsOneWidget);
    expect(find.text('admin'), findsOneWidget);

    await tester.tap(
      find.byKey(const ValueKey('settings-change-password-button')),
    );
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey('settings-password-dialog')),
      findsOneWidget,
    );

    await tester.enterText(
      find.byKey(const ValueKey('settings-current-password-field')),
      'current-password',
    );
    await tester.enterText(
      find.byKey(const ValueKey('settings-new-password-field')),
      'new-password',
    );
    await tester.enterText(
      find.byKey(const ValueKey('settings-confirm-password-field')),
      'new-password',
    );
    await tester.tap(
      find.byKey(const ValueKey('settings-password-change-submit')),
    );
    await tester.pumpAndSettle();

    expect(api.passwordChangeCalls, 1);
    expect(
        find.byKey(const ValueKey('settings-password-dialog')), findsNothing);
    expect(find.text('비밀번호가 변경되었습니다.'), findsOneWidget);
  });

  testWidgets('Settings keeps password dialog open and shows friendly error',
      (tester) async {
    final api = _FakeAuthApiClient()..passwordChangeError = true;
    final controller = DashboardController(api, autoload: false);
    addTearDown(controller.dispose);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SettingsScreen(
            controller: controller,
            onLogout: () async {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.byKey(const ValueKey('settings-account-card')),
      500,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();
    await tester.tap(
      find.byKey(const ValueKey('settings-change-password-button')),
    );
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const ValueKey('settings-current-password-field')),
      'wrong-password',
    );
    await tester.enterText(
      find.byKey(const ValueKey('settings-new-password-field')),
      'new-password',
    );
    await tester.enterText(
      find.byKey(const ValueKey('settings-confirm-password-field')),
      'new-password',
    );
    await tester.tap(
      find.byKey(const ValueKey('settings-password-change-submit')),
    );
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey('settings-password-change-error')),
      findsOneWidget,
    );
    expect(
      find.text('현재 비밀번호가 올바르지 않거나 로그인 세션이 만료되었습니다.'),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('settings-password-dialog')),
      findsOneWidget,
    );
  });
}

class _FakeAuthApiClient extends ApiClient {
  _FakeAuthApiClient({
    AuthSessionState? state,
  }) : state = state ??
            const AuthSessionState(
              authenticated: false,
              setupRequired: true,
            );

  AuthSessionState state;
  bool loginError = false;
  bool passwordChangeError = false;
  bool passwordResetError = false;
  int setupCalls = 0;
  int logoutCalls = 0;
  int passwordChangeCalls = 0;
  int passwordResetCalls = 0;

  @override
  Future<AuthSessionState> fetchAuthMe() async => state;

  @override
  Future<void> setupAdmin({
    required String username,
    required String setupCode,
    required String newPassword,
    required String confirmPassword,
  }) async {
    setupCalls += 1;
    state = const AuthSessionState(
      authenticated: false,
      setupRequired: false,
    );
  }

  @override
  Future<void> loginAdmin({
    required String username,
    required String password,
  }) async {
    if (loginError) {
      throw const ApiRequestException('Invalid username or password.');
    }
    state = const AuthSessionState(
      authenticated: true,
      setupRequired: false,
      user: AuthUser(
        username: 'admin',
        role: 'admin',
        enabled: true,
        setupCompleted: true,
      ),
    );
  }

  @override
  Future<void> resetAdminPassword({
    required String username,
    required String setupCode,
    required String newPassword,
    required String confirmPassword,
  }) async {
    passwordResetCalls += 1;
    if (passwordResetError) {
      throw const ApiRequestException(
        'Invalid setup code.',
        statusCode: 400,
      );
    }
  }

  @override
  Future<void> logout() async {
    logoutCalls += 1;
    state = const AuthSessionState(
      authenticated: false,
      setupRequired: false,
    );
  }

  @override
  Future<void> changeAdminPassword({
    required String currentPassword,
    required String newPassword,
    required String confirmPassword,
  }) async {
    passwordChangeCalls += 1;
    if (passwordChangeError) {
      throw const ApiRequestException(
        'Current password is incorrect.',
        statusCode: 401,
      );
    }
  }
}
