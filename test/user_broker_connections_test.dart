import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/user/user_settings_screen.dart';
import 'package:auto_invest_dashboard/models/auth_session.dart';
import 'package:auto_invest_dashboard/models/user_broker_credential.dart';
import 'package:auto_invest_dashboard/models/user_watchlist_item.dart';

void main() {
  testWidgets(
      'regular user can manage broker credentials without refilling secrets',
      (tester) async {
    final api = _BrokerSettingsApi();
    await tester.binding.setSurfaceSize(const Size(800, 1400));
    addTearDown(() async {
      await tester.binding.setSurfaceSize(null);
    });

    await tester.pumpWidget(
      MaterialApp(
        home: UserSettingsScreen(
          apiClient: api,
          user: const AuthUser(
            username: 'regular-user',
            role: 'user',
            enabled: true,
            setupCompleted: true,
          ),
          onLogout: () async {},
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('user-broker-connections-card')),
        findsOneWidget);
    expect(find.text('증권사 연결'), findsOneWidget);
    expect(find.text('한국투자증권'), findsOneWidget);
    expect(find.text('거래 환경'), findsNWidgets(2));
    expect(find.text('앱 키'), findsOneWidget);
    expect(find.text('앱 시크릿'), findsOneWidget);
    expect(find.text('HTS ID'), findsOneWidget);
    expect(find.text('계좌번호'), findsOneWidget);
    expect(find.text('API 키'), findsOneWidget);
    expect(find.text('시크릿 키'), findsOneWidget);
    expect(find.text('저장'), findsNWidgets(2));
    expect(find.text('연결 확인'), findsNWidgets(2));
    expect(find.text('모의투자 환경입니다.'), findsNWidgets(2));
    expect(find.text('한국투자증권 Open API에서 발급받은 정보를 입력하세요.'), findsOneWidget);
    expect(find.text('Alpaca에서 발급받은 API 정보를 입력하세요.'), findsOneWidget);
    expect(find.text('미설정'), findsNWidgets(2));

    await tester.enterText(
      find.byKey(const ValueKey('user-broker-kis-app-key')),
      'user-app-key',
    );
    await tester.enterText(
      find.byKey(const ValueKey('user-broker-kis-app-secret')),
      'user-app-secret',
    );
    await tester.enterText(
      find.byKey(const ValueKey('user-broker-kis-hts-id')),
      'user-hts-id',
    );
    await tester.enterText(
      find.byKey(const ValueKey('user-broker-kis-account-no')),
      '12345678',
    );
    await tester.enterText(
      find.byKey(const ValueKey('user-broker-kis-product-code')),
      '01',
    );
    await tester.ensureVisible(
      find.byKey(const ValueKey('user-broker-kis-save')),
    );
    await tester.tap(find.byKey(const ValueKey('user-broker-kis-save')));
    await tester.pumpAndSettle();

    expect(api.savedProviders, contains('kis'));
    expect(api.savedCredentials.single['hts_id'], 'user-hts-id');
    expect(find.text('설정됨'), findsOneWidget);
    expect(find.text('HTS ID: ****-hts'), findsOneWidget);
    expect(
      tester
          .widget<TextField>(
            find.byKey(const ValueKey('user-broker-kis-app-secret')),
          )
          .controller!
          .text,
      isEmpty,
    );

    await tester.ensureVisible(
      find.byKey(const ValueKey('user-broker-kis-validate')),
    );
    await tester.tap(find.byKey(const ValueKey('user-broker-kis-validate')));
    await tester.pumpAndSettle();

    expect(api.validationCalls, 1);
    expect(find.text('연결 확인됨'), findsOneWidget);

    await tester.ensureVisible(
      find.byKey(const ValueKey('user-broker-kis-remove')),
    );
    await tester.tap(find.byKey(const ValueKey('user-broker-kis-remove')));
    await tester.pumpAndSettle();

    expect(api.removeCalls, 1);
    expect(find.text('미설정'), findsNWidgets(2));
  });
}

class _BrokerSettingsApi extends ApiClient {
  final Map<String, UserBrokerCredential> _saved = {};
  final List<String> savedProviders = [];
  final List<Map<String, dynamic>> savedCredentials = [];
  int validationCalls = 0;
  int removeCalls = 0;

  @override
  Future<Map<String, dynamic>> fetchUserSettings() async => {};

  @override
  Future<List<UserWatchlistItem>> fetchUserWatchlist() async => [];

  @override
  Future<List<UserBrokerCredential>> fetchUserBrokers() async => [
        'kis',
        'alpaca'
      ].map((provider) => _saved[provider] ?? _empty(provider)).toList();

  @override
  Future<UserBrokerCredential> saveUserBroker(
    String provider,
    Map<String, dynamic> credentials,
  ) async {
    savedProviders.add(provider);
    savedCredentials.add(credentials);
    final saved = UserBrokerCredential(
      provider: provider,
      configured: true,
      environment: credentials['environment']?.toString() ?? 'paper',
      appKeyMasked: provider == 'kis' ? '****-key' : null,
      htsIdMasked: provider == 'kis' ? '****-hts' : null,
      accountNoMasked: provider == 'kis' ? '****5678' : null,
      apiKeyMasked: provider == 'alpaca' ? '****-key' : null,
      secretConfigured: true,
      appSecretConfigured: provider == 'kis',
      secretKeyConfigured: provider == 'alpaca',
    );
    _saved[provider] = saved;
    return saved;
  }

  @override
  Future<Map<String, dynamic>> validateUserBroker(String provider) async {
    validationCalls += 1;
    final current = _saved[provider]!;
    _saved[provider] = current.withValidation(status: 'success', error: null);
    return {
      'provider': provider,
      'valid': true,
      'status': 'success',
      'message': null,
    };
  }

  @override
  Future<void> removeUserBroker(String provider) async {
    removeCalls += 1;
    _saved.remove(provider);
  }

  static UserBrokerCredential _empty(String provider) {
    return UserBrokerCredential(provider: provider, configured: false);
  }
}
