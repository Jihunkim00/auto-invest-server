import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/app.dart';
import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/auth/user_registration_screen.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/models/auth_session.dart';
import 'package:auto_invest_dashboard/models/user_watchlist_item.dart';


void main() {
  testWidgets('registration screen validates and submits user setup',
      (tester) async {
    final api = _UserDataApi();
    await tester.pumpWidget(
      MaterialApp(home: UserRegistrationScreen(apiClient: api)),
    );

    await tester.tap(find.byKey(const ValueKey('auth-register-button')));
    await tester.pump();
    expect(find.text('사용자 ID을(를) 입력해 주세요.'), findsOneWidget);

    await tester.enterText(
      find.byKey(const ValueKey('auth-register-username-field')),
      'test01',
    );
    await tester.enterText(
      find.byKey(const ValueKey('auth-register-code-field')),
      'autoinvest테스터',
    );
    await tester.enterText(
      find.byKey(const ValueKey('auth-register-password-field')),
      'user-password',
    );
    await tester.enterText(
      find.byKey(const ValueKey('auth-register-confirm-password-field')),
      'user-password',
    );
    await tester.tap(find.byKey(const ValueKey('auth-register-button')));
    await tester.pumpAndSettle();
    expect(api.registerCalls, 1);
  });

  testWidgets('regular user gets Home and Settings only', (tester) async {
    final api = _UserDataApi(
      state: const AuthSessionState(
        authenticated: true,
        setupRequired: false,
        user: AuthUser(
          username: 'test01',
          role: 'user',
          enabled: true,
          setupCompleted: true,
        ),
      ),
    );
    final controller = DashboardController(api, autoload: false);

    await tester.pumpWidget(
      MaterialApp(
        home: AutoInvestApp(
          controller: controller,
          authenticationEnabled: true,
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('user-home-screen')), findsOneWidget);
    expect(find.text('Settings'), findsOneWidget);
    expect(find.text('AI 도우미'), findsNothing);
    expect(find.byKey(const ValueKey('home-open-admin')), findsNothing);
  });
}


class _UserDataApi extends ApiClient {
  _UserDataApi({
    this.state = const AuthSessionState(
      authenticated: false,
      setupRequired: false,
    ),
  });

  AuthSessionState state;
  int registerCalls = 0;

  @override
  Future<AuthSessionState> fetchAuthMe() async => state;

  @override
  Future<void> registerUser({
    required String username,
    required String setupCode,
    required String newPassword,
    required String confirmPassword,
  }) async {
    registerCalls += 1;
  }

  @override
  Future<Map<String, dynamic>> fetchUserSettings() async => {};

  @override
  Future<List<UserWatchlistItem>> fetchUserWatchlist() async => [];
}
